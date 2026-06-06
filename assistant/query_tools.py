"""
Fast, database-backed query tools for the finance assistant.

These run SQL aggregations instead of sending transaction history to an LLM,
so simple questions stay fast and cheap even with years of data.
"""
import re
import calendar
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Sum, Count, Max, Q, Avg
from django.db.models.functions import TruncMonth


CATEGORY_ALIASES = {
    'groceries': ['groceries', 'grocery', 'food', 'supermarket'],
    'dining': ['dining', 'restaurant', 'restaurants', 'food delivery', 'takeout', 'coffee'],
    'transportation': ['transportation', 'transport', 'gas', 'uber', 'lyft', 'transit'],
    'shopping': ['shopping', 'retail', 'amazon'],
    'entertainment': ['entertainment', 'streaming', 'movies', 'games'],
    'utilities': ['utilities', 'bills', 'electric', 'internet', 'phone'],
    'healthcare': ['healthcare', 'health', 'medical', 'pharmacy'],
    'income': ['income', 'salary', 'paycheck'],
}


def _parse_month(message):
    """Extract a month reference from natural language."""
    message_lower = message.lower()
    today = date.today()

    if 'last month' in message_lower:
        ref = today - relativedelta(months=1)
        return ref.replace(day=1), ref.replace(day=calendar.monthrange(ref.year, ref.month)[1])

    if 'this month' in message_lower:
        return today.replace(day=1), today

    month_names = list(calendar.month_name)[1:]
    for i, name in enumerate(month_names, 1):
        if name.lower() in message_lower:
            year = today.year
            year_match = re.search(r'(20\d{2})', message_lower)
            if year_match:
                year = int(year_match.group(1))
            start = date(year, i, 1)
            end = date(year, i, calendar.monthrange(year, i)[1])
            return start, end

    return None, None


def _match_category(message, TransactionCategory):
    message_lower = message.lower()
    for cat_name, aliases in CATEGORY_ALIASES.items():
        if any(alias in message_lower for alias in aliases):
            cat = TransactionCategory.objects.filter(name__iexact=cat_name).first()
            if cat:
                return cat
    return None


def _debit_queryset(user, Transaction):
    return Transaction.objects.filter(user=user, transaction_type='debit', status='posted')


def _apply_user_rules(user, queryset, UserContext):
    """Apply stored user rules (e.g. exclude rent from food budget)."""
    rules = UserContext.objects.filter(user=user, context_type='rule', is_active=True)
    for rule in rules:
        value_lower = rule.value.lower()
        if 'exclude' in value_lower or "don't count" in value_lower or 'do not count' in value_lower:
            for cat_name, aliases in CATEGORY_ALIASES.items():
                if cat_name in value_lower or any(a in value_lower for a in aliases):
                    queryset = queryset.exclude(category__name__iexact=cat_name.title())
    return queryset


