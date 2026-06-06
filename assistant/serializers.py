from rest_framework import serializers
from .models import Conversation, Message, AssistantTool, AssistantAction, Subscription, Anomaly


class ConversationSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = ['id', 'title', 'is_active', 'context_summary', 'created_at', 'updated_at', 'message_count', 'last_message']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_message_count(self, obj):
        return obj.messages.count()
    
    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return {
                'content': last_msg.content[:100],
                'role': last_msg.role,
                'created_at': last_msg.created_at
            }
        return None


class ConversationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ['title']


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'role', 'content', 'tool_calls',
            'tool_results', 'metadata', 'tokens_used', 'model_used', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'tokens_used', 'model_used', 'tool_calls', 'tool_results']


class MessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['conversation', 'role', 'content', 'metadata']


class AssistantToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantTool
        fields = ['id', 'name', 'description', 'parameters_schema', 'is_active', 'requires_auth', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AssistantActionSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source='tool.name', read_only=True)
    
    class Meta:
        model = AssistantAction
        fields = [
            'id', 'conversation', 'message', 'tool', 'tool_name',
            'input_data', 'output_data', 'error', 'status',
            'started_at', 'completed_at', 'duration_ms'
        ]
        read_only_fields = ['id', 'started_at', 'completed_at', 'duration_ms']


class SubscriptionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    transaction_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Subscription
        fields = [
            'id', 'merchant_name', 'normalized_merchant', 'category', 'category_name',
            'amount', 'currency', 'billing_cycle', 'status',
            'start_date', 'next_billing_date', 'last_billing_date', 'end_date',
            'confidence', 'detection_method', 'transaction_count',
            'notes', 'is_user_confirmed', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'confidence', 'normalized_merchant']
    
    def get_transaction_count(self, obj):
        return obj.transactions.count()


class SubscriptionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ['status', 'billing_cycle', 'amount', 'currency', 'next_billing_date', 'end_date', 'notes', 'is_user_confirmed']


class AnomalySerializer(serializers.ModelSerializer):
    transaction_detail = serializers.SerializerMethodField()
    
    class Meta:
        model = Anomaly
        fields = [
            'id', 'transaction', 'transaction_detail', 'anomaly_type', 'severity',
            'title', 'description', 'expected_value', 'actual_value', 'confidence',
            'is_reviewed', 'is_false_positive', 'user_feedback', 'created_at', 'reviewed_at'
        ]
        read_only_fields = ['id', 'created_at', 'reviewed_at', 'confidence']
    
    def get_transaction_detail(self, obj):
        t = obj.transaction
        return {
            'id': str(t.id),
            'date': t.date,
            'merchant_name': t.merchant_name,
            'amount': str(t.amount),
            'category': t.category.name if t.category else None
        }


class AnomalyReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Anomaly
        fields = ['is_reviewed', 'is_false_positive', 'user_feedback']