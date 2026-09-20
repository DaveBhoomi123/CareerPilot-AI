import re
import time
from contextlib import redirect_stdout
from io import StringIO
from urllib.parse import urlsplit
from unittest.mock import patch, Mock
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .verification import PENDING_GROUP, make_verification_token, send_verification_email
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class VerificationTests(TestCase):
    def register(self):
        response = self.client.post(reverse('signup'), {'username': 'verifyme', 'email': 'verify@example.com',
            'password1': 'Verify-safe-pass-2049', 'password2': 'Verify-safe-pass-2049'})
        self.assertRedirects(response, reverse('verification_pending'))
        self.user = get_user_model().objects.get(username='verifyme')
        return self.link()

    def link(self):
        return re.search(r'https?://[^\s]+', mail.outbox[-1].body).group()

    def test_registration_inactive_and_verification_then_login(self):
        link = self.register()
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.groups.filter(name=PENDING_GROUP).exists())
        self.assertEqual(mail.outbox[0].to, ['verify@example.com'])
        self.assertNotIn('Verify-safe-pass-2049', mail.outbox[0].body)
        self.assertNotIn('verify@example.com', link)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertFalse(self.client.login(username='verifyme', password='Verify-safe-pass-2049'))
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)
        login = self.client.post(reverse('login'), {'username': 'verifyme', 'password': 'Verify-safe-pass-2049'})
        self.assertContains(login, 'verify their email before signing in')
        self.assertContains(login, 'Resend verification email')
        self.assertContains(self.client.get(link), 'Verify my email')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)  # Email scanners cannot activate on GET.
        response = self.client.post(link)
        self.assertContains(response, 'Email verified')
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.groups.filter(name=PENDING_GROUP).exists())
        self.assertTrue(self.client.login(username='verifyme', password='Verify-safe-pass-2049'))
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        self.assertContains(Client().post(link), 'invalid or has already been used')

    def test_expiry_resend_and_single_use_for_all_links(self):
        old_link = self.register()
        with patch('django.core.signing.time.time', return_value=time.time() + 901):
            self.assertContains(self.client.post(old_link), 'This verification link has expired.')
            self.user.refresh_from_db()
            self.assertFalse(self.user.is_active)
            self.client.post(reverse('resend_verification'), {'email': 'VERIFY@example.com'})
            fresh_link = self.link()
            self.assertNotEqual(old_link, fresh_link)
            self.assertContains(self.client.post(fresh_link), 'Email verified')
            self.assertContains(self.client.post(fresh_link), 'invalid or has already been used')
        self.assertContains(self.client.post(old_link), 'invalid or has already been used')

    def test_resend_exact_pending_email_calls_sender_and_sends_one_email(self):
        old_link = self.register()
        mail.outbox.clear()
        with patch('assistant.auth_views.send_verification_email', wraps=send_verification_email) as sender:
            response = self.client.post(reverse('resend_verification'), {'email': self.user.email})
        self.assertRedirects(response, reverse('verification_pending'))
        sender.assert_called_once()
        self.assertEqual(sender.call_args.args[1].pk, self.user.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        fresh_link = self.link()
        self.assertIn('/accounts/verify/', fresh_link)
        self.assertNotEqual(fresh_link, old_link)
        self.assertContains(self.client.post(fresh_link), 'Email verified')
        self.assertContains(self.client.post(old_link), 'invalid or has already been used')

    def test_resend_console_output_contains_fresh_link_with_fifteen_minute_expiry(self):
        old_link = self.register()
        output = StringIO()
        issued_at = int(time.time())
        with override_settings(DEBUG=True, EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend'):
            with redirect_stdout(output), patch('django.core.signing.time.time', return_value=issued_at):
                response = self.client.post(reverse('resend_verification'), {'email': self.user.email})
        self.assertRedirects(response, reverse('verification_pending'))
        console_email = output.getvalue()
        self.assertEqual(console_email.count('Subject: Verify your CareerPilot AI email'), 1)
        self.assertIn('To: ' + self.user.email, console_email)
        fresh_link = re.search(r'https?://[^\s]+', console_email).group()
        self.assertNotEqual(fresh_link, old_link)
        with patch('django.core.signing.time.time', return_value=issued_at + 899):
            self.assertContains(self.client.get(fresh_link), 'Verify my email')
        with patch('django.core.signing.time.time', return_value=issued_at + 901):
            self.assertContains(self.client.get(fresh_link), 'This verification link has expired.')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_resend_unknown_active_and_legacy_inactive_are_generic(self):
        active = get_user_model().objects.create_user('active', email='active@example.com', password='Existing-safe-2049')
        disabled = get_user_model().objects.create_user('disabled', email='disabled@example.com', is_active=False)
        self.register()
        known = self.client.post(reverse('resend_verification'), {'email': 'verify@example.com'}, follow=True)
        count = len(mail.outbox)
        for address in ['unknown@example.com', active.email, disabled.email]:
            with patch('assistant.auth_views.send_verification_email', wraps=send_verification_email) as sender:
                response = self.client.post(reverse('resend_verification'), {'email': address}, follow=True)
            sender.assert_not_called()
            self.assertEqual(response.content, known.content)
            self.assertContains(response, 'If an account is awaiting verification for this email')
            self.assertEqual(len(mail.outbox), count)
        token = make_verification_token(disabled)
        url = reverse('verify_email', kwargs={'uidb64': urlsafe_base64_encode(force_bytes(disabled.pk)), 'token': token})
        self.assertContains(self.client.post(url), 'invalid or has already been used')
        disabled.refresh_from_db()
        self.assertFalse(disabled.is_active)
        self.assertTrue(self.client.login(username='active', password='Existing-safe-2049'))

    def test_csrf_tampering_and_no_token_storage(self):
        link = self.register()
        self.assertContains(self.client.get(link.rstrip('/') + 'tampered/'), 'invalid or has already been used')
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(reverse('resend_verification'), {'email': self.user.email}).status_code, 403)
        self.assertEqual(strict.post(link).status_code, 403)
        response = strict.get(link)
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
        self.assertIn('no-store', response['Cache-Control'])
        token = link.rstrip('/').split('/')[-1]
        self.assertNotIn(token, str(dict(strict.session)))
        self.assertNotIn(token, str(self.user.__dict__))
        self.assertContains(strict.post(link, {'csrfmiddlewaretoken': strict.cookies['csrftoken'].value}), 'Email verified')

    def test_changed_email_invalidates_link_and_pending_cannot_reset_password(self):
        link = self.register()
        before = len(mail.outbox)
        self.client.post(reverse('password_reset'), {'email': self.user.email})
        self.assertEqual(len(mail.outbox), before)
        self.user.email = 'changed@example.com'
        self.user.save(update_fields=['email'])
        self.assertContains(self.client.post(link), 'invalid or has already been used')

    @override_settings(ALLOWED_HOSTS=['127.0.0.1', 'localhost', 'careerpilot-test.onrender.com'],
        CSRF_TRUSTED_ORIGINS=[], SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_confirmation_browser_origins_and_csrf_enforcement(self):
        from django.contrib.auth.models import Group
        for index, origin in enumerate(['http://127.0.0.1:8000', 'http://localhost:8000',
                                       'https://careerpilot-test.onrender.com']):
            with self.subTest(origin=origin):
                user = get_user_model().objects.create_user(
                    f'origin{index}', email=f'origin{index}@example.com', is_active=False)
                user.groups.add(Group.objects.get_or_create(name=PENDING_GROUP)[0])
                path = reverse('verify_email', kwargs={
                    'uidb64': urlsafe_base64_encode(force_bytes(user.pk)),
                    'token': make_verification_token(user)})
                headers = {'HTTP_HOST': urlsplit(origin).netloc}
                if origin.startswith('https:'):
                    headers['HTTP_X_FORWARDED_PROTO'] = 'https'
                browser = Client(enforce_csrf_checks=True)
                page = browser.get(path, **headers)
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page['Referrer-Policy'], 'same-origin')
                self.assertContains(page, f'action="{path}"')
                csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',
                                 page.content.decode()).group(1)
                # Reproduce the reported failure even with a valid form token.
                for bad_origin in ['null', 'https://untrusted.example']:
                    rejected = browser.post(path, {'csrfmiddlewaretoken': csrf},
                                            HTTP_ORIGIN=bad_origin, **headers)
                    self.assertEqual(rejected.status_code, 403)
                    user.refresh_from_db()
                    self.assertFalse(user.is_active)
                for data in [{}, {'csrfmiddlewaretoken': 'invalid'}]:
                    rejected = browser.post(path, data, HTTP_ORIGIN=origin, **headers)
                    self.assertEqual(rejected.status_code, 403)
                    user.refresh_from_db()
                    self.assertFalse(user.is_active)
                accepted = browser.post(path, {'csrfmiddlewaretoken': csrf},
                                        HTTP_ORIGIN=origin, **headers)
                self.assertContains(accepted, 'Email verified')
                user.refresh_from_db()
                self.assertTrue(user.is_active)
                reused = browser.post(path, {'csrfmiddlewaretoken': csrf},
                                      HTTP_ORIGIN=origin, **headers)
                self.assertContains(reused, 'invalid or has already been used')

    @patch('assistant.verification.send_mail', side_effect=RuntimeError('mail unavailable'))
    def test_delivery_failure_keeps_account_pending(self, send):
        with self.assertLogs('assistant.verification', level='WARNING'):
            response = self.client.post(reverse('signup'), {'username':'mailfailed', 'email':'mailfailed@example.com',
                'password1':'Mail-safe-pass-2049', 'password2':'Mail-safe-pass-2049'})
        self.assertRedirects(response, reverse('verification_pending'))
        self.assertFalse(get_user_model().objects.get(username='mailfailed').is_active)


