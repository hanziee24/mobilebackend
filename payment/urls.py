from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaymentViewSet, RiderWalletViewSet, WithdrawalRequestViewSet

router = DefaultRouter()
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'wallets', RiderWalletViewSet, basename='wallet')
router.register(r'withdrawals', WithdrawalRequestViewSet, basename='withdrawal')

urlpatterns = [
    path('', include(router.urls)),
]
