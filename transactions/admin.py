from django.contrib import admin
from .models import TransactionCategory, Transaction, Receipt, TransactionImport, MerchantCache


@admin.register(TransactionCategory)
class TransactionCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'icon', 'color', 'is_system']
    list_filter = ['is_system', 'parent']
    search_fields = ['name']
    prepopulated_fields = {}


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'user', 'account', 'merchant_name', 'amount', 'category', 'transaction_type', 'status']
    list_filter = ['transaction_type', 'status', 'category', 'account__account_type', 'is_recurring', 'date']
    search_fields = ['user__email', 'merchant_name', 'description', 'plaid_transaction_id']
    readonly_fields = ['created_at', 'updated_at', 'plaid_transaction_id']
    date_hierarchy = 'date'
    ordering = ['-date', '-created_at']
    list_select_related = ['user', 'account', 'category']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'account', 'category')


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'merchant_name', 'date', 'total_amount', 'status', 'confidence_score', 'created_at']
    list_filter = ['status', 'currency']
    search_fields = ['user__email', 'merchant_name', 'original_filename']
    readonly_fields = ['created_at', 'updated_at', 'processed_at', 'extracted_text', 'extracted_data']
    date_hierarchy = 'created_at'


@admin.register(TransactionImport)
class TransactionImportAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'account', 'source', 'status', 'total_rows', 'imported_count', 'duplicate_count', 'error_count', 'created_at']
    list_filter = ['source', 'status']
    search_fields = ['user__email', 'filename']
    readonly_fields = ['created_at', 'started_at', 'completed_at', 'errors']
    ordering = ['-created_at']


@admin.register(MerchantCache)
class MerchantCacheAdmin(admin.ModelAdmin):
    list_display = ['name', 'normalized_name', 'category', 'confidence', 'lookup_count', 'last_looked_up']
    list_filter = ['category']
    search_fields = ['name', 'normalized_name']
    readonly_fields = ['created_at', 'last_looked_up', 'lookup_count']