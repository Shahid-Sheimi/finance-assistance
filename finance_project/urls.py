"""
URL configuration for finance_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from core.chat_views import (
    chat_interface, chat_send, chat_upload_receipt, chat_upload_document,
    chat_conversations_list, chat_conversation_create,
    chat_conversation_detail, chat_conversation_delete,
    chat_conversation_rename, chat_memory, chat_memory_delete,
)
from core.views import signup

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include([
        path('', include('core.urls')),
        path('', include('transactions.urls')),
        path('', include('assistant.urls')),
        path('', include('budgets.urls')),
        path('', include('insights.urls')),
    ])),
    path('api/v1/auth/', include('rest_framework.urls')),
    path('signup/', signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    # Chat API (multi-tenant, per-user)
    path('chat/api/conversations/', chat_conversations_list, name='chat_conversations_list'),
    path('chat/api/conversations/new/', chat_conversation_create, name='chat_conversation_create'),
    path('chat/api/conversations/<uuid:conversation_id>/', chat_conversation_detail, name='chat_conversation_detail'),
    path('chat/api/conversations/<uuid:conversation_id>/delete/', chat_conversation_delete, name='chat_conversation_delete'),
    path('chat/api/conversations/<uuid:conversation_id>/rename/', chat_conversation_rename, name='chat_conversation_rename'),
    path('chat/api/memory/', chat_memory, name='chat_memory'),
    path('chat/api/memory/<int:memory_id>/delete/', chat_memory_delete, name='chat_memory_delete'),
    path('chat/send/', chat_send, name='chat_send'),
    path('chat/upload-receipt/', chat_upload_receipt, name='chat_upload_receipt'),
    path('chat/upload-document/', chat_upload_document, name='chat_upload_document'),
    path('', chat_interface, name='chat'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)