from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from core.views import chat_interface, signup

urlpatterns = [
    path('', chat_interface, name='chat'),
    path('signup/', signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
]