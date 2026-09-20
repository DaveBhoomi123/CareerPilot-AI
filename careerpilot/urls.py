from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from assistant import views
from assistant.auth_views import StatelessPasswordResetConfirmView, verify_email, resend_verification
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/verification/pending/', TemplateView.as_view(template_name='registration/verification_pending.html'), name='verification_pending'),
    path('accounts/verification/resend/', resend_verification, name='resend_verification'),
    path('accounts/verify/<uidb64>/<token>/', verify_email, name='verify_email'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/password-reset/', auth_views.PasswordResetView.as_view(
        email_template_name='registration/password_reset_email.txt',
        subject_template_name='registration/password_reset_subject.txt'), name='password_reset'),
    path('accounts/password-reset/sent/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', StatelessPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('accounts/reset/complete/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    path('accounts/password/', auth_views.PasswordChangeView.as_view(template_name='form.html', success_url='/dashboard/', extra_context={'title': 'Change password'}), name='password_change'),
    path('', include('assistant.urls')),
]
