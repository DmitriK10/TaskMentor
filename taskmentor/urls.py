from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from core.views import index

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('core/', include('core.urls')),
    path('', index, name='home'),
    # Service Worker
    path('sw.js', TemplateView.as_view(template_name='sw.js', content_type='application/javascript'), name='sw.js'),
]