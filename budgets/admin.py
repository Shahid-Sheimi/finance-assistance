from django.contrib import admin
from .models import Budget, BudgetAlert


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ['user', 'name', 'category', 'amount', 'period', 'alert_threshold', 'is_active', 'start_date', 'end_date']
    list_filter = ['period', 'is_active', 'alert_enabled', 'rollover_enabled', 'category']
    search_fields = ['user__email', 'name', 'category__name']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'start_date'


@admin.register(BudgetAlert)
class BudgetAlertAdmin(admin.ModelAdmin):
    list_display = ['budget', 'alert_type', 'percentage', 'amount_spent', 'amount_budgeted', 'is_read', 'is_dismissed', 'created_at']
    list_filter = ['alert_type', 'is_read', 'is_dismissed']
    search_fields = ['budget__name', 'budget__user__email', 'message']
    readonly_fields = ['created_at', 'read_at']
    ordering = ['-created_at']