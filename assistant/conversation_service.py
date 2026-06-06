"""Conversation CRUD with strict per-user isolation (multi-tenant)."""
from django.utils import timezone
from django.shortcuts import get_object_or_404

from assistant.models import Conversation, Message


class ConversationService:
    """All conversation access goes through here — scoped to one user."""

    def __init__(self, user):
        self.user = user

    def list_conversations(self, limit=50):
        return (
            Conversation.objects.filter(user=self.user, is_active=True)
            .prefetch_related('messages')
            .order_by('-updated_at')[:limit]
        )

    def get_conversation(self, conversation_id):
        return get_object_or_404(Conversation, id=conversation_id, user=self.user)

    def create_conversation(self, title='New Chat'):
        return Conversation.objects.create(user=self.user, title=title)

    def get_or_create_default(self):
        existing = (
            Conversation.objects.filter(user=self.user, is_active=True)
            .order_by('-updated_at')
            .first()
        )
        if existing:
            return existing
        return self.create_conversation()

    def delete_conversation(self, conversation_id):
        conversation = self.get_conversation(conversation_id)
        conversation.is_active = False
        conversation.save(update_fields=['is_active', 'updated_at'])
        return conversation

    def hard_delete_conversation(self, conversation_id):
        conversation = self.get_conversation(conversation_id)
        conversation.delete()

    def rename_conversation(self, conversation_id, title):
        conversation = self.get_conversation(conversation_id)
        conversation.title = (title or 'Untitled')[:200]
        conversation.save(update_fields=['title', 'updated_at'])
        return conversation

    def get_messages(self, conversation_id, limit=100):
        conversation = self.get_conversation(conversation_id)
        return conversation.messages.order_by('created_at')[:limit]

    def add_message(self, conversation_id, role, content, **kwargs):
        conversation = self.get_conversation(conversation_id)
        message = Message.objects.create(
            conversation=conversation,
            role=role,
            content=content,
            metadata=kwargs.pop('metadata', {}),
            tokens_used=kwargs.pop('tokens_used', 0),
            model_used=kwargs.pop('model_used', ''),
            **kwargs,
        )
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])
        return message

    def serialize_conversation(self, conversation):
        last_msg = conversation.messages.order_by('-created_at').first()
        return {
            'id': str(conversation.id),
            'title': conversation.title or 'New Chat',
            'context_summary': conversation.context_summary,
            'message_count': conversation.messages.count(),
            'updated_at': conversation.updated_at.isoformat(),
            'preview': (last_msg.content[:80] + '…') if last_msg and len(last_msg.content) > 80 else (last_msg.content if last_msg else ''),
        }

    def serialize_message(self, message):
        return {
            'id': str(message.id),
            'role': message.role,
            'content': message.content,
            'metadata': message.metadata,
            'created_at': message.created_at.isoformat(),
        }
