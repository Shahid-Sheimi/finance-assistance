from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FinancialSummaryViewSet, SpendingInsightViewSet,
    SavingsRecommendationViewSet, MerchantEnrichmentViewSet, CashFlowProjectionViewSet
)

router = DefaultRouter()
router.register(r'summaries', FinancialSummaryViewSet, basename='financialsummary')
router.register(r'insights', SpendingInsightViewSet, basename='spendinginsight')
router.register(r'recommendations', SavingsRecommendationViewSet, basename='savingsrecommendation')
router.register(r'merchants', MerchantEnrichmentViewSet, basename='merchantenrichment')
router.register(r'projections', CashFlowProjectionViewSet, basename='cashflowprojection')

urlpatterns = router.urls