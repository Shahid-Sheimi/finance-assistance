from rest_framework import serializers
from .models import Budget, BudgetAlert
from transactions.serializers import TransactionCategorySerializer


class BudgetSerializer(serializers.ModelSerializer):
    category_detail = TransactionCategorySerializer(source='category', read_only=True)
    spent_amount = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    is_over_budget = serializers.SerializerMethodField()
    period_start = serializers.SerializerMethodField()
    period_end = serializers.SerializerMethodField()
    
    class Meta:
        model = Budget
        fields = [
            'id', 'name', 'description', 'amount', 'currency', 'period',
            'custom_start_date', 'custom_end_date', 'category', 'category_detail',
            'subcategories', 'alert_threshold', 'alert_enabled', 'rollover_enabled',
            'is_active', 'start_date', 'end_date', 'created_at', 'updated_at',
            'spent_amount', 'remaining_amount', 'progress_percentage', 'is_over_budget',
            'period_start', 'period_end'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_spent_amount(self, obj):
        return str(obj.get_spent_amount())
    
    def get_remaining_amount(self, obj):
        return str(obj.get_remaining_amount())
    
    def get_progress_percentage(self, obj):
        return obj.get_progress_percentage()
    
    def get_is_over_budget(self, obj):
        return obj.is_over_budget()
    
    def get_period_start(self, obj):
        return obj.get_period_start()
    
    def get_period_end(self, obj):
        return obj.get_period_end()


class BudgetCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = [
            'name', 'description', 'amount', 'currency', 'period',
            'custom_start_date', 'custom_end_date', 'category', 'subcategories',
            'alert_threshold', 'alert_enabled', 'rollover_enabled',
            'is_active', 'start_date', 'end_date'
        ]


class BudgetAlertSerializer(serializers.ModelSerializer):
    budget_name = serializers.CharField(source='budget.name', read_only=True)
    
    class Meta:
        model = BudgetAlert
        fields = [
            'id', 'budget', 'budget_name', 'alert_type', 'message',
            'percentage', 'amount_spent', 'amount_budgeted',
            'is_read', 'is_dismissed', 'created_at', 'read_at'
        ]
        read_only_fields = ['id', 'created_at', 'read_at']