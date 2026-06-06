from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .models import User, UserProfile, FinancialAccount, UserPreference, UserContext
from .serializers import (
    UserSerializer, UserProfileSerializer, FinancialAccountSerializer,
    FinancialAccountCreateSerializer,
    UserPreferenceSerializer, UserContextSerializer, UserContextCreateSerializer
)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return User.objects.none()
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        return Response(UserSerializer(request.user).data)


class UserProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)


class FinancialAccountViewSet(viewsets.ModelViewSet):
    serializer_class = FinancialAccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return FinancialAccount.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return FinancialAccountCreateSerializer
        return FinancialAccountSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def sync_balance(self, request, pk=None):
        account = self.get_object()
        return Response({'balance': str(account.balance), 'synced_at': timezone.now()})


class UserPreferenceViewSet(viewsets.ModelViewSet):
    serializer_class = UserPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return UserPreference.objects.filter(user=self.request.user)
    
    def get_object(self):
        pref, _ = UserPreference.objects.get_or_create(user=self.request.user)
        return pref
    
    def perform_update(self, serializer):
        serializer.save(user=self.request.user)


class UserContextViewSet(viewsets.ModelViewSet):
    serializer_class = UserContextSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return UserContext.objects.filter(user=self.request.user, is_active=True)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserContextCreateSerializer
        return UserContextSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        contexts = self.get_queryset()
        facts = contexts.filter(context_type='fact')
        rules = contexts.filter(context_type='rule')
        preferences = contexts.filter(context_type='preference')
        goals = contexts.filter(context_type='goal')
        
        return Response({
            'facts': UserContextSerializer(facts, many=True).data,
            'rules': UserContextSerializer(rules, many=True).data,
            'preferences': UserContextSerializer(preferences, many=True).data,
            'goals': UserContextSerializer(goals, many=True).data,
        })


def signup(request):
    if request.user.is_authenticated:
        return redirect('chat')
    
    error = None
    email = ''
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        
        if not email:
            error = 'Email is required.'
        elif password != password2:
            error = 'Passwords do not match.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        elif User.objects.filter(email=email).exists():
            error = 'An account with this email already exists.'
        else:
            username = email.split('@')[0]
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f'{base_username}{counter}'
                counter += 1
            
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            UserProfile.objects.create(user=user)
            FinancialAccount.objects.create(
                user=user,
                name='Checking Account',
                account_type='checking',
                institution='Demo Bank',
            )
            UserPreference.objects.create(user=user)
            from transactions.seed import ensure_sample_data
            ensure_sample_data(user)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Welcome! Your sample transaction history is ready.')
            return redirect('chat')
    
    return render(request, 'registration/signup.html', {'error': error, 'email': email})


@login_required
def chat_interface(request):
    from assistant.models import Conversation, Message
    from transactions.models import Receipt
    from transactions.receipt_processing import process_receipt_record
    from assistant.services import AssistantService
    
    if request.method == 'POST':
        if 'message' in request.POST and request.POST.get('message'):
            content = request.POST.get('message')
            conversation, _ = Conversation.objects.get_or_create(user=request.user, is_active=True)
            Message.objects.create(
                conversation=conversation,
                role='user',
                content=content
            )
            service = AssistantService(request.user)
            response = service.process_message(content, conversation)
            Message.objects.create(
                conversation=conversation,
                role='assistant',
                content=response['content']
            )
        elif 'receipt_image' in request.FILES:
            image = request.FILES['receipt_image']
            conversation, _ = Conversation.objects.get_or_create(user=request.user, is_active=True)
            
            receipt = Receipt.objects.create(
                user=request.user,
                image=image,
                original_filename=image.name,
                status='uploaded'
            )
            Message.objects.create(
                conversation=conversation,
                role='user',
                content=f'[Receipt uploaded: {image.name}]',
                metadata={'receipt_id': str(receipt.id)}
            )
            
            try:
                result = process_receipt_record(receipt)
                Message.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=result
                )
            except Exception as e:
                receipt.status = 'failed'
                receipt.processing_error = str(e)
                receipt.save()
                Message.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=f"Sorry, I couldn't process your receipt: {str(e)}"
                )
        return redirect('chat')
    
    conversation, _ = Conversation.objects.get_or_create(user=request.user, is_active=True)
    messages = conversation.messages.all()[:100]
    return render(request, 'assistant/chat.html', {'messages': messages, 'conversation': conversation})