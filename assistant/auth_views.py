"""Password reset confirmation without saving the raw token in the session."""
from django.contrib.auth.views import PasswordResetConfirmView
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic.edit import FormView


class StatelessPasswordResetConfirmView(PasswordResetConfirmView):
    @method_decorator(sensitive_post_parameters())
    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def dispatch(self, request, *args, **kwargs):
        self.user = self.get_user(kwargs['uidb64'])
        self.validlink = self.user is not None and self.token_generator.check_token(
            self.user, kwargs['token'])
        if self.validlink:
            response = FormView.dispatch(self, request, *args, **kwargs)
        else:
            response = self.render_to_response(self.get_context_data())
        # The token stays in the email URL, never in a session or custom table.
        # Preserve Origin for the form POST without leaking the URL to other sites.
        response['Referrer-Policy'] = 'same-origin'
        response['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    def form_valid(self, form):
        form.save()  # Django SetPasswordForm hashes the new password.
        return FormView.form_valid(self, form)


# Use existing auth tables to identify only newly registered pending accounts.
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_http_methods
from .forms import ResendVerificationForm
from .verification import PENDING_GROUP, verification_salt, send_verification_email


@never_cache
@csrf_protect
@require_http_methods(['GET', 'POST'])
def verify_email(request, uidb64, token):
    status = 'invalid'
    with transaction.atomic():
        try:
            pk = urlsafe_base64_decode(uidb64).decode()
            user = get_user_model().objects.select_for_update().get(pk=pk)
        except (ValueError, TypeError, OverflowError, UnicodeError, get_user_model().DoesNotExist):
            user = None
        if user is not None and not user.is_active and user.groups.filter(name=PENDING_GROUP).exists():
            try:
                signing.loads(token, salt=verification_salt(user), max_age=settings.EMAIL_VERIFICATION_TIMEOUT)
            except signing.SignatureExpired:
                status = 'expired'
            except signing.BadSignature:
                pass
            else:
                status = 'confirm'
                if request.method == 'POST':
                    # Conditional update also prevents concurrent token reuse.
                    updated = get_user_model().objects.filter(pk=user.pk, is_active=False).update(is_active=True)
                    if updated:
                        user.groups.remove(*user.groups.filter(name=PENDING_GROUP))
                        request.session['new_user_welcome'] = user.pk
                        status = 'success'
                    else:
                        status = 'invalid'
    response = render(request, 'registration/verification_result.html', {'verification_status': status})
    # Preserve Origin on same-origin form POSTs without leaking the token URL
    # to other sites. no-referrer can make browsers send Origin: null.
    response['Referrer-Policy'] = 'same-origin'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@csrf_protect
@require_http_methods(['GET', 'POST'])
def resend_verification(request):
    form = ResendVerificationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        users = get_user_model().objects.filter(email__iexact=form.cleaned_data['email'],
            is_active=False, groups__name=PENDING_GROUP).distinct()
        for user in users:
            send_verification_email(request, user)
        return redirect('verification_pending')
    return render(request, 'registration/resend_verification.html', {'form': form})
