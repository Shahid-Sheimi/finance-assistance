from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BudgetViewSet, BudgetAlertViewSet

router = DefaultRouter()
router.register(r'budgets', BudgetViewSet, basename='budget')
router.register(r'budget-alerts', BudgetAlertViewSet, basename='budgetalert')

urlpatterns = router.urls