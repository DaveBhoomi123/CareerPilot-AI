"""Optional HTTPS email transport for hosts that block SMTP."""
import requests
import logging
from email.utils import parseaddr
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

logger = logging.getLogger(__name__)


def _address(value):
    name, address = parseaddr(value)
    validate_email(address)
    return {'email': address, **({'name': name} if name else {})}


class BrevoDeliveryError(RuntimeError):
    """A safe diagnostic without provider response contents."""


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages or []:
            if not message.recipients():
                continue
            try:
                if not getattr(settings, 'BREVO_API_KEY', ''):
                    raise ValueError('Brevo email configuration requires BREVO_API_KEY.')
                if message.attachments:
                    raise ValueError('Brevo email backend does not support attachments.')
                # Validate Django headers, including protection against newlines.
                message.message()
                payload = {'sender': _address(message.from_email or settings.DEFAULT_FROM_EMAIL),
                           'subject': message.subject,
                           'htmlContent' if message.content_subtype == 'html' else 'textContent': message.body}
                for field in ('to', 'cc', 'bcc'):
                    addresses = getattr(message, field)
                    if addresses:
                        payload[field] = [_address(address) for address in addresses]
                if message.reply_to:
                    if len(message.reply_to) != 1:
                        raise ValueError('Brevo supports one reply-to address.')
                    payload['replyTo'] = _address(message.reply_to[0])
                for content, mimetype in getattr(message, 'alternatives', []):
                    if mimetype == 'text/html':
                        payload['htmlContent'] = content
                with requests.post('https://api.brevo.com/v3/smtp/email',
                    headers={'api-key': settings.BREVO_API_KEY, 'Accept': 'application/json'},
                    json=payload,
                    timeout=(5, 10), allow_redirects=False) as response:
                    if response.status_code != 201:
                        raise BrevoDeliveryError(f'Brevo rejected email (HTTP {response.status_code}). Check sender, API configuration and quota.')
                sent += 1
            except (requests.RequestException, ValueError, ValidationError, BrevoDeliveryError) as exc:
                # Never include raw exceptions, response bodies, addresses or tokens.
                if isinstance(exc, requests.RequestException):
                    reason = 'Brevo HTTPS request failed. Check connectivity and provider availability.'
                elif isinstance(exc, BrevoDeliveryError):
                    reason = str(exc)  # Only our status-only error above.
                elif not getattr(settings, 'BREVO_API_KEY', ''):
                    reason = 'Brevo email configuration requires BREVO_API_KEY.'
                else:
                    reason = 'Brevo email message is invalid or unsupported. Check sender and message configuration.'
                logger.warning(reason)
                if not self.fail_silently:
                    raise RuntimeError(reason) from None
        return sent
