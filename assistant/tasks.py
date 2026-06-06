from celery import shared_task
from django.utils import timezone
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_assistant_message(self, conversation_id, message_id):
    from assistant.models import Conversation, Message
    from assistant.services import AssistantService
    
    try:
        conversation = Conversation.objects.get(id=conversation_id)
        user_message = Message.objects.get(id=message_id)
        
        started_at = timezone.now()

        # Process with assistant service
        service = AssistantService(conversation.user)
        response = service.process_message(user_message.content, conversation)
        
        # Create assistant response message
        assistant_message = Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=response.get('content', ''),
            metadata=response.get('metadata', {}),
            tokens_used=response.get('tokens_used', 0),
            model_used=response.get('model_used', '')
        )
        
        completed_at = timezone.now()
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        
        # Update conversation title if first message
        if conversation.messages.count() == 2:  # user + assistant
            conversation.title = user_message.content[:50]
            conversation.save()
        
        return {'status': 'completed', 'response_id': str(assistant_message.id)}
        
    except Exception as exc:
        logger.error(f"Assistant message processing failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def detect_subscriptions(self, user_id):
    from django.contrib.auth import get_user_model
    from transactions.models import Transaction
    from assistant.models import Subscription
    from dateutil.relativedelta import relativedelta
    
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return
    
    # Get recurring transactions from last 12 months
    cutoff_date = date.today() - relativedelta(months=12)
    transactions = Transaction.objects.filter(
        user=user,
        date__gte=cutoff_date,
        transaction_type='debit',
        status='posted'
    ).order_by('merchant_name', 'date')
    
    # Group by merchant
    merchant_groups = defaultdict(list)
    for txn in transactions:
        key = txn.merchant_name.strip().lower()
        merchant_groups[key].append(txn)
    
    # Analyze each merchant for subscription patterns
    for merchant_key, txns in merchant_groups.items():
        if len(txns) < 2:
            continue
        
        # Check for regular intervals
        pattern = analyze_subscription_pattern(txns)
        if pattern:
            # Check if subscription already exists
            existing = Subscription.objects.filter(
                user=user,
                normalized_merchant=merchant_key
            ).first()
            
            if existing:
                # Update existing
                existing.confidence = max(existing.confidence, pattern['confidence'])
                existing.transactions.add(*txns)
                existing.amount = pattern['amount']
                existing.billing_cycle = pattern['billing_cycle']
                existing.next_billing_date = pattern['next_date']
                existing.save()
            else:
                # Create new subscription
                Subscription.objects.create(
                    user=user,
                    merchant_name=txns[0].merchant_name,
                    normalized_merchant=merchant_key,
                    category=txns[0].category,
                    amount=pattern['amount'],
                    currency=txns[0].currency,
                    billing_cycle=pattern['billing_cycle'],
                    status='unknown',
                    confidence=pattern['confidence'],
                    detection_method='pattern',
                    start_date=pattern['start_date'],
                    next_billing_date=pattern['next_date'],
                    last_billing_date=txns[-1].date
                ).transactions.add(*txns)
    
    logger.info(f"Subscription detection completed for user {user_id}")


def analyze_subscription_pattern(transactions):
    """Analyze transactions for subscription pattern"""
    if len(transactions) < 2:
        return None
    
    # Sort by date
    txns = sorted(transactions, key=lambda t: t.date)
    
    # Calculate intervals between transactions
    intervals = []
    amounts = []
    for i in range(1, len(txns)):
        delta = (txns[i].date - txns[i-1].date).days
        intervals.append(delta)
        amounts.append(float(txns[i].amount))
    
    if not intervals:
        return None
    
    # Check if amounts are consistent (within 10%)
    avg_amount = sum(amounts) / len(amounts)
    amount_consistent = all(abs(a - avg_amount) / avg_amount < 0.15 for a in amounts)
    
    if not amount_consistent:
        return None
    
    # Determine billing cycle from intervals
    avg_interval = sum(intervals) / len(intervals)
    
    if 25 <= avg_interval <= 35:
        billing_cycle = 'monthly'
    elif 6 <= avg_interval <= 10:
        billing_cycle = 'weekly'
    elif 85 <= avg_interval <= 95:
        billing_cycle = 'quarterly'
    elif 355 <= avg_interval <= 375:
        billing_cycle = 'yearly'
    else:
        billing_cycle = 'irregular'
    
    # Calculate confidence
    interval_variance = sum((i - avg_interval) ** 2 for i in intervals) / len(intervals)
    interval_consistency = 1 - min(interval_variance / (avg_interval ** 2), 1)
    
    confidence = (0.5 * interval_consistency + 0.3 * (1 if amount_consistent else 0) + 0.2 * min(len(txns) / 6, 1))
    
    if confidence < 0.5:
        return None
    
    # Predict next billing date
    last_date = txns[-1].date
    if billing_cycle == 'monthly':
        next_date = last_date + relativedelta(months=1)
    elif billing_cycle == 'weekly':
        next_date = last_date + relativedelta(weeks=1)
    elif billing_cycle == 'quarterly':
        next_date = last_date + relativedelta(months=3)
    elif billing_cycle == 'yearly':
        next_date = last_date + relativedelta(years=1)
    else:
        next_date = last_date + timedelta(days=int(avg_interval))
    
    return {
        'amount': Decimal(str(avg_amount)),
        'billing_cycle': billing_cycle,
        'confidence': round(confidence, 2),
        'start_date': txns[0].date,
        'next_date': next_date
    }


@shared_task(bind=True, max_retries=3)
def detect_anomalies(self, user_id):
    from django.contrib.auth import get_user_model
    from transactions.models import Transaction
    from assistant.models import Anomaly
    from dateutil.relativedelta import relativedelta
    from decimal import Decimal
    import statistics
    
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return
    
    # Get transactions from last 6 months for baseline
    cutoff_date = date.today() - relativedelta(months=6)
    recent_cutoff = date.today() - relativedelta(weeks=4)
    
    baseline_transactions = Transaction.objects.filter(
        user=user,
        date__gte=cutoff_date,
        date__lt=recent_cutoff,
        transaction_type='debit',
        status='posted'
    )
    
    recent_transactions = Transaction.objects.filter(
        user=user,
        date__gte=recent_cutoff,
        transaction_type='debit',
        status='posted'
    )
    
    if baseline_transactions.count() < 10:
        logger.info(f"Not enough baseline data for user {user_id}")
        return
    
    # Build baseline stats by category
    category_stats = {}
    for txn in baseline_transactions:
        cat_key = txn.category.name if txn.category else 'uncategorized'
        if cat_key not in category_stats:
            category_stats[cat_key] = {'amounts': [], 'merchants': set(), 'days': []}
        category_stats[cat_key]['amounts'].append(float(abs(txn.amount)))
        category_stats[cat_key]['merchants'].add(txn.merchant_name.lower().strip())
        category_stats[cat_key]['days'].append(txn.date.weekday())
    
    # Calculate stats
    for cat, data in category_stats.items():
        if len(data['amounts']) >= 3:
            data['mean'] = statistics.mean(data['amounts'])
            data['stdev'] = statistics.stdev(data['amounts']) if len(data['amounts']) > 1 else 0
            data['merchant_count'] = len(data['merchants'])
            data['common_days'] = statistics.mode(data['days']) if data['days'] else None
    
    # Check recent transactions for anomalies
    for txn in recent_transactions:
        cat_key = txn.category.name if txn.category else 'uncategorized'
        if cat_key not in category_stats:
            continue
        
        stats = category_stats[cat_key]
        amount = float(abs(txn.amount))
        
        # 1. Unusual amount (z-score > 2.5)
        if stats['stdev'] > 0:
            z_score = abs(amount - stats['mean']) / stats['stdev']
            if z_score > 2.5:
                create_anomaly(user, txn, 'unusual_amount', 'high' if z_score > 3.5 else 'medium',
                    f"Unusual {cat_key} expense: ${amount:.2f} (typical: ${stats['mean']:.2f} ± ${stats['stdev']:.2f})",
                    {'expected_range': [stats['mean'] - 2*stats['stdev'], stats['mean'] + 2*stats['stdev']]},
                    z_score / 4  # Normalize confidence
                )
        
        # 2. Unusual merchant
        merchant_key = txn.merchant_name.lower().strip()
        if merchant_key not in stats['merchants'] and stats['merchant_count'] > 0:
            create_anomaly(user, txn, 'unusual_merchant', 'medium',
                f"New merchant in {cat_key}: {txn.merchant_name}",
                {'known_merchants': list(stats['merchants'])[:10]},
                0.7
            )
        
        # 3. Check for duplicate charges (same merchant, same amount within 3 days)
        duplicates = Transaction.objects.filter(
            user=user,
            merchant_name=txn.merchant_name,
            amount=txn.amount,
            date__gte=txn.date - timedelta(days=3),
            date__lt=txn.date
        ).exclude(id=txn.id)
        
        if duplicates.exists():
            create_anomaly(user, txn, 'duplicate_charge', 'high',
                f"Possible duplicate charge: {txn.merchant_name} for ${amount:.2f}",
                {'duplicate_ids': [str(d.id) for d in duplicates]},
                0.9
            )
    
    logger.info(f"Anomaly detection completed for user {user_id}")


def create_anomaly(user, transaction, anomaly_type, severity, title, expected_value, confidence):
    from assistant.models import Anomaly
    
    # Check if already exists
    exists = Anomaly.objects.filter(
        user=user,
        transaction=transaction,
        anomaly_type=anomaly_type
    ).exists()
    
    if not exists:
        Anomaly.objects.create(
            user=user,
            transaction=transaction,
            anomaly_type=anomaly_type,
            severity=severity,
            title=title,
            description=title,
            expected_value=expected_value,
            actual_value={'amount': str(abs(transaction.amount)), 'merchant': transaction.merchant_name},
            confidence=confidence
        )


@shared_task
def enrich_merchant(merchant_name):
    from insights.models import MerchantEnrichment
    from transactions.models import MerchantCache
    from assistant.merchant_lookup import lookup_merchant_online

    normalized = merchant_name.strip().lower()

    existing = MerchantEnrichment.objects.filter(normalized_name__iexact=normalized).first()
    if existing:
        existing.lookup_count += 1
        existing.save()
        return

    web = lookup_merchant_online(merchant_name) or {}
    MerchantEnrichment.objects.create(
        merchant_name=merchant_name,
        normalized_name=normalized,
        description=web.get('description', ''),
        confidence=0.6 if web.get('description') else 0.3,
        source=web.get('source', 'manual'),
        is_subscription_service=web.get('is_subscription', False),
    )

    MerchantCache.objects.update_or_create(
        normalized_name=normalized,
        defaults={
            'name': merchant_name,
            'confidence': 0.6 if web.get('description') else 0.3,
        }
    )