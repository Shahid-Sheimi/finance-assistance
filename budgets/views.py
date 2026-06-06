from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import date
from dateutil.relativedelta import relativedelta

from .models import Budget, BudgetAlert
from .serializers import BudgetSerializer, BudgetCreateSerializer, BudgetAlertSerializer
from transactions.models import Transaction


class BudgetViewSet(viewsets.ModelViewSet):
    serializer_class = BudgetSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Budget.objects.filter(user=self.request.user).select_related('category')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return BudgetCreateSerializer
        return BudgetSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Get current budget status with spending"""
        budget = self.get_object()
        reference_date = request.query_params.get('date')
        if reference_date:
            reference_date = date.fromisoformat(reference_date)
        else:
            reference_date = date.today()
        
        spent = budget.get_spent_amount(reference_date)
        remaining = budget.get_remaining_amount(reference_date)
        progress = budget.get_progress_percentage(reference_date)
        is_over = budget.is_over_budget(reference_date)
        should_alert = budget.should_alert(reference_date)
        period_start = budget.get_period_start(reference_date)
        period_end = budget.get_period_end(reference_date)
        
        # Get transactions in this budget period
        transactions = Transaction.objects.filter(
            user=request.user,
            category=budget.category,
            date__gte=period_start,
            date__lte=period_end,
            transaction_type='debit'
        )
        if budget.subcategories:
            transactions = transactions.filter(subcategory__in=budget.subcategories)
        
        return Response({
            'budget': BudgetSerializer(budget).data,
            'period': {'start': period_start, 'end': period_end},
            'spent': str(spent),
            'remaining': str(remaining),
            'progress_percentage': progress,
            'is_over_budget': is_over,
            'should_alert': should_alert,
            'transaction_count': transactions.count(),
            'transactions': transactions.values('id', 'date', 'merchant_name', 'amount', 'subcategory')[:20]
        })
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get all budgets with current status"""
        reference_date = request.query_params.get('date')
        if reference_date:
            reference_date = date.fromisoformat(reference_date)
        else:
            reference_date = date.today()
        
        budgets = self.get_queryset().filter(is_active=True)
        result = []
        
        for budget in budgets:
            spent = budget.get_spent_amount(reference_date)
            remaining = budget.get_remaining_amount(reference_date)
            progress = budget.get_progress_percentage(reference_date)
            is_over = budget.is_over_budget(reference_date)
            should_alert = budget.should_alert(reference_date)
            
            result.append({
                'id': str(budget.id),
                'name': budget.name,
                'category': budget.category.name,
                'category_color': budget.category.color,
                'amount': str(budget.amount),
                'spent': str(spent),
                'remaining': str(remaining),
                'progress_percentage': progress,
                'is_over_budget': is_over,
                'should_alert': should_alert,
                'period': budget.period,
            })
        
        # Sort: over budget first, then by progress
        result.sort(key=lambda x: (not x['is_over_budget'], -x['progress_percentage']))
        
        return Response(result)
    
    @action(detail=False, methods=['post'])
    def check_alerts(self, request):
        """Check all budgets and create alerts if needed"""
        reference_date = request.query_params.get('date')
        if reference_date:
            reference_date = date.fromisoformat(reference_date)
        else:
            reference_date = date.today()
        
        budgets = self.get_queryset().filter(is_active=True, alert_enabled=True)
        alerts_created = 0
        
        for budget in budgets:
            if budget.should_alert(reference_date):
                # Check if alert already exists for this period
                period_start = budget.get_period_start(reference_date)
                existing = BudgetAlert.objects.filter(
                    budget=budget,
                    created_at__date__gte=period_start
                ).exists()
                
                if not existing:
                    progress = budget.get_progress_percentage(reference_date)
                    spent = budget.get_spent_amount(reference_date)
                    
                    if progress >= 100:
                        alert_type = 'over_budget'
                        message = f"Budget '{budget.name}' is over budget! Spent ${spent} of ${budget.amount}"
                    else:
                        alert_type = 'threshold'
                        message = f"Budget '{budget.name}' has reached {budget.alert_threshold}% (${spent} of ${budget.amount})"
                    
                    BudgetAlert.objects.create(
                        user=request.user,
                        budget=budget,
                        alert_type=alert_type,
                        message=message,
                        percentage=progress,
                        amount_spent=spent,
                        amount_budgeted=budget.amount
                    )
                    alerts_created += 1
        
        return Response({'alerts_created': alerts_created})


class BudgetAlertViewSet(viewsets.ModelViewSet):
    serializer_class = BudgetAlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return BudgetAlert.objects.filter(user=self.request.user).select_related('budget', 'budget__category')
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        alert = self.get_object()
        alert.is_read = True
        alert.read_at = timezone.now()
        alert.save()
        return Response(BudgetAlertSerializer(alert).data)
    
    @action(detail=True, methods=['post'])
    def dismiss(self, request, pk=None):
        alert = self.get_object()
        alert.is_dismissed = True
        alert.save()
        return Response(BudgetAlertSerializer(alert).data)
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({'status': 'all marked read'})