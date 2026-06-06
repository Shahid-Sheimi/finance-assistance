from django.db import models
from django.conf import settings
import uuid
from decimal import Decimal


class Budget(models.Model):
    PERIOD_CHOICES = [
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('custom', 'Custom'),
    ]
    
    ALERT_THRESHOLDS = [
        (50, '50%'),
        (75, '75%'),
        (90, '90%'),
        (100, '100%'),
        (110, '110%'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='budgets')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES, default='monthly')
    custom_start_date = models.DateField(null=True, blank=True)
    custom_end_date = models.DateField(null=True, blank=True)
    
    category = models.ForeignKey('transactions.TransactionCategory', on_delete=models.CASCADE, related_name='budgets')
    subcategories = models.JSONField(default=list, blank=True)
    
    alert_threshold = models.IntegerField(choices=ALERT_THRESHOLDS, default=90)
    alert_enabled = models.BooleanField(default=True)
    rollover_enabled = models.BooleanField(default=False)
    
    is_active = models.BooleanField(default=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'budgets'
        ordering = ['-created_at']
        unique_together = ['user', 'category', 'period', 'start_date']
    
    def __str__(self):
        return f"{self.name} - {self.amount} {self.currency}/{self.get_period_display()}"
    
    def get_period_start(self, reference_date=None):
        from datetime import date
        from dateutil.relativedelta import relativedelta
        
        if reference_date is None:
            reference_date = date.today()
        
        if self.period == 'weekly':
            return reference_date - relativedelta(days=reference_date.weekday())
        elif self.period == 'monthly':
            return reference_date.replace(day=1)
        elif self.period == 'quarterly':
            quarter = (reference_date.month - 1) // 3 + 1
            return reference_date.replace(month=(quarter - 1) * 3 + 1, day=1)
        elif self.period == 'yearly':
            return reference_date.replace(month=1, day=1)
        elif self.period == 'custom':
            return self.custom_start_date or reference_date.replace(day=1)
        return reference_date.replace(day=1)
    
    def get_period_end(self, reference_date=None):
        from datetime import date
        from dateutil.relativedelta import relativedelta
        
        if reference_date is None:
            reference_date = date.today()
        
        period_start = self.get_period_start(reference_date)
        
        if self.period == 'weekly':
            return period_start + relativedelta(days=6)
        elif self.period == 'monthly':
            return period_start + relativedelta(months=1, days=-1)
        elif self.period == 'quarterly':
            return period_start + relativedelta(months=3, days=-1)
        elif self.period == 'yearly':
            return period_start + relativedelta(years=1, days=-1)
        elif self.period == 'custom':
            return self.custom_end_date or (period_start + relativedelta(months=1, days=-1))
        return period_start + relativedelta(months=1, days=-1)
    
    def get_spent_amount(self, reference_date=None):
        from django.db.models import Sum
        from transactions.models import Transaction
        
        period_start = self.get_period_start(reference_date)
        period_end = self.get_period_end(reference_date)
        
        queryset = Transaction.objects.filter(
            user=self.user,
            category=self.category,
            date__gte=period_start,
            date__lte=period_end,
            transaction_type='debit',
        )
        
        if self.subcategories:
            queryset = queryset.filter(subcategory__in=self.subcategories)
        
        result = queryset.aggregate(total=Sum('amount'))
        return abs(result['total'] or Decimal('0'))
    
    def get_remaining_amount(self, reference_date=None):
        spent = self.get_spent_amount(reference_date)
        return self.amount - spent
    
    def get_progress_percentage(self, reference_date=None):
        spent = self.get_spent_amount(reference_date)
        if self.amount == 0:
            return 0
        return min(100, float(spent / self.amount * 100))
    
    def is_over_budget(self, reference_date=None):
        return self.get_spent_amount(reference_date) > self.amount
    
    def should_alert(self, reference_date=None):
        if not self.alert_enabled:
            return False
        progress = self.get_progress_percentage(reference_date)
        return progress >= self.alert_threshold


class BudgetAlert(models.Model):
    ALERT_TYPES = [
        ('threshold', 'Threshold Reached'),
        ('over_budget', 'Over Budget'),
        ('projected_over', 'Projected Over Budget'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='budget_alerts')
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='alerts')
    
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    message = models.TextField()
    percentage = models.FloatField()
    amount_spent = models.DecimalField(max_digits=15, decimal_places=2)
    amount_budgeted = models.DecimalField(max_digits=15, decimal_places=2)
    
    is_read = models.BooleanField(default=False)
    is_dismissed = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'budget_alerts'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Alert: {self.budget.name} - {self.alert_type}"