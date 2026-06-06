from celery import shared_task
from django.utils import timezone
from django.db.models import Sum
from datetime import date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


@shared_task
def generate_financial_summaries(user_id):
    from django.contrib.auth import get_user_model
    from django.db.models import Sum
    from transactions.models import Transaction
    from .models import FinancialSummary
    
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return
    
    today = date.today()
    
    # Generate monthly summary
    period_start = today.replace(day=1)
    period_end = period_start + relativedelta(months=1, days=-1)
    
    transactions = Transaction.objects.filter(
        user=user,
        date__gte=period_start,
        date__lte=period_end
    )
    
    total_income = transactions.filter(transaction_type='credit').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    total_expenses = transactions.filter(transaction_type='debit').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    FinancialSummary.objects.update_or_create(
        user=user,
        period='monthly',
        period_start=period_start,
        defaults={
            'period_end': period_end,
            'total_income': total_income,
            'total_expenses': abs(total_expenses),
            'net_savings': total_income + total_expenses,
            'transaction_count': transactions.count(),
        }
    )


@shared_task
def generate_spending_insights(user_id):
    from django.contrib.auth import get_user_model
    from django.db.models import Sum
    from transactions.models import Transaction
    from assistant.models import Subscription, Anomaly
    from budgets.models import Budget
    from .models import SpendingInsight
    from datetime import date
    from dateutil.relativedelta import relativedelta

    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return

    today = date.today()
    current_start = today.replace(day=1)
    prev_start = current_start - relativedelta(months=1)
    prev_end = current_start - relativedelta(days=1)

    current = Transaction.objects.filter(
        user=user, transaction_type='debit', date__gte=current_start, date__lte=today
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    previous = Transaction.objects.filter(
        user=user, transaction_type='debit', date__gte=prev_start, date__lte=prev_end
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    current_abs = abs(float(current))
    previous_abs = abs(float(previous))

    if previous_abs > 0:
        change_pct = (current_abs - previous_abs) / previous_abs * 100
        if change_pct > 15:
            SpendingInsight.objects.update_or_create(
                user=user,
                insight_type='spending_increase',
                valid_from=current_start,
                defaults={
                    'title': f'Spending up {change_pct:.0f}% vs last month',
                    'description': f"You've spent ${current_abs:.2f} so far this month vs ${previous_abs:.2f} last month.",
                    'actionable_advice': 'Review your top categories to see where the increase came from.',
                    'priority': 'high' if change_pct > 30 else 'medium',
                    'supporting_data': {'change_percent': round(change_pct, 1)},
                }
            )

    for budget in Budget.objects.filter(user=user, is_active=True):
        if budget.should_alert():
            SpendingInsight.objects.update_or_create(
                user=user,
                insight_type='budget_warning',
                valid_from=current_start,
                title=f"Budget alert: {budget.name}",
                defaults={
                    'title': f"Budget alert: {budget.name}",
                    'description': f"You've used {budget.get_progress_percentage():.0f}% of your {budget.name} budget.",
                    'actionable_advice': f"${budget.get_remaining_amount():.2f} remaining this period.",
                    'priority': 'urgent' if budget.is_over_budget() else 'high',
                }
            )

    for sub in Subscription.objects.filter(user=user, status='active')[:5]:
        SpendingInsight.objects.update_or_create(
            user=user,
            insight_type='subscription_found',
            valid_from=current_start,
            title=f"Recurring: {sub.merchant_name}",
            defaults={
                'description': f"${sub.amount} {sub.billing_cycle} — review if still needed.",
                'priority': 'medium',
            }
        )

    for anomaly in Anomaly.objects.filter(user=user, is_reviewed=False)[:3]:
        SpendingInsight.objects.update_or_create(
            user=user,
            insight_type='anomaly_detected',
            valid_from=today,
            title=anomaly.title,
            defaults={
                'description': anomaly.description,
                'priority': 'high' if anomaly.severity in ('high', 'critical') else 'medium',
            }
        )

    logger.info(f"Spending insights generated for user {user_id}")


@shared_task
def generate_savings_recommendations(user_id):
    from django.contrib.auth import get_user_model
    from assistant.services import AssistantService
    from .models import SavingsRecommendation

    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return

    service = AssistantService(user)
    recs = service.get_recommendations(user)

    category_map = {
        'high_spending': 'other',
        'subscription': 'subscriptions',
    }

    for rec in recs:
        SavingsRecommendation.objects.update_or_create(
            user=user,
            title=rec['suggestion'],
            defaults={
                'category': category_map.get(rec['type'], 'other'),
                'description': rec['suggestion'],
                'estimated_monthly_savings': Decimal(str(rec.get('amount', 0) * 0.2)),
                'confidence': 0.7,
                'action_steps': [rec['suggestion']],
                'supporting_data': rec,
            }
        )

    logger.info(f"Savings recommendations generated for user {user_id}")


@shared_task
def generate_cashflow_projections(user_id):
    from django.contrib.auth import get_user_model
    from .models import CashFlowProjection
    
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return
    
    # Stub implementation - would use predictive analysis
    logger.info(f"Cashflow projections generation queued for user {user_id}")


@shared_task
def enrich_merchant(merchant_name):
    from .models import MerchantEnrichment
    from transactions.models import MerchantCache
    
    normalized = merchant_name.strip().lower()
    
    # Check if already cached
    existing = MerchantEnrichment.objects.filter(normalized_name__iexact=normalized).first()
    if existing:
        existing.lookup_count += 1
        existing.save()
        return
    
    # In real implementation, call external API (Google Places, Yelp, etc.)
    # For now, create basic entry
    MerchantEnrichment.objects.create(
        merchant_name=merchant_name,
        normalized_name=normalized,
        confidence=0.3,
        source='manual'
    )
    
    # Also update merchant cache
    MerchantCache.objects.get_or_create(
        normalized_name=normalized,
        defaults={'name': merchant_name, 'confidence': 0.3}
    )