from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'stores', views.StoreViewSet, basename='store')
router.register(r'memberships', views.StoreMembershipViewSet, basename='membership')
router.register(r'devices', views.DeviceViewSet, basename='device')
router.register(r'products', views.ProductViewSet, basename='product')
router.register(r'custom-columns', views.CustomColumnViewSet, basename='custom-column')
router.register(r'sales', views.SaleViewSet, basename='sale')
router.register(r'udhar', views.UdharViewSet, basename='udhar')
router.register(r'discount-rules', views.DiscountRuleViewSet, basename='discount-rule')
router.register(r'settings', views.StoreSettingViewSet, basename='store-setting')

urlpatterns = [
    path('', views.ApiRootView.as_view(), name='api-root'),
    path('auth/signup/', views.SignupAPIView.as_view(), name='api-signup'),
    path('auth/login/', views.LoginAPIView.as_view(), name='api-login'),
    path('auth/me/', views.MeAPIView.as_view(), name='api-me'),
    path('devices/register/', views.DeviceRegisterAPIView.as_view(), name='api-device-register'),
    path('sync/', views.SyncAPIView.as_view(), name='api-sync'),
    path('sync/pull/', views.SyncPullAPIView.as_view(), name='api-sync-pull'),
    path('sync/push/', views.SyncPushAPIView.as_view(), name='api-sync-push'),
    path('', include(router.urls)),
]
