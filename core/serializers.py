from rest_framework import serializers
from .models import User, UserProfile, FinancialAccount, UserPreference, UserContext


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'date_joined', 'last_login']
        read_only_fields = ['id', 'date_joined', 'last_login']


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['email', 'username', 'first_name', 'last_name', 'password', 'password_confirm']
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['phone', 'date_of_birth', 'timezone', 'currency', 'onboarding_completed']
        read_only_fields = ['created_at', 'updated_at']


class FinancialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialAccount
        fields = [
            'id', 'name', 'account_type', 'institution', 'last_four',
            'balance', 'currency', 'is_active', 'is_manual', 'plaid_account_id',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FinancialAccountCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialAccount
        fields = [
            'name', 'account_type', 'institution', 'last_four',
            'balance', 'currency', 'is_manual', 'plaid_account_id'
        ]


class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = [
            'payday', 'excluded_categories', 'custom_categories',
            'notification_preferences', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class UserContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserContext
        fields = ['id', 'key', 'value', 'context_type', 'confidence', 'source', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserContextCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserContext
        fields = ['key', 'value', 'context_type', 'confidence', 'source']