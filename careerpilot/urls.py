from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from assistant import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/password/', auth_views.PasswordChangeView.as_view(template_name='form.html', success_url='/dashboard/', extra_context={'title': 'Change password'}), name='password_change'),
    path('', include('assistant.urls')),
]
