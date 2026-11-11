"""
URL configuration for projectpos project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from api import views as api_views

urlpatterns = [
    path('admin/', admin.site.urls),
    # Hosted account/access UI (for server customers)
    path('account/signup/', api_views.hosted_signup, name='hosted-signup'),
    path('account/login/', api_views.hosted_login, name='hosted-login'),
    path('account/logout/', api_views.hosted_logout, name='hosted-logout'),
    path('account/', api_views.hosted_dashboard, name='hosted-dashboard'),
    # DRF API
    path('api/v1/', include('api.urls')),
    path('api-auth/', include('rest_framework.urls')),
]

