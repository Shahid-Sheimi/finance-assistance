from rest_framework import serializers
from .models import FinancialSummary, SpendingInsight, SavingsRecommendation, MerchantEnrichment, CashFlowProjection
from transactions.serializers import TransactionCategorySerializer
from budgets.serializers import BudgetSerializer
from assistant.serializers import SubscriptionSerializer


class FinancialSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialSummary
        fields = [
            'id', 'period', 'period_start', 'period_end',
            'total_income', 'total_expenses', 'net_savings', 'savings_rate',
            'top_categories', 'top_merchants', 'category_breakdown', 'monthly_trend',
            'largest_expense', 'largest_income',
            'transaction_count', 'unique_merchants', 'generated_at'
        ]
        read_only_fields = ['id', 'generated_at']


class SpendingInsightSerializer(serializers.ModelSerializer):
    related_budgets_detail = BudgetSerializer(source='related_budgets', many=True, read_only=True)
    related_subscriptions_detail = SubscriptionSerializer(source='related_subscriptions', many=True, read_only=True)
    
    class Meta:
        model = SpendingInsight
        fields = [
            'id', 'insight_type', 'priority', 'title', 'description',
            'actionable_advice', 'supporting_data', 'related_budgets', 'related_budgets_detail',
            'related_subscriptions', 'related_subscriptions_detail',
            'is_read', 'is_dismissed', 'is_actioned',
            'valid_from', 'valid_until', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SavingsRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavingsRecommendation
        fields = [
            'id', 'category', 'title', 'description', 'estimated_monthly_savings',
            'confidence', 'action_steps', 'supporting_data',
            'is_implemented', 'implemented_at', 'user_feedback',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'implemented_at']


class SavingsRecommendationActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavingsRecommendation
        fields = ['is_implemented', 'user_feedback']


class MerchantEnrichmentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = MerchantEnrichment
        fields = [
            'id', 'merchant_name', 'normalized_name', 'category', 'category_name',
            'website', 'description', 'logo_url', 'phone', 'address', 'business_type',
            'is_subscription_service', 'subscription_pricing',
            'confidence', 'source', 'lookup_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'lookup_count']


class CashFlowProjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashFlowProjection
        fields = [
            'id', 'projection_date', 'projected_income', 'projected_expenses',
            'projected_balance', 'confidence_interval_low', 'confidence_interval_high',
            'assumptions', 'model_version', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']