class FinanceQueryTools:
    def __init__(self, user):
        self.user = user

    def spending_by_period(self, message):
        from transactions.models import Transaction, TransactionCategory
        from core.models import UserContext

        start, end = _parse_month(message)
        if not start:
            today = date.today()
            start = today.replace(day=1)
            end = today

        qs = _debit_queryset(self.user, Transaction).filter(date__gte=start, date__lte=end)
        category = _match_category(message, TransactionCategory)
        if category:
            qs = qs.filter(category=category)

        qs = _apply_user_rules(self.user, qs, UserContext)
        total = qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        count = qs.count()

        cat_label = category.name if category else 'all categories'
        return {
            'tool': 'spending_by_period',
            'start': start.isoformat(),
            'end': end.isoformat(),
            'category': cat_label,
            'total_spent': float(abs(total)),
            'transaction_count': count,
        }

    def biggest_purchase(self, message):
        from transactions.models import Transaction

        start, end = _parse_month(message)
        qs = _debit_queryset(self.user, Transaction)
        if start and end:
            qs = qs.filter(date__gte=start, date__lte=end)

        txn = qs.order_by('amount').first()
        if not txn:
            return {'tool': 'biggest_purchase', 'found': False}

        return {
            'tool': 'biggest_purchase',
            'found': True,
            'merchant': txn.merchant_name,
            'amount': float(abs(txn.amount)),
            'date': txn.date.isoformat(),
            'category': txn.category.name if txn.category else 'Uncategorized',
        }

    def compare_spending(self, message):
        from transactions.models import Transaction

        today = date.today()
        current_start = today.replace(day=1)
        prev_start = current_start - relativedelta(months=1)
        prev_end = current_start - relativedelta(days=1)

        current_total = _debit_queryset(self.user, Transaction).filter(
            date__gte=current_start, date__lte=today
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        prev_total = _debit_queryset(self.user, Transaction).filter(
            date__gte=prev_start, date__lte=prev_end
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        current = float(abs(current_total))
        previous = float(abs(prev_total))
        change = current - previous
        pct = (change / previous * 100) if previous else 0

        days_elapsed = today.day
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        projected = (current / days_elapsed * days_in_month) if days_elapsed else 0

        return {
            'tool': 'compare_spending',
            'current_month_to_date': current,
            'previous_month_total': previous,
            'change_amount': round(change, 2),
            'change_percent': round(pct, 1),
            'projected_month_total': round(projected, 2),
            'days_elapsed': days_elapsed,
            'days_in_month': days_in_month,
        }

    def budget_status(self):
        from budgets.models import Budget

        budgets = Budget.objects.filter(user=self.user, is_active=True).select_related('category')
        if not budgets.exists():
            return {'tool': 'budget_status', 'budgets': [], 'has_budgets': False}

        results = []
        for budget in budgets:
            spent = budget.get_spent_amount()
            progress = budget.get_progress_percentage()
            results.append({
                'name': budget.name,
                'category': budget.category.name,
                'budgeted': float(budget.amount),
                'spent': float(spent),
                'remaining': float(budget.get_remaining_amount()),
                'progress_percent': round(progress, 1),
                'should_alert': budget.should_alert(),
                'is_over': budget.is_over_budget(),
            })

        return {'tool': 'budget_status', 'has_budgets': True, 'budgets': results}

    def list_subscriptions(self):
        from assistant.models import Subscription

        subs = Subscription.objects.filter(user=self.user).order_by('-confidence')[:20]
        if not subs.exists():
            from assistant.services import AssistantService
            detected = AssistantService(self.user).detect_subscriptions(self.user)
            return {
                'tool': 'list_subscriptions',
                'source': 'pattern_detection',
                'subscriptions': detected,
                'monthly_total': round(sum(
                    s['amount'] if s['billing_cycle'] == 'monthly' else s['amount'] * 4.33
                    for s in detected if s['billing_cycle'] in ('monthly', 'weekly')
                ), 2),
            }

        items = []
        monthly_total = 0
        for sub in subs:
            amt = float(sub.amount)
            if sub.billing_cycle == 'weekly':
                monthly_total += amt * 4.33
            elif sub.billing_cycle == 'monthly':
                monthly_total += amt
            elif sub.billing_cycle == 'quarterly':
                monthly_total += amt / 3
            elif sub.billing_cycle == 'yearly':
                monthly_total += amt / 12
            items.append({
                'merchant': sub.merchant_name,
                'amount': amt,
                'billing_cycle': sub.billing_cycle,
                'confidence': sub.confidence,
                'status': sub.status,
            })

        return {'tool': 'list_subscriptions', 'source': 'database', 'subscriptions': items, 'monthly_total': round(monthly_total, 2)}

    def list_anomalies(self):
        from assistant.models import Anomaly

        anomalies = Anomaly.objects.filter(
            user=self.user, is_reviewed=False, is_false_positive=False
        ).select_related('transaction')[:10]

        return {
            'tool': 'list_anomalies',
            'count': anomalies.count(),
            'anomalies': [
                {
                    'type': a.anomaly_type,
                    'severity': a.severity,
                    'title': a.title,
                    'merchant': a.transaction.merchant_name,
                    'amount': float(abs(a.transaction.amount)),
                    'date': a.transaction.date.isoformat(),
                }
                for a in anomalies
            ],
        }

    def financial_summary(self, months=6):
        from transactions.models import Transaction

        end = date.today()
        start = end - relativedelta(months=months)
        qs = _debit_queryset(self.user, Transaction).filter(date__gte=start, date__lte=end)

        by_category = list(
            qs.values('category__name').annotate(total=Sum('amount'), count=Count('id')).order_by('-total')[:8]
        )
        for item in by_category:
            item['total'] = float(abs(item['total'] or 0))

        monthly = list(
            qs.annotate(month=TruncMonth('date')).values('month').annotate(
                total=Sum('amount')
            ).order_by('month')
        )
        for item in monthly:
            item['month'] = item['month'].strftime('%Y-%m')
            item['total'] = float(abs(item['total'] or 0))

        total_spent = sum(c['total'] for c in by_category)

        return {
            'tool': 'financial_summary',
            'months': months,
            'total_spent': round(total_spent, 2),
            'by_category': by_category,
            'monthly_trend': monthly,
            'transaction_count': qs.count(),
        }

    def savings_suggestions(self):
        from assistant.services import AssistantService

        summary = AssistantService(self.user).get_spending_summary('month')
        recommendations = AssistantService(self.user).get_recommendations(self.user)

        return {
            'tool': 'savings_suggestions',
            'monthly_by_category': [
                {
                    'category': c['category__name'] or 'Uncategorized',
                    'amount': float(abs(c['total'] or 0)),
                }
                for c in summary['by_category'][:5]
            ],
            'recommendations': recommendations,
        }

    def lookup_merchant(self, merchant_name):
        from transactions.models import Transaction, MerchantCache
        from insights.models import MerchantEnrichment

        normalized = merchant_name.strip().lower()

        cached = MerchantCache.objects.filter(normalized_name__iexact=normalized).first()
        enrichment = MerchantEnrichment.objects.filter(normalized_name__iexact=normalized).first()
        user_txns = Transaction.objects.filter(
            user=self.user, merchant_name__icontains=merchant_name
        ).order_by('-date')[:5]

        result = {
            'tool': 'lookup_merchant',
            'merchant': merchant_name,
            'from_cache': None,
            'from_enrichment': None,
            'user_history': [
                {
                    'date': t.date.isoformat(),
                    'amount': float(abs(t.amount)),
                    'category': t.category.name if t.category else None,
                }
                for t in user_txns
            ],
            'web_info': None,
        }

        if cached:
            result['from_cache'] = {
                'name': cached.name,
                'category': cached.category.name if cached.category else None,
                'website': cached.website,
            }

        if enrichment:
            result['from_enrichment'] = {
                'description': enrichment.description,
                'business_type': enrichment.business_type,
                'website': enrichment.website,
                'is_subscription': enrichment.is_subscription_service,
            }

        if not enrichment or not enrichment.description:
            from assistant.merchant_lookup import lookup_merchant_online
            web = lookup_merchant_online(merchant_name)
            result['web_info'] = web

        return result

    def format_tool_result(self, data):
        """Turn structured tool output into plain-English for fast-path responses."""
        tool = data.get('tool')

        if tool == 'spending_by_period':
            return (
                f"From {data['start']} to {data['end']}, you spent "
                f"${data['total_spent']:.2f} on {data['category']} "
                f"({data['transaction_count']} transactions)."
            )

        if tool == 'biggest_purchase':
            if not data.get('found'):
                return "I couldn't find any purchases in that period."
            return (
                f"Your biggest purchase was ${data['amount']:.2f} at {data['merchant']} "
                f"on {data['date']} ({data['category']})."
            )

        if tool == 'compare_spending':
            direction = 'more' if data['change_amount'] > 0 else 'less'
            return (
                f"This month you've spent ${data['current_month_to_date']:.2f} so far "
                f"({data['days_elapsed']} of {data['days_in_month']} days). "
                f"Last month you spent ${data['previous_month_total']:.2f} total — "
                f"that's ${abs(data['change_amount']):.2f} {direction} at this point "
                f"({abs(data['change_percent']):.1f}%). "
                f"At your current pace, you'd spend about ${data['projected_month_total']:.2f} this month."
            )

        if tool == 'budget_status':
            if not data.get('has_budgets'):
                return "You don't have any budgets set up yet. Create one and I can track it for you."
            lines = []
            for b in data['budgets']:
                status = 'OVER BUDGET' if b['is_over'] else ('near limit' if b['should_alert'] else 'on track')
                lines.append(
                    f"• {b['name']} ({b['category']}): ${b['spent']:.2f} of ${b['budgeted']:.2f} "
                    f"({b['progress_percent']:.0f}%) — {status}"
                )
            return "Here's your budget status:\n" + "\n".join(lines)

        if tool == 'list_subscriptions':
            if not data['subscriptions']:
                return "I didn't find any recurring subscriptions in your transaction history."
            lines = [
                f"• {s['merchant']}: ${s['amount']:.2f}/{s['billing_cycle']}"
                + (f" (confidence: {s.get('confidence', 'n/a')})" if s.get('confidence') else '')
                for s in data['subscriptions'][:10]
            ]
            return (
                f"I found {len(data['subscriptions'])} recurring charges "
                f"(~${data['monthly_total']:.2f}/month):\n" + "\n".join(lines)
            )

        if tool == 'list_anomalies':
            if not data['anomalies']:
                return "No unusual activity flagged recently. Your spending looks normal."
            lines = [f"• [{a['severity'].upper()}] {a['title']}" for a in data['anomalies']]
            return f"I found {data['count']} unusual items:\n" + "\n".join(lines)

        if tool == 'financial_summary':
            cat_lines = [
                f"• {c['category__name'] or 'Uncategorized'}: ${c['total']:.2f}"
                for c in data['by_category'][:5]
            ]
            return (
                f"Over the last {data['months']} months you spent ${data['total_spent']:.2f} "
                f"across {data['transaction_count']} transactions.\n"
                f"Top categories:\n" + "\n".join(cat_lines)
            )

        if tool == 'savings_suggestions':
            if not data['recommendations']:
                return "Your spending looks reasonable — no major cutback opportunities stood out."
            lines = [f"• {r['suggestion']} (${r.get('amount', r.get('amount', 0)):.2f})" for r in data['recommendations'][:5]]
            return "Here are personalized suggestions to save money:\n" + "\n".join(lines)

        if tool == 'lookup_merchant':
            parts = [f"Here's what I found about **{data['merchant']}**:"]
            if data['user_history']:
                total = sum(h['amount'] for h in data['user_history'])
                parts.append(f"You've charged ${total:.2f} there recently ({len(data['user_history'])} transactions).")
            if data['from_enrichment'] and data['from_enrichment'].get('description'):
                parts.append(data['from_enrichment']['description'])
            elif data['web_info'] and data['web_info'].get('description'):
                parts.append(data['web_info']['description'])
            elif data['from_cache']:
                parts.append(f"Likely category: {data['from_cache'].get('category', 'unknown')}.")
            else:
                parts.append("I couldn't find much public info — check your bank statement for the full merchant name.")
            return "\n".join(parts)

        return str(data)
