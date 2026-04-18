from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DeliveryViewSet, NotificationViewSet, RatingViewSet, track_by_number, get_fee_config, update_fee_config, create_delivery_request, list_delivery_requests, accept_delivery_request, cancel_delivery_request, upload_gcash_proof
from .analytics import analytics_dashboard, predictive_analytics

router = DefaultRouter()
router.register(r'deliveries', DeliveryViewSet, basename='delivery')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'ratings', RatingViewSet, basename='rating')

urlpatterns = [
    path('', include(router.urls)),
    path('track/<str:tracking_number>/', track_by_number, name='track_by_number'),
    path('analytics/dashboard/', analytics_dashboard, name='analytics_dashboard'),
    path('analytics/predictive/', predictive_analytics, name='predictive_analytics'),
    path('settings/fee-config/', get_fee_config, name='get_fee_config'),
    path('settings/fee-config/update/', update_fee_config, name='update_fee_config'),
    path('delivery-requests/', list_delivery_requests, name='list_delivery_requests'),
    path('delivery-requests/create/', create_delivery_request, name='create_delivery_request'),
    path('delivery-requests/<int:request_id>/accept/', accept_delivery_request, name='accept_delivery_request'),
    path('delivery-requests/<int:request_id>/cancel/', cancel_delivery_request, name='cancel_delivery_request'),
    path('deliveries/<int:delivery_id>/gcash-proof/', upload_gcash_proof, name='upload_gcash_proof'),
]
