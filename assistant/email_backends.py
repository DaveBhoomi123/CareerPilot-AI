"""Optional HTTPS email transport for hosts that block SMTP."""
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages or []:
            if not message.recipients():
                continue
            try:
                if not settings.RESEND_API_KEY:
                    raise ValueError('Missing email provider configuration')
                with requests.post('https://api.resend.com/emails',
                    headers={'Authorization': f'Bearer {settings.RESEND_API_KEY}'},
                    json={'from': message.from_email, 'to': message.to,
                          'subject': message.subject, 'text': message.body},
                    timeout=(5, 10), allow_redirects=False) as response:
                    if not 200 <= response.status_code < 300:
                        raise ValueError('Email provider rejected delivery')
                sent += 1
            except (requests.RequestException, ValueError):
                if not self.fail_silently:
                    raise RuntimeError('Email delivery failed. Check server email configuration.') from None
        return sent
