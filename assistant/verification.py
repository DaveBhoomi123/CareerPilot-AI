"""Email verification using Django timestamped signing; no token persistence."""
import logging
import secrets
from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

PENDING_GROUP = 'CareerPilot email verification pending'
logger = logging.getLogger(__name__)


def verification_salt(user):
    # Salt binds signatures to this account and its current email/password.
    # These values are NOT included in the URL or signed payload.
    return f'careerpilot.verify:{user.pk}:{user.email}:{user.password}'


def make_verification_token(user):
    return signing.dumps({'nonce': secrets.token_urlsafe(16)}, salt=verification_salt(user))


def send_verification_email(request, user):
    link = request.build_absolute_uri(reverse('verify_email', kwargs={
        'uidb64': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': make_verification_token(user),
    }))
    body = render_to_string('registration/verification_email.txt', {'user': user, 'verification_url': link})
    try:
        send_mail('Verify your CareerPilot AI email', body, settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception:
        # No addresses, tokens, credentials or raw provider errors in logs.
        logger.warning('Verification email delivery failed; account remains pending.')