@override_settings(BREVO_API_KEY='synthetic-brevo-key',
    DEFAULT_FROM_EMAIL='CareerPilot AI <sender@example.com>',
    EMAIL_BACKEND='assistant.email_backends.BrevoEmailBackend')
class HttpEmailBackendTests(TestCase):
    def setUp(self):
        self.patcher = patch('assistant.email_backends.requests.post')
        self.post = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.response = Mock(status_code=201)
        self.post.return_value.__enter__.return_value = self.response

    def test_send_mail_payload_and_authentication(self):
        from django.core.mail import send_mail
        self.assertEqual(send_mail('Verify email', 'Synthetic body', None, ['recipient@example.com']), 1)
        self.post.assert_called_once_with('https://api.brevo.com/v3/smtp/email',
            headers={'api-key': 'synthetic-brevo-key', 'Accept': 'application/json'},
            json={'sender': {'email': 'sender@example.com', 'name': 'CareerPilot AI'},
                  'to': [{'email': 'recipient@example.com'}], 'subject': 'Verify email',
                  'textContent': 'Synthetic body'}, timeout=(5, 10), allow_redirects=False)

    def test_html_alternative_and_recipient_fields(self):
        from django.core.mail import EmailMultiAlternatives
        message = EmailMultiAlternatives('Hello', 'Plain body', to=['Reader <reader@example.com>'],
            cc=['copy@example.com'], bcc=['hidden@example.com'], reply_to=['reply@example.com'])
        message.attach_alternative('<p>Hello</p>', 'text/html')
        self.assertEqual(message.send(), 1)
        payload = self.post.call_args.kwargs['json']
        self.assertEqual(payload['textContent'], 'Plain body')
        self.assertEqual(payload['htmlContent'], '<p>Hello</p>')
        self.assertEqual(payload['to'], [{'email': 'reader@example.com', 'name': 'Reader'}])
        self.assertEqual(payload['cc'], [{'email': 'copy@example.com'}])
        self.assertEqual(payload['bcc'], [{'email': 'hidden@example.com'}])
        self.assertEqual(payload['replyTo'], {'email': 'reply@example.com'})

    def test_api_rejections_never_count_as_sent(self):
        from django.core.mail import send_mail
        for status in [302, 400, 401, 429, 500]:
            with self.subTest(status=status), self.assertLogs('assistant.email_backends') as logs:
                self.response.status_code = status
                self.response.text = 'synthetic-brevo-key private provider response'
                with self.assertRaisesMessage(RuntimeError, f'HTTP {status}'):
                    send_mail('Subject', 'Body', None, ['recipient@example.com'])
                self.assertEqual(send_mail('Subject', 'Body', None, ['recipient@example.com'], fail_silently=True), 0)
                self.assertNotIn('synthetic-brevo-key', str(logs.output))
                self.assertNotIn('private provider response', str(logs.output))

    @override_settings(BREVO_API_KEY='')
    def test_missing_api_key_fails_before_http(self):
        from django.core.mail import send_mail
        with self.assertLogs('assistant.email_backends'):
            with self.assertRaisesMessage(RuntimeError, 'requires BREVO_API_KEY'):
                send_mail('Subject', 'Body', None, ['recipient@example.com'])
            self.assertEqual(send_mail('Subject', 'Body', None, ['recipient@example.com'], fail_silently=True), 0)
        self.post.assert_not_called()

    def test_transport_failure_does_not_expose_secrets(self):
        import requests
        from django.core.mail import send_mail
        self.post.side_effect = requests.Timeout('synthetic-brevo-key private request')
        with self.assertLogs('assistant.email_backends') as logs:
            with self.assertRaisesMessage(RuntimeError, 'Brevo HTTPS request failed') as error:
                send_mail('Subject', 'Body', None, ['recipient@example.com'])
        self.assertNotIn('synthetic-brevo-key', str(error.exception) + str(logs.output))

    def test_empty_messages_and_no_recipients_do_not_send(self):
        from .email_backends import BrevoEmailBackend
        from django.core.mail import EmailMessage
        self.assertEqual(BrevoEmailBackend().send_messages([]), 0)
        self.assertEqual(BrevoEmailBackend().send_messages([EmailMessage('Subject', 'Body')]), 0)
        self.post.assert_not_called()
