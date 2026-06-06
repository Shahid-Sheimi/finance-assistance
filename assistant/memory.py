"""Conversation and user-level memory for the assistant."""
import logging

logger = logging.getLogger(__name__)


def build_memory_context(user, conversation):
    """Assemble memory layers for the assistant prompt."""
    from core.models import UserContext

    user_memory = list(
        UserContext.objects.filter(user=user, is_active=True)
        .order_by('-updated_at')[:20]
        .values('key', 'value', 'context_type')
    )

    recent_messages = list(
        conversation.messages.order_by('-created_at')[:12]
        .values('role', 'content', 'created_at')
    )
    recent_messages.reverse()

    return {
        'user_memory': user_memory,
        'conversation_summary': conversation.context_summary,
        'recent_messages': recent_messages,
    }


def update_conversation_memory(conversation):
    """
    Update conversation title and rolling summary after each exchange.
    Lightweight — no LLM call.
    """
    user_messages = list(
        conversation.messages.filter(role='user')
        .order_by('-created_at')[:5]
        .values_list('content', flat=True)
    )

    if not conversation.title or conversation.title in ('New Chat', 'New Conversation'):
        first = conversation.messages.filter(role='user').order_by('created_at').first()
        if first:
            conversation.title = first.content[:60].strip() or 'New Chat'

    if user_messages:
        topics = [m[:80].replace('\n', ' ') for m in reversed(user_messages[:3])]
        conversation.context_summary = 'Topics discussed: ' + ' | '.join(topics)
        conversation.context_summary = conversation.context_summary[:600]

    conversation.save(update_fields=['title', 'context_summary', 'updated_at'])


def get_user_memory_summary(user):
    """Return structured memory for the UI memory panel."""
    from core.models import UserContext

    contexts = UserContext.objects.filter(user=user, is_active=True).order_by('-updated_at')
    return {
        'facts': [_ctx_item(c) for c in contexts.filter(context_type='fact')[:10]],
        'rules': [_ctx_item(c) for c in contexts.filter(context_type='rule')[:10]],
        'preferences': [_ctx_item(c) for c in contexts.filter(context_type='preference')[:10]],
        'goals': [_ctx_item(c) for c in contexts.filter(context_type='goal')[:10]],
    }


def delete_user_memory_item(user, memory_id):
    from core.models import UserContext
    ctx = UserContext.objects.filter(id=memory_id, user=user).first()
    if ctx:
        ctx.is_active = False
        ctx.save(update_fields=['is_active', 'updated_at'])
        return True
    return False


def _ctx_item(ctx):
    return {
        'id': ctx.id,
        'key': ctx.key,
        'value': ctx.value,
        'type': ctx.context_type,
        'updated_at': ctx.updated_at.isoformat(),
    }
