from django.db import models
from django.conf import settings
import uuid
from decimal import Decimal


class TransactionCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, blank=True)
    is_system = models.BooleanField(default=True)
    keywords = models.JSONField(default=list, blank=True, help_text="Keywords for auto-categorization")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'transaction_categories'
        verbose_name_plural = 'Transaction categories'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('debit', 'Debit'),
        ('credit', 'Credit'),
        ('transfer', 'Transfer'),
        ('refund', 'Refund'),
        ('fee', 'Fee'),
        ('interest', 'Interest'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('posted', 'Posted'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    account = models.ForeignKey('core.FinancialAccount', on_delete=models.CASCADE, related_name='transactions')
    plaid_transaction_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, default='debit')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='posted')
    
    merchant_name = models.CharField(max_length=200, blank=True)
    merchant_category = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    
    category = models.ForeignKey(TransactionCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    subcategory = models.CharField(max_length=100, blank=True)
    is_recurring = models.BooleanField(default=False)
    recurring_group_id = models.UUIDField(null=True, blank=True)
    
    date = models.DateField()
    posted_date = models.DateField(null=True, blank=True)
    
    location = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    needs_review = models.BooleanField(default=False)
    user_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'transactions'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'category']),
            models.Index(fields=['user', 'merchant_name']),
            models.Index(fields=['account', 'date']),
            models.Index(fields=['recurring_group_id']),
        ]
    
    def __str__(self):
        return f"{self.date} - {self.merchant_name or self.description} - {self.amount}"
    
    @property
    def is_expense(self):
        return self.amount < 0 or self.transaction_type == 'debit'
    
    @property
    def abs_amount(self):
        return abs(self.amount)


class Receipt(models.Model):
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('manual_review', 'Manual Review'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='receipts')
    transaction = models.OneToOneField(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='receipt')
    
    image = models.ImageField(upload_to='receipts/%Y/%m/%d/')
    original_filename = models.CharField(max_length=255)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
    
    extracted_text = models.TextField(blank=True)
    extracted_data = models.JSONField(default=dict, blank=True)
    
    merchant_name = models.CharField(max_length=200, blank=True)
    merchant_address = models.TextField(blank=True)
    date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    tip_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    items = models.JSONField(default=list, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)
    
    confidence_score = models.FloatField(default=0.0)
    processing_error = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'receipts'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Receipt {self.id} - {self.merchant_name or 'Unknown'}"


class TransactionImport(models.Model):
    SOURCE_CHOICES = [
        ('csv', 'CSV Upload'),
        ('plaid', 'Plaid'),
        ('manual', 'Manual Entry'),
        ('api', 'Bank API'),
        ('receipt', 'Receipt OCR'),
        ('txt', 'Text File'),
        ('pdf', 'PDF Document'),
        ('docx', 'Word Document'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partial'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='imports')
    account = models.ForeignKey('core.FinancialAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='imports')
    
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_rows = models.PositiveIntegerField(default=0)
    imported_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'transaction_imports'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Import {self.id} - {self.source} - {self.status}"


class MerchantCache(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    normalized_name = models.CharField(max_length=200, db_index=True)
    category = models.ForeignKey(TransactionCategory, on_delete=models.SET_NULL, null=True, blank=True)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    logo_url = models.URLField(blank=True)
    confidence = models.FloatField(default=0.0)
    lookup_count = models.PositiveIntegerField(default=0)
    last_looked_up = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'merchant_cache'
        ordering = ['-lookup_count']
    
    def __str__(self):
        return self.name