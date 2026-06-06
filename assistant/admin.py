from django.contrib import admin
from .models import Conversation, Message, AssistantTool, AssistantAction, Subscription, Anomaly


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'title', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__email', 'title']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-updated_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'role', 'content_preview', 'tokens_used', 'model_used', 'created_at']
    list_filter = ['role', 'model_used']
    search_fields = ['conversation__user__email', 'content']
    readonly_fields = ['created_at', 'tokens_used', 'model_used', 'tool_calls', 'tool_results']
    ordering = ['-created_at']
    
    def content_preview(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_preview.short_description = 'Content'


@admin.register(AssistantTool)
class AssistantToolAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'requires_auth', 'created_at', 'updated_at']
    list_filter = ['is_active', 'requires_auth']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(AssistantAction)
class AssistantActionAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'tool', 'status', 'duration_ms', 'started_at']
    list_filter = ['status', 'tool']
    search_fields = ['conversation__user__email', 'tool__name', 'error']
    readonly_fields = ['started_at', 'completed_at', 'duration_ms', 'input_data', 'output_data', 'error']
    ordering = ['-started_at']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'merchant_name', 'amount', 'currency', 'billing_cycle', 'status', 'confidence', 'is_user_confirmed', 'next_billing_date']
    list_filter = ['status', 'billing_cycle', 'is_user_confirmed', 'detection_method']
    search_fields = ['user__email', 'merchant_name', 'normalized_merchant']
    readonly_fields = ['created_at', 'updated_at', 'confidence']
    date_hierarchy = 'created_at'


@admin.register(Anomaly)
class AnomalyAdmin(admin.ModelAdmin):
    list_display = ['user', 'transaction', 'anomaly_type', 'severity', 'title', 'confidence', 'is_reviewed', 'is_false_positive', 'created_at']
    list_filter = ['anomaly_type', 'severity', 'is_reviewed', 'is_false_positive']
    search_fields = ['user__email', 'title', 'description', 'transaction__merchant_name']
    readonly_fields = ['created_at', 'reviewed_at', 'confidence', 'expected_value', 'actual_value']
    ordering = ['-created_at']