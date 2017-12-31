from collections import OrderedDict
from django.conf import settings
from django.shortcuts import render
from .sources import SOURCE_MAP
import time
from datetime import datetime

from requests_aws4auth import AWS4Auth
from elasticsearch import Elasticsearch, RequestsHttpConnection
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import Q, FunctionScore, SF
from elasticsearch_dsl.aggs import A, Filters

# host = settings.AWS['ES_HOST']
host = "localhost"
# awsauth = AWS4Auth(settings.AWS['ACCESS_KEY'], settings.AWS['SECRET_KEY'], 'us-east-2', 'es')

es = Elasticsearch(
    hosts=[{'host': host, 'port': 9200}],
    use_ssl=False,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)

def index(request):

    s = Search(using=es, index="fcc-comments")

    total = s.count()
    pro_titleii = s.query('match', **{'analysis.titleii': True}).count()
    anti_titleii = s.query('match', **{'analysis.titleii': False}).count()
    unknown_titleii = total - pro_titleii - anti_titleii

    context = {
        'total_comments': s.count(),
        'title_ii': {
            'pro': float(pro_titleii) / total * 100,
            'anti': float(anti_titleii) / total * 100,
            'unknown': float(unknown_titleii) / total * 100
        }
    }
    a = A('terms', field='analysis.source.keyword', size=25)
    s.aggs.bucket('sources', a)
    response = s.execute()
    context['sources'] = []
    for source in response.aggregations.sources.buckets:
        if source.key == 'unknown':
            continue

        context['sources'].append({
            'key': source.key,
            'count': source.doc_count,
            'name': SOURCE_MAP.get(source.key, {}).get('name'),
            'url': SOURCE_MAP.get(source.key, {}).get('url')
        })

        # print(source.key, source.doc_count)
    # context['sources'] = s.aggs['sources']

    return render(request, 'index.html', context)

def sources(request):
    s = Search(using=es, index='fcc-comments')
    
    a = A('terms', field='analysis.source.keyword', size=50)
    s.aggs.bucket('sources', a)
    response = s.execute()
    
    context = { 'sources': [] }
    
    for source in response.aggregations.sources.buckets:
        context['sources'].append({
            'key': source.key,
            'count': source.doc_count,
            'name': SOURCE_MAP.get(source.key, {}).get('name'),
            'url': SOURCE_MAP.get(source.key, {}).get('url')
        })
    
    return render(request, 'sources.html', context)
    

def browse(request, sentiment=None, group=None):

    s = Search(using=es, index="fcc-comments")
    description = None

    s.query = FunctionScore(
        query=s.query, functions=[SF('random_score', seed=int(time.time()))]
    )

    if group:
        source = group
        s = s.filter('terms', **{'analysis.source.keyword': [source]})
        description = SOURCE_MAP.get(source, {}).get('name') or source
        details = SOURCE_MAP.get(source, {}).get('details') or ""
        url = SOURCE_MAP.get(source, {}).get('url') or ""

    elif sentiment:
        title_ii = sentiment
        if title_ii == 'pro':
            s = s.filter('terms', **{'analysis.titleii': [True]})
            description = "Pro Title II"
        elif title_ii == 'anti':
            description = 'Anti Title II'
            s = s.filter('terms', **{'analysis.titleii': [False]})
        elif title_ii == 'unknown':
            description = 'Uncategorized'
            s = s.exclude('exists', field='analysis.titleii')
        details, url = "", None
    
    s.aggs.bucket("date", A('date_histogram', field='date_submission', interval='month'))
    s.aggs.bucket('address', A('terms', field='analysis.fulladdress'))
    s.aggs.bucket('email_domain', A('terms', field='analysis.throwawayemail'))
    s.aggs.bucket('site', A('terms', field='analysis.onsite'))
    s.aggs.bucket('ingestion', A('terms', field='analysis.ingestion_method.keyword'))
    s.aggs.bucket('email_confirmation', A('filters', filters={
        'true': {'term': {'emailConfirmation': 'true'}},
        'false': {'term': {'emailConfirmation': 'false'}}
    }))

    # s.aggs.bucket('unique_emails', A('cardinality', field='contact_email.raw'))


    stats = OrderedDict({
        'Comment Form': {
            'On-site': 0,
            'Off-site': 0
        },
        'Throwaway Email': {
            'True': 0,
            'False': 0
        },
        'Address': {
            'Full Address': 0,
            'Partial Address': 0,
        },
        'Email Confirmation': {
            'True': 0,
            'False': 0,
            'Missing': 0
        },
        'Filing Method': {
            'API': 0,
            'Spreadsheet': 0,
            'Direct': 0
        },
        'Filing Dates': OrderedDict({
            
        })
    })

    response = s[:50].execute()
    total = s.count()

    for bucket in response.aggregations.date.buckets:
        d = datetime.fromtimestamp((bucket.key/1000.) + 14400)
        title = "%s/17 - %s" % (d.strftime("%m"), d.strftime("%B"))
        stats['Filing Dates'][title] = bucket.doc_count

    for bucket in response.aggregations.address.buckets:
        if bucket.key == 1:
            stats['Address']['Full Address'] = bucket.doc_count
        elif bucket.key == 0:
            stats['Address']['Partial Address'] = bucket.doc_count

    for bucket in response.aggregations.email_domain.buckets:
        if bucket.key == 1:
            stats['Throwaway Email']['True'] = bucket.doc_count
        elif bucket.key == 0:
            stats['Throwaway Email']['False'] = bucket.doc_count

    for bucket in response.aggregations.ingestion.buckets:
        if bucket.key == "api":
            stats['Filing Method']['API'] = bucket.doc_count
        elif bucket.key == "csv":
            stats['Filing Method']['Spreadsheet'] = bucket.doc_count
        elif bucket.key == "direct":
            stats['Filing Method']['Direct'] = bucket.doc_count


    for bucket in response.aggregations.site.buckets:
        if bucket.key == 1:
            stats['Comment Form']['On-site'] = bucket.doc_count
        elif bucket.key == 0:
            stats['Comment Form']['Off-site'] = bucket.doc_count

    # stats['Emails']['Unique'] = response.aggregations.unique_emails.value

    for bucket, value in response.aggs.email_confirmation.to_dict()['buckets'].items():
        if bucket == 'true':
            stats['Email Confirmation']['True'] = value['doc_count']
        elif bucket == 'false':
            stats['Email Confirmation']['False'] = value['doc_count']
    stats['Email Confirmation']['Missing'] = (
        total - stats['Email Confirmation']['True'] - stats['Email Confirmation']['False']
    )

    context = {
        'description': description,
        'details': details,
        'url': url,
        'stats': stats,
        'results': response,
        'comment_count': total
    }

    return render(request, 'listing.html', context)
