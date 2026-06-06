from django.contrib import admin
from .models import User, UserProfile, FinancialAccount, UserPreference, UserContext


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'username', 'first_name', 'last_name', 'is_staff', 'created_at']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'created_at']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'currency', 'timezone', 'onboarding_completed']
    search_fields = ['user__email', 'user__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(FinancialAccount)
class FinancialAccountAdmin(admin.ModelAdmin):
    list_display = ['user', 'name', 'account_type', 'institution', 'last_four', 'balance', 'is_active', 'is_manual']
    list_filter = ['account_type', 'is_active', 'is_manual', 'currency']
    search_fields = ['user__email', 'name', 'institution', 'last_four']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'payday']
    search_fields = ['user__email']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UserContext)
class UserContextAdmin(admin.ModelAdmin):
    list_display = ['user', 'key', 'context_type', 'confidence', 'is_active', 'created_at']
    list_filter = ['context_type', 'is_active']
    search_fields = ['user__email', 'key', 'value']
    readonly_fields = ['created_at', 'updated_at']