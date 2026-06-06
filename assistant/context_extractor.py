"""
Extract and persist user context from natural language messages.

Handles facts like paydays, rules like budget exclusions, and goals.
"""
import re
import logging

logger = logging.getLogger(__name__)

PAYDAY_PATTERNS = [
    (r'(?:i get paid|payday|paid)\s+(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?', 'payday', 'fact'),
    (r'pay\s+(?:is\s+)?(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?', 'payday', 'fact'),
]

RULE_PATTERNS = [
    (r"(?:don't|do not|dont)\s+count\s+(.+?)\s+(?:in|from|for)\s+(?:my\s+)?(.+?)(?:\s+budget)?$", 'exclude_from_budget', 'rule'),
    (r"exclude\s+(.+?)\s+from\s+(?:my\s+)?(.+?)(?:\s+budget)?$", 'exclude_from_budget', 'rule'),
]

GOAL_PATTERNS = [
    (r"(?:i want to|my goal is to|trying to)\s+save\s+\$?([\d,]+(?:\.\d{2})?)", 'savings_goal', 'goal'),
    (r"spending\s+(?:limit|cap)\s+(?:of\s+)?\$?([\d,]+(?:\.\d{2})?)", 'spending_limit', 'goal'),
]


def extract_and_save_context(user, message):
    """Parse message for context signals and persist to UserContext."""
    from core.models import UserContext, UserPreference

    message_lower = message.lower().strip()
    saved = []

    for pattern, key, ctx_type in PAYDAY_PATTERNS:
        match = re.search(pattern, message_lower)
        if match:
            day = int(match.group(1))
            if 1 <= day <= 31:
                UserContext.objects.update_or_create(
                    user=user, key=key, context_type=ctx_type,
                    defaults={'value': str(day), 'source': 'conversation', 'confidence': 0.95}
                )
                pref, _ = UserPreference.objects.get_or_create(user=user)
                pref.payday = day
                pref.save()
                saved.append({'key': key, 'value': str(day), 'type': ctx_type})

    for pattern, key, ctx_type in RULE_PATTERNS:
        match = re.search(pattern, message_lower)
        if match:
            excluded = match.group(1).strip()
            budget_area = match.group(2).strip()
            value = f"exclude {excluded} from {budget_area} budget"
            rule_key = f"exclude_{excluded.replace(' ', '_')}_{budget_area.replace(' ', '_')}"
            UserContext.objects.update_or_create(
                user=user, key=rule_key, context_type=ctx_type,
                defaults={'value': value, 'source': 'conversation', 'confidence': 0.9}
            )
            saved.append({'key': rule_key, 'value': value, 'type': ctx_type})

    for pattern, key, ctx_type in GOAL_PATTERNS:
        match = re.search(pattern, message_lower)
        if match:
            amount = match.group(1).replace(',', '')
            UserContext.objects.update_or_create(
                user=user, key=key, context_type=ctx_type,
                defaults={'value': amount, 'source': 'conversation', 'confidence': 0.85}
            )
            saved.append({'key': key, 'value': amount, 'type': ctx_type})

    if saved:
        logger.info(f"Saved {len(saved)} context items for user {user.id}")

    return saved
