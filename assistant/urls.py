from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ConversationViewSet, MessageViewSet, AssistantToolViewSet,
    SubscriptionViewSet, AnomalyViewSet, AssistantActionViewSet
)

router = DefaultRouter()
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'tools', AssistantToolViewSet, basename='assistanttool')
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'anomalies', AnomalyViewSet, basename='anomaly')
router.register(r'actions', AssistantActionViewSet, basename='assistantaction')

urlpatterns = router.urls