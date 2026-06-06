from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TransactionCategoryViewSet, TransactionViewSet, ReceiptViewSet,
    TransactionImportViewSet, MerchantCacheViewSet, mock_bank_transactions
)

router = DefaultRouter()
router.register(r'categories', TransactionCategoryViewSet, basename='transactioncategory')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'receipts', ReceiptViewSet, basename='receipt')
router.register(r'imports', TransactionImportViewSet, basename='transactionimport')
router.register(r'merchants', MerchantCacheViewSet, basename='merchantcache')

urlpatterns = [
    path('mock-bank/transactions/', mock_bank_transactions, name='mock-bank-transactions'),
] + router.urls