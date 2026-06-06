from django.db import models
from django.conf import settings
import uuid
from decimal import Decimal


class FinancialSummary(models.Model):
    PERIOD_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='financial_summaries')
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()
    
    total_income = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_savings = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    savings_rate = models.FloatField(default=0)
    
    top_categories = models.JSONField(default=list, blank=True)
    top_merchants = models.JSONField(default=list, blank=True)
    category_breakdown = models.JSONField(default=dict, blank=True)
    monthly_trend = models.JSONField(default=list, blank=True)
    
    largest_expense = models.JSONField(default=dict, blank=True)
    largest_income = models.JSONField(default=dict, blank=True)
    
    transaction_count = models.PositiveIntegerField(default=0)
    unique_merchants = models.PositiveIntegerField(default=0)
    
    generated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'financial_summaries'
        ordering = ['-period_start']
        unique_together = ['user', 'period', 'period_start']
    
    def __str__(self):
        return f"{self.user.email}: {self.period} {self.period_start} - {self.period_end}"


class SpendingInsight(models.Model):
    INSIGHT_TYPES = [
        ('spending_increase', 'Spending Increase'),
        ('spending_decrease', 'Spending Decrease'),
        ('new_merchant', 'New Merchant'),
        ('category_trend', 'Category Trend'),
        ('subscription_found', 'Subscription Found'),
        ('budget_warning', 'Budget Warning'),
        ('anomaly_detected', 'Anomaly Detected'),
        ('savings_opportunity', 'Savings Opportunity'),
        ('recurring_pattern', 'Recurring Pattern'),
        ('income_change', 'Income Change'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='spending_insights')
    insight_type = models.CharField(max_length=30, choices=INSIGHT_TYPES)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    actionable_advice = models.TextField(blank=True)
    
    supporting_data = models.JSONField(default=dict, blank=True)
    related_transactions = models.ManyToManyField('transactions.Transaction', blank=True)
    related_budgets = models.ManyToManyField('budgets.Budget', blank=True)
    related_subscriptions = models.ManyToManyField('assistant.Subscription', blank=True)
    
    is_read = models.BooleanField(default=False)
    is_dismissed = models.BooleanField(default=False)
    is_actioned = models.BooleanField(default=False)
    
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'spending_insights'
        ordering = ['-priority', '-created_at']
    
    def __str__(self):
        return f"{self.get_insight_type_display()}: {self.title}"


class SavingsRecommendation(models.Model):
    CATEGORY_CHOICES = [
        ('subscriptions', 'Subscriptions'),
        ('dining', 'Dining & Entertainment'),
        ('shopping', 'Shopping'),
        ('transportation', 'Transportation'),
        ('utilities', 'Utilities & Bills'),
        ('groceries', 'Groceries'),
        ('fees', 'Bank Fees'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='savings_recommendations')
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    estimated_monthly_savings = models.DecimalField(max_digits=15, decimal_places=2)
    confidence = models.FloatField(default=0.0)
    
    action_steps = models.JSONField(default=list, blank=True)
    supporting_data = models.JSONField(default=dict, blank=True)
    
    is_implemented = models.BooleanField(default=False)
    implemented_at = models.DateTimeField(null=True, blank=True)
    user_feedback = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'savings_recommendations'
        ordering = ['-estimated_monthly_savings']
    
    def __str__(self):
        return f"{self.title} - ${self.estimated_monthly_savings}/mo"


class MerchantEnrichment(models.Model):
    merchant_name = models.CharField(max_length=200, db_index=True)
    normalized_name = models.CharField(max_length=200, db_index=True)
    
    category = models.ForeignKey('transactions.TransactionCategory', on_delete=models.SET_NULL, null=True, blank=True)
    website = models.URLField(blank=True)
    description = models.TextField(blank=True)
    logo_url = models.URLField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    business_type = models.CharField(max_length=100, blank=True)
    
    is_subscription_service = models.BooleanField(default=False)
    subscription_pricing = models.JSONField(default=dict, blank=True)
    
    confidence = models.FloatField(default=0.0)
    source = models.CharField(max_length=50, default='manual')
    lookup_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'merchant_enrichments'
        ordering = ['-lookup_count']
    
    def __str__(self):
        return self.merchant_name


class CashFlowProjection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cashflow_projections')
    
    projection_date = models.DateField()
    projected_income = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    projected_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    projected_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    confidence_interval_low = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    confidence_interval_high = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    assumptions = models.JSONField(default=dict, blank=True)
    model_version = models.CharField(max_length=50, default='v1')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'cashflow_projections'
        ordering = ['projection_date']
        unique_together = ['user', 'projection_date']
    
    def __str__(self):
        return f"{self.user.email}: {self.projection_date} - Balance: {self.projected_balance}"