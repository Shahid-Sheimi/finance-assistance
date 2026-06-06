from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import logging

from .models import FinancialSummary, SpendingInsight, SavingsRecommendation, MerchantEnrichment, CashFlowProjection
from .serializers import (
    FinancialSummarySerializer, SpendingInsightSerializer,
    SavingsRecommendationSerializer, SavingsRecommendationActionSerializer,
    MerchantEnrichmentSerializer, CashFlowProjectionSerializer
)
from transactions.models import Transaction, TransactionCategory
from budgets.models import Budget
from assistant.models import Subscription

logger = logging.getLogger(__name__)


class FinancialSummaryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FinancialSummarySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return FinancialSummary.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def latest(self, request):
        """Get latest summary for each period"""
        summaries = {}
        for period_choice in FinancialSummary.PERIOD_CHOICES:
            period = period_choice[0]
            summary = self.get_queryset().filter(period=period).first()
            if summary:
                summaries[period] = FinancialSummarySerializer(summary).data
        return Response(summaries)
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Trigger summary generation"""
        from .tasks import generate_financial_summaries
        generate_financial_summaries.delay(str(request.user.id))
        return Response({'status': 'generation queued'})


class SpendingInsightViewSet(viewsets.ModelViewSet):
    serializer_class = SpendingInsightSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return SpendingInsight.objects.filter(user=self.request.user).prefetch_related(
            'related_budgets', 'related_subscriptions', 'related_transactions'
        )
    
    @action(detail=False, methods=['get'])
    def unread(self, request):
        """Get unread insights"""
        insights = self.get_queryset().filter(is_read=False, is_dismissed=False)
        return Response(SpendingInsightSerializer(insights, many=True).data)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        insight = self.get_object()
        insight.is_read = True
        insight.save()
        return Response(SpendingInsightSerializer(insight).data)
    
    @action(detail=True, methods=['post'])
    def dismiss(self, request, pk=None):
        insight = self.get_object()
        insight.is_dismissed = True
        insight.save()
        return Response(SpendingInsightSerializer(insight).data)
    
    @action(detail=True, methods=['post'])
    def action_taken(self, request, pk=None):
        insight = self.get_object()
        insight.is_actioned = True
        insight.save()
        return Response(SpendingInsightSerializer(insight).data)
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Trigger insight generation"""
        from .tasks import generate_spending_insights
        generate_spending_insights.delay(str(request.user.id))
        return Response({'status': 'generation queued'})


class SavingsRecommendationViewSet(viewsets.ModelViewSet):
    serializer_class = SavingsRecommendationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return SavingsRecommendation.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return SavingsRecommendationActionSerializer
        return SavingsRecommendationSerializer
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get non-implemented recommendations"""
        recs = self.get_queryset().filter(is_implemented=False)
        return Response(SavingsRecommendationSerializer(recs, many=True).data)
    
    @action(detail=True, methods=['post'])
    def implement(self, request, pk=None):
        rec = self.get_object()
        rec.is_implemented = True
        rec.implemented_at = timezone.now()
        rec.user_feedback = request.data.get('feedback', '')
        rec.save()
        return Response(SavingsRecommendationSerializer(rec).data)
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Trigger recommendation generation"""
        from .tasks import generate_savings_recommendations
        generate_savings_recommendations.delay(str(request.user.id))
        return Response({'status': 'generation queued'})


class MerchantEnrichmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MerchantEnrichmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return MerchantEnrichment.objects.all()
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q', '')
        if len(query) < 2:
            return Response([])
        
        merchants = MerchantEnrichment.objects.filter(
            Q(merchant_name__icontains=query) | Q(normalized_name__icontains=query)
        )[:10]
        return Response(MerchantEnrichmentSerializer(merchants, many=True).data)
    
    @action(detail=False, methods=['post'])
    def lookup(self, request):
        """Look up merchant info (calls external API if not cached)"""
        merchant_name = request.data.get('merchant_name')
        if not merchant_name:
            return Response({'error': 'merchant_name required'}, status=400)
        
        # Check cache first
        from insights.tasks import enrich_merchant
        enrich_merchant.delay(merchant_name)
        
        # Return cached if exists
        try:
            merchant = MerchantEnrichment.objects.get(normalized_name__iexact=merchant_name.strip().lower())
            return Response(MerchantEnrichmentSerializer(merchant).data)
        except MerchantEnrichment.DoesNotExist:
            return Response({'status': 'lookup queued', 'merchant_name': merchant_name})


class CashFlowProjectionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CashFlowProjectionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return CashFlowProjection.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming projections"""
        days = int(request.query_params.get('days', 90))
        end_date = date.today() + timedelta(days=days)
        
        projections = self.get_queryset().filter(
            projection_date__gte=date.today(),
            projection_date__lte=end_date
        ).order_by('projection_date')
        
        return Response(CashFlowProjectionSerializer(projections, many=True).data)
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Trigger projection generation"""
        from .tasks import generate_cashflow_projections
        generate_cashflow_projections.delay(str(request.user.id))
        return Response({'status': 'generation queued'})