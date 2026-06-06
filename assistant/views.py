from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import json
import logging

from .models import Conversation, Message, AssistantTool, AssistantAction, Subscription, Anomaly
from .serializers import (
    ConversationSerializer, ConversationCreateSerializer,
    MessageSerializer, MessageCreateSerializer,
    AssistantToolSerializer, AssistantActionSerializer,
    SubscriptionSerializer, SubscriptionUpdateSerializer,
    AnomalySerializer, AnomalyReviewSerializer
)
from transactions.models import Transaction, TransactionCategory
from budgets.models import Budget
from insights.models import SpendingInsight, SavingsRecommendation, MerchantEnrichment
from core.models import UserContext, UserPreference

logger = logging.getLogger(__name__)


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).prefetch_related('messages')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ConversationCreateSerializer
        return ConversationSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Send a message and get assistant response"""
        conversation = self.get_object()
        content = request.data.get('content')
        metadata = request.data.get('metadata', {})
        
        if not content:
            return Response({'error': 'content required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create user message
        user_message = Message.objects.create(
            conversation=conversation,
            role='user',
            content=content,
            metadata=metadata
        )
        
        # Process with assistant (async with sync fallback)
        from .tasks import process_assistant_message
        try:
            process_assistant_message.delay(str(conversation.id), str(user_message.id))
        except Exception:
            process_assistant_message(str(conversation.id), str(user_message.id))
        
        return Response(MessageSerializer(user_message).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Get all messages for a conversation"""
        conversation = self.get_object()
        messages = conversation.messages.all()
        return Response(MessageSerializer(messages, many=True).data)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get or create active conversation"""
        conversation = Conversation.objects.filter(user=request.user, is_active=True).first()
        if not conversation:
            conversation = Conversation.objects.create(user=request.user, title='New Conversation')
        return Response(ConversationSerializer(conversation).data)


class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Message.objects.filter(conversation__user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return MessageCreateSerializer
        return MessageSerializer


class AssistantToolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AssistantTool.objects.filter(is_active=True)
    serializer_class = AssistantToolSerializer
    permission_classes = [permissions.IsAuthenticated]


class SubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user).select_related('category').prefetch_related('transactions')
    
    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return SubscriptionUpdateSerializer
        return SubscriptionSerializer
    
    @action(detail=False, methods=['post'])
    def detect(self, request):
        """Trigger subscription detection"""
        from .tasks import detect_subscriptions
        detect_subscriptions.delay(str(request.user.id))
        return Response({'status': 'detection queued'})
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """User confirms a detected subscription"""
        subscription = self.get_object()
        subscription.is_user_confirmed = True
        subscription.status = request.data.get('status', 'active')
        subscription.save()
        return Response(SubscriptionSerializer(subscription).data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """User rejects a detected subscription"""
        subscription = self.get_object()
        subscription.is_user_confirmed = True
        subscription.status = 'cancelled'
        subscription.save()
        return Response(SubscriptionSerializer(subscription).data)
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming subscription payments"""
        days = int(request.query_params.get('days', 30))
        end_date = date.today() + timedelta(days=days)
        
        subscriptions = self.get_queryset().filter(
            status='active',
            next_billing_date__lte=end_date,
            next_billing_date__gte=date.today()
        ).order_by('next_billing_date')
        
        return Response(SubscriptionSerializer(subscriptions, many=True).data)
    
    @action(detail=False, methods=['get'])
    def total_monthly(self, request):
        """Get total monthly subscription cost"""
        subscriptions = self.get_queryset().filter(status='active', is_user_confirmed=True)
        
        monthly_total = 0
        for sub in subscriptions:
            if sub.billing_cycle == 'weekly':
                monthly_total += float(sub.amount) * 4.33
            elif sub.billing_cycle == 'monthly':
                monthly_total += float(sub.amount)
            elif sub.billing_cycle == 'quarterly':
                monthly_total += float(sub.amount) / 3
            elif sub.billing_cycle == 'yearly':
                monthly_total += float(sub.amount) / 12
        
        return Response({'monthly_total': round(monthly_total, 2), 'count': subscriptions.count()})


class AnomalyViewSet(viewsets.ModelViewSet):
    serializer_class = AnomalySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Anomaly.objects.filter(user=self.request.user).select_related('transaction', 'transaction__category')
    
    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return AnomalyReviewSerializer
        return AnomalySerializer
    
    @action(detail=False, methods=['post'])
    def detect(self, request):
        """Trigger anomaly detection"""
        from .tasks import detect_anomalies
        detect_anomalies.delay(str(request.user.id))
        return Response({'status': 'detection queued'})
    
    @action(detail=False, methods=['get'])
    def unreviewed(self, request):
        """Get unreviewed anomalies"""
        anomalies = self.get_queryset().filter(is_reviewed=False, is_false_positive=False)
        return Response(AnomalySerializer(anomalies, many=True).data)
    
    @action(detail=True, methods=['post'])
    def mark_false_positive(self, request, pk=None):
        anomaly = self.get_object()
        anomaly.is_reviewed = True
        anomaly.is_false_positive = True
        anomaly.user_feedback = request.data.get('feedback', '')
        anomaly.reviewed_at = timezone.now()
        anomaly.save()
        return Response(AnomalySerializer(anomaly).data)
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        anomaly = self.get_object()
        anomaly.is_reviewed = True
        anomaly.is_false_positive = False
        anomaly.user_feedback = request.data.get('feedback', '')
        anomaly.reviewed_at = timezone.now()
        anomaly.save()
        return Response(AnomalySerializer(anomaly).data)


class AssistantActionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AssistantActionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return AssistantAction.objects.filter(conversation__user=self.request.user)