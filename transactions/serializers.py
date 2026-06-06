from rest_framework import serializers
from .models import TransactionCategory, Transaction, Receipt, TransactionImport, MerchantCache


class TransactionCategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = TransactionCategory
        fields = ['id', 'name', 'parent', 'icon', 'color', 'is_system', 'keywords', 'children']
        read_only_fields = ['id', 'created_at']
    
    def get_children(self, obj):
        children = obj.children.all()
        if children:
            return TransactionCategorySerializer(children, many=True).data
        return []


class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'account', 'account_name', 'plaid_transaction_id',
            'amount', 'currency', 'transaction_type', 'status',
            'merchant_name', 'merchant_category', 'description',
            'category', 'category_name', 'subcategory', 'is_recurring', 'recurring_group_id',
            'date', 'posted_date', 'location', 'metadata',
            'needs_review', 'user_notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'plaid_transaction_id']


class TransactionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'account', 'amount', 'currency', 'transaction_type', 'status',
            'merchant_name', 'merchant_category', 'description',
            'category', 'subcategory', 'is_recurring',
            'date', 'posted_date', 'location', 'metadata', 'user_notes'
        ]


class TransactionListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_color = serializers.CharField(source='category.color', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'date', 'merchant_name', 'amount', 'currency',
            'transaction_type', 'category', 'category_name', 'category_color',
            'subcategory', 'is_recurring', 'status'
        ]


class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = [
            'id', 'transaction', 'image', 'original_filename',
            'status', 'extracted_text', 'extracted_data',
            'merchant_name', 'merchant_address', 'date', 'total_amount',
            'tax_amount', 'tip_amount', 'currency', 'items', 'payment_method',
            'confidence_score', 'processing_error', 'created_at', 'updated_at', 'processed_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'processed_at', 'extracted_text', 'extracted_data', 'confidence_score']


class ReceiptUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = ['image', 'original_filename']


class TransactionImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionImport
        fields = [
            'id', 'account', 'source', 'filename', 'file_size',
            'status', 'total_rows', 'imported_count', 'duplicate_count',
            'error_count', 'errors', 'started_at', 'completed_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'started_at', 'completed_at', 'status', 'total_rows', 'imported_count', 'duplicate_count', 'error_count', 'errors']


class MerchantCacheSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = MerchantCache
        fields = ['id', 'name', 'normalized_name', 'category', 'category_name', 'website', 'phone', 'address', 'logo_url', 'confidence', 'lookup_count', 'last_looked_up', 'created_at']
        read_only_fields = ['id', 'created_at', 'last_looked_up', 'lookup_count']