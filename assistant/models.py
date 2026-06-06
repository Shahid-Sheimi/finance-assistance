from django.db import models
from django.conf import settings
import uuid


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    context_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'conversations'
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.user.email}: {self.title or 'New Conversation'}"


class Message(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
        ('tool', 'Tool'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    
    tool_calls = models.JSONField(default=list, blank=True)
    tool_results = models.JSONField(default=list, blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    tokens_used = models.PositiveIntegerField(default=0)
    model_used = models.CharField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'messages'
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.conversation_id}: {self.role} - {self.content[:50]}"


class AssistantTool(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    parameters_schema = models.JSONField()
    is_active = models.BooleanField(default=True)
    requires_auth = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'assistant_tools'
    
    def __str__(self):
        return self.name


class AssistantAction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='actions')
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='actions')
    tool = models.ForeignKey(AssistantTool, on_delete=models.CASCADE, related_name='actions')
    
    input_data = models.JSONField()
    output_data = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'assistant_actions'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Action {self.tool.name} - {self.status}"


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('paused', 'Paused'),
        ('trial', 'Trial'),
        ('unknown', 'Unknown'),
    ]
    
    BILLING_CYCLES = [
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('irregular', 'Irregular'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    merchant_name = models.CharField(max_length=200)
    normalized_merchant = models.CharField(max_length=200)
    category = models.ForeignKey('transactions.TransactionCategory', on_delete=models.SET_NULL, null=True, blank=True)
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLES, default='monthly')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unknown')
    
    start_date = models.DateField(null=True, blank=True)
    next_billing_date = models.DateField(null=True, blank=True)
    last_billing_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    confidence = models.FloatField(default=0.0)
    detection_method = models.CharField(max_length=50, default='pattern')
    transactions = models.ManyToManyField('transactions.Transaction', related_name='subscription_matches', blank=True)
    
    notes = models.TextField(blank=True)
    is_user_confirmed = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subscriptions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.merchant_name} - {self.amount} {self.currency}/{self.get_billing_cycle_display()}"


class Anomaly(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    ANOMALY_TYPES = [
        ('unusual_amount', 'Unusual Amount'),
        ('unusual_merchant', 'Unusual Merchant'),
        ('unusual_category', 'Unusual Category'),
        ('unusual_time', 'Unusual Time'),
        ('duplicate_charge', 'Duplicate Charge'),
        ('subscription_change', 'Subscription Change'),
        ('velocity_spike', 'Velocity Spike'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='anomalies')
    transaction = models.ForeignKey('transactions.Transaction', on_delete=models.CASCADE, related_name='anomalies')
    
    anomaly_type = models.CharField(max_length=30, choices=ANOMALY_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    expected_value = models.JSONField(default=dict, blank=True)
    actual_value = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(default=0.0)
    
    is_reviewed = models.BooleanField(default=False)
    is_false_positive = models.BooleanField(default=False)
    user_feedback = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'anomalies'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_anomaly_type_display()}: {self.title} ({self.severity})"