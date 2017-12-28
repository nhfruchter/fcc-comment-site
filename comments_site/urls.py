from django.conf import settings
from django.conf.urls import url
from django.conf.urls.static import static
from django.views.generic import TemplateView

from .core.views import index, browse, sources

urlpatterns = [
    # url(r'^admin/', admin.site.urls),
    url(r'^$', index),
    url(r'^browse/?$', browse),
    url(r'^sources/?$', sources),
    url(r'^about', 
        TemplateView.as_view(template_name='about.html'),
        name='about'),
    url(r'^credits', 
        TemplateView.as_view(template_name='credits.html'),
        name='credits'),
    url(r'^visualization', 
        TemplateView.as_view(template_name='visualization.html'),
        name='visualization'),
    
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

