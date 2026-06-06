from django.contrib import admin
from .models import FinancialSummary, SpendingInsight, SavingsRecommendation, MerchantEnrichment, CashFlowProjection


@admin.register(FinancialSummary)
class FinancialSummaryAdmin(admin.ModelAdmin):
    list_display = ['user', 'period', 'period_start', 'period_end', 'total_income', 'total_expenses', 'net_savings', 'savings_rate', 'transaction_count']
    list_filter = ['period', 'period_start']
    search_fields = ['user__email']
    readonly_fields = ['generated_at']
    date_hierarchy = 'period_start'
    ordering = ['-period_start']


@admin.register(SpendingInsight)
class SpendingInsightAdmin(admin.ModelAdmin):
    list_display = ['user', 'insight_type', 'priority', 'title', 'is_read', 'is_dismissed', 'is_actioned', 'created_at']
    list_filter = ['insight_type', 'priority', 'is_read', 'is_dismissed', 'is_actioned']
    search_fields = ['user__email', 'title', 'description']
    readonly_fields = ['created_at']
    ordering = ['-priority', '-created_at']


@admin.register(SavingsRecommendation)
class SavingsRecommendationAdmin(admin.ModelAdmin):
    list_display = ['user', 'category', 'title', 'estimated_monthly_savings', 'confidence', 'is_implemented', 'created_at']
    list_filter = ['category', 'is_implemented']
    search_fields = ['user__email', 'title', 'description']
    readonly_fields = ['created_at', 'updated_at', 'implemented_at']
    ordering = ['-estimated_monthly_savings']


@admin.register(MerchantEnrichment)
class MerchantEnrichmentAdmin(admin.ModelAdmin):
    list_display = ['merchant_name', 'normalized_name', 'category', 'business_type', 'is_subscription_service', 'confidence', 'lookup_count']
    list_filter = ['category', 'is_subscription_service', 'source']
    search_fields = ['merchant_name', 'normalized_name', 'website']
    readonly_fields = ['created_at', 'updated_at', 'lookup_count']
    ordering = ['-lookup_count']


@admin.register(CashFlowProjection)
class CashFlowProjectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'projection_date', 'projected_income', 'projected_expenses', 'projected_balance', 'model_version']
    list_filter = ['model_version']
    search_fields = ['user__email']
    readonly_fields = ['created_at']
    date_hierarchy = 'projection_date'
    ordering = ['projection_date']