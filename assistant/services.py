try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from django.conf import settings
import json
import logging
import re
from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Sum, Count

from assistant.context_extractor import extract_and_save_context
from assistant.query_tools import FinanceQueryTools
from assistant.memory import build_memory_context, update_conversation_memory

logger = logging.getLogger(__name__)


class AssistantService:
    """
    Hybrid assistant: fast DB tools for structured questions,
    LLM only for synthesis or genuinely ambiguous queries.
    """

    FAST_PATH_INTENTS = {
        'spending', 'biggest', 'comparison', 'budget', 'subscription',
        'anomaly', 'summary', 'savings', 'merchant_lookup', 'context',
    }

    def __init__(self, user):
        self.user = user
        self.tools = FinanceQueryTools(user)
        api_key = getattr(settings, 'GEMINI_API_KEY', '')
        self.client = None
        if GEMINI_AVAILABLE and api_key:
            try:
                self.client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to configure Gemini client: {e}")

    def process_message(self, message, conversation):
        saved_context = extract_and_save_context(self.user, message)
        intents = self._identify_intents(message)

        if saved_context:
            ack = self._format_context_ack(saved_context)
            if intents.get('primary') == 'context':
                update_conversation_memory(conversation)
                return {
                    'content': ack,
                    'metadata': {'intents': intents, 'context_saved': saved_context},
                    'tokens_used': 0,
                    'model_used': 'context_extractor',
                }

        if intents.get('is_receipt_query'):
            return self._handle_receipt_intent(message, conversation)

        route = self._route_query(message, intents)
        if route:
            content = self.tools.format_tool_result(route)
            if saved_context:
                content = self._format_context_ack(saved_context) + "\n\n" + content
            update_conversation_memory(conversation)
            return {
                'content': content,
                'metadata': {'intents': intents, 'route': route.get('tool'), 'fast_path': True},
                'tokens_used': 0,
                'model_used': 'query_tools',
            }

        context = self._build_context(conversation)
        prompt = self._build_prompt(message, context, intents)

        if self.client:
            try:
                response = self.client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=prompt
                )
                content = response.text
                if saved_context:
                    content = self._format_context_ack(saved_context) + "\n\n" + content
                update_conversation_memory(conversation)
                return {
                    'content': content,
                    'metadata': {'intents': intents, 'confidence': 0.9, 'fast_path': False},
                    'tokens_used': getattr(response, 'usage_metadata', None) and getattr(response.usage_metadata, 'total_token_count', 0) or 0,
                    'model_used': 'gemini-2.0-flash',
                }
            except Exception as e:
                logger.error(f"Gemini API error: {e}")

        fallback = self._fallback_response(message, context)
        if saved_context:
            fallback = self._format_context_ack(saved_context) + "\n\n" + fallback
        result = {
            'content': fallback,
            'metadata': {'intents': intents, 'error': 'LLM unavailable'},
            'tokens_used': 0,
            'model_used': 'fallback',
        }
        update_conversation_memory(conversation)
        return result

    def _format_context_ack(self, saved):
        parts = []
        for item in saved:
            if item['key'] == 'payday':
                parts.append(f"Got it — I'll remember you get paid on the {item['value']}th.")
            elif item['type'] == 'rule':
                parts.append(f"Noted: {item['value']}.")
            elif item['type'] == 'goal':
                parts.append(f"I'll track your goal: {item['key'].replace('_', ' ')} of ${item['value']}.")
        return " ".join(parts) if parts else "I've saved that for future reference."

    def _identify_intents(self, message):
        message_lower = message.lower()

        intents = {
            'is_spending_query': any(w in message_lower for w in ['spend', 'spent', 'cost', 'expensive', 'how much']),
            'is_budget_query': any(w in message_lower for w in ['budget', 'limit', 'allowance', 'over budget']),
            'is_subscription_query': any(w in message_lower for w in ['subscription', 'recurring', 'billing cycle']),
            'is_comparison_query': any(w in message_lower for w in ['more than usual', 'compared', 'vs last', 'this month vs', 'am i spending more']),
            'is_anomaly_query': any(w in message_lower for w in ['unusual', 'suspicious', 'weird charge', 'anomaly', 'flagged']),
            'is_summary_query': any(w in message_lower for w in ['summarize', 'summary', 'overview', 'where is my money', 'breakdown']),
            'is_savings_query': any(w in message_lower for w in ['cut back', 'save money', 'reduce spending', 'suggestions', 'recommend']),
            'is_merchant_query': any(w in message_lower for w in ['what is', 'who is', 'what charge', 'unfamiliar', 'recognize', 'merchant']),
            'is_biggest_query': any(w in message_lower for w in ['biggest', 'largest', 'most expensive']),
            'is_receipt_query': any(w in message_lower for w in ['receipt', 'upload a photo', 'scan receipt']),
            'is_context_query': any(w in message_lower for w in ['remember', 'i get paid', "don't count", 'do not count', 'my goal']),
        }

        priority = [
            ('context', intents['is_context_query']),
            ('merchant_lookup', intents['is_merchant_query']),
            ('biggest', intents['is_biggest_query']),
            ('comparison', intents['is_comparison_query']),
            ('budget', intents['is_budget_query']),
            ('subscription', intents['is_subscription_query']),
            ('anomaly', intents['is_anomaly_query']),
            ('summary', intents['is_summary_query']),
            ('savings', intents['is_savings_query']),
            ('spending', intents['is_spending_query']),
        ]
        intents['primary'] = next((name for name, hit in priority if hit), 'general')
        return intents

    def _route_query(self, message, intents):
        primary = intents.get('primary', 'general')

        if primary == 'biggest' or (intents['is_biggest_query'] and intents['is_spending_query']):
            return self.tools.biggest_purchase(message)
        if primary == 'comparison' or intents['is_comparison_query']:
            return self.tools.compare_spending(message)
        if primary == 'budget' or intents['is_budget_query']:
            return self.tools.budget_status()
        if primary == 'subscription' or intents['is_subscription_query']:
            return self.tools.list_subscriptions()
        if primary == 'anomaly' or intents['is_anomaly_query']:
            return self.tools.list_anomalies()
        if primary == 'summary' or intents['is_summary_query']:
            return self.tools.financial_summary()
        if primary == 'savings' or intents['is_savings_query']:
            return self.tools.savings_suggestions()
        if primary == 'merchant_lookup' or intents['is_merchant_query']:
            merchant = self._extract_merchant_name(message)
            if merchant:
                return self.tools.lookup_merchant(merchant)
        if primary == 'spending' or intents['is_spending_query']:
            return self.tools.spending_by_period(message)

        return None

    def _extract_merchant_name(self, message):
        patterns = [
            r'(?:what is|who is|what charge is|what is this charge from)\s+(.+?)\??$',
            r'(?:charge from|merchant)\s+(.+?)\??$',
            r'(?:recognize|unfamiliar)\s+(?:charge\s+)?(?:from\s+)?(.+?)\??$',
        ]
        for pattern in patterns:
            match = re.search(pattern, message.strip(), re.IGNORECASE)
            if match:
                return match.group(1).strip().strip('"\'')
        quoted = re.search(r'["\'](.+?)["\']', message)
        if quoted:
            return quoted.group(1)
        return None

    def _build_context(self, conversation):
        from transactions.models import TransactionCategory

        memory = build_memory_context(self.user, conversation)
        monthly_summary = self.tools.financial_summary(months=3)

        return {
            'user_facts': memory['user_memory'],
            'conversation_summary': memory['conversation_summary'],
            'categories': list(TransactionCategory.objects.filter(is_system=True).values_list('name', flat=True)),
            'recent_summary': monthly_summary,
            'conversation_turns': memory['recent_messages'],
        }

    def _handle_receipt_intent(self, message, conversation):
        return {
            'content': (
                "Upload a receipt photo using the **Upload Receipt** button below. "
                "I'll extract the merchant, date, and total, then record it as an expense."
            ),
            'metadata': {'intent': 'receipt_upload'},
            'tokens_used': 0,
            'model_used': 'query_tools',
        }

    def _build_prompt(self, message, context, intents):
        prompt = f"""You are a helpful personal finance assistant for this specific user.
Use their saved memory and this conversation's history. Never mix data from other users.
If you cannot answer from the data, say so clearly — do not invent numbers.

Long-term user memory (facts, rules, goals — persists across all chats):
{json.dumps(context.get('user_facts', []), indent=2)}

This conversation's summary:
{context.get('conversation_summary') or 'New conversation'}

Spending summary (aggregated):
{json.dumps(context.get('recent_summary', {}), default=str, indent=2)}

Recent messages in this chat:
{json.dumps(context.get('conversation_turns', []), default=str, indent=2)}

Current question: {message}

Answer in plain English with specific numbers when available."""
        return prompt

    def _fallback_response(self, message, context):
        from transactions.models import Transaction

        message_lower = message.lower()
        if any(w in message_lower for w in ['spend', 'spent', 'how much']):
            result = self.tools.spending_by_period(message)
            return self.tools.format_tool_result(result)

        if 'budget' in message_lower:
            return self.tools.format_tool_result(self.tools.budget_status())

        if 'subscription' in message_lower:
            return self.tools.format_tool_result(self.tools.list_subscriptions())

        total = abs(float(Transaction.objects.filter(user=self.user, transaction_type='debit').aggregate(Sum('amount'))['amount__sum'] or 0))
        return (
            f"I'm here to help with your finances. You've spent ${total:.2f} total on record. "
            "Try asking about spending by category, budgets, subscriptions, or upload a receipt."
        )

    def get_spending_summary(self, period='month'):
        from transactions.models import Transaction

        today = date.today()
        if period == 'month':
            start_date = today - relativedelta(months=1)
        elif period == 'year':
            start_date = today - relativedelta(years=1)
        else:
            start_date = today - relativedelta(months=3)

        transactions = Transaction.objects.filter(
            user=self.user,
            date__gte=start_date
        )

        by_category = transactions.filter(
            transaction_type='debit'
        ).values('category__name').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        total_spent = sum(abs(float(t['total'])) for t in by_category)

        return {
            'period': period,
            'total_spent': total_spent,
            'by_category': list(by_category)
        }

    def detect_anomalies(self, user):
        from transactions.models import Transaction
        import statistics

        cutoff_date = date.today() - relativedelta(months=6)
        recent_cutoff = date.today() - relativedelta(weeks=4)

        baseline = Transaction.objects.filter(
            user=user,
            date__gte=cutoff_date,
            date__lt=recent_cutoff,
            transaction_type='debit'
        )

        if baseline.count() < 10:
            return []

        amounts = [float(abs(t.amount)) for t in baseline]
        mean = statistics.mean(amounts)
        stdev = statistics.stdev(amounts) if len(amounts) > 1 else 0

        anomalies = []
        recent = Transaction.objects.filter(
            user=user,
            date__gte=recent_cutoff,
            transaction_type='debit'
        )

        for txn in recent:
            if stdev > 0:
                z_score = abs(float(abs(txn.amount)) - mean) / stdev
                if z_score > 2.5:
                    anomalies.append({
                        'transaction': str(txn.id),
                        'type': 'unusual_amount',
                        'severity': 'high' if z_score > 3.5 else 'medium',
                        'title': f"Unusual expense: ${float(abs(txn.amount)):.2f} at {txn.merchant_name}"
                    })

        return anomalies

    def detect_subscriptions(self, user):
        from transactions.models import Transaction
        from collections import defaultdict

        cutoff_date = date.today() - relativedelta(months=12)
        transactions = Transaction.objects.filter(
            user=user,
            date__gte=cutoff_date,
            transaction_type='debit'
        ).order_by('merchant_name', 'date')

        merchant_groups = defaultdict(list)
        for txn in transactions:
            key = txn.merchant_name.strip().lower()
            merchant_groups[key].append(txn)

        subscriptions = []
        for merchant_key, txns in merchant_groups.items():
            if len(txns) < 2:
                continue

            intervals = [(txns[i].date - txns[i-1].date).days for i in range(1, len(txns))]
            if not intervals:
                continue

            avg_interval = sum(intervals) / len(intervals)
            amounts = [float(abs(t.amount)) for t in txns[1:]]

            if len(amounts) > 0 and all(abs(a - sum(amounts)/len(amounts)) / (sum(amounts)/len(amounts)) < 0.2 for a in amounts):
                billing_cycle = 'monthly' if 25 <= avg_interval <= 35 else 'weekly' if 6 <= avg_interval <= 10 else 'irregular'

                if billing_cycle in ['monthly', 'weekly']:
                    subscriptions.append({
                        'merchant': txns[0].merchant_name,
                        'amount': float(abs(txns[0].amount)),
                        'billing_cycle': billing_cycle,
                        'frequency_count': len(txns)
                    })

        return subscriptions

    def get_recommendations(self, user):
        summary = self.get_spending_summary('month')
        subscriptions = self.detect_subscriptions(user)

        recommendations = []

        for category in summary['by_category']:
            if float(category['total']) > 500:
                recommendations.append({
                    'type': 'high_spending',
                    'category': category['category__name'],
                    'amount': float(abs(category['total'])),
                    'suggestion': f"Consider reducing spending in {category['category__name']}"
                })

        for sub in subscriptions:
            if sub['frequency_count'] > 3:
                recommendations.append({
                    'type': 'subscription',
                    'merchant': sub['merchant'],
                    'amount': sub['amount'],
                    'suggestion': f"Review {sub['merchant']} subscription (${sub['amount']}/month)"
                })

        return recommendations
