import re
from datetime import timedelta
from urllib.parse import urlsplit
from unittest.mock import patch
from django.core import mail
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PasswordRecoveryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            'returning', email='registered@example.com', password='Old-safe-pass-2049')

    def registration(self, **overrides):
        data = {'username': 'newcandidate', 'email': 'new@example.com',
                'password1': 'Fresh-safe-pass-2049', 'password2': 'Fresh-safe-pass-2049'}
        data.update(overrides)
        return self.client.post(reverse('signup'), data)

    def request_link(self, **request_options):
        response = self.client.post(reverse('password_reset'),
            {'email': self.user.email}, **request_options)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        return re.search(r'https?://[^\s]+', mail.outbox[0].body).group()

    def test_registration_requires_valid_unique_email(self):
        for email in ['', 'not-an-email', 'registered@example.com', 'REGISTERED@example.com']:
            with self.subTest(email=email):
                response = self.registration(email=email)
                self.assertEqual(response.status_code, 200)
                self.assertIn('email', response.context['form'].errors)
                self.assertFalse(get_user_model().objects.filter(username='newcandidate').exists())
        self.assertContains(self.registration(email='Registered@example.com'), 'An account with this email already exists.')
        self.assertEqual(self.registration(email=' New@Example.COM ').status_code, 302)
        self.assertEqual(get_user_model().objects.get(username='newcandidate').email, 'new@example.com')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'registered@example.com')

    def test_registration_field_order_and_password_validation(self):
        response = self.client.get(reverse('signup'))
        self.assertEqual(list(response.context['form'].fields), ['username', 'email', 'password1', 'password2'])
        for data in [{'password1': '123', 'password2': '123'}, {'password2': 'different'}]:
            self.assertTrue(self.registration(**data).context['form'].errors)

    def test_reset_pages_and_login_link(self):
        self.assertContains(self.client.get(reverse('login')), 'Forgot password?')
        self.assertEqual(self.client.get(reverse('password_reset')).status_code, 200)
        self.assertContains(self.client.get(reverse('password_reset_complete')), 'Your password is updated')

    def test_registered_and_unknown_email_have_identical_confirmation(self):
        known = self.client.post(reverse('password_reset'), {'email': 'REGISTERED@example.com'}, follow=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['registered@example.com'])
        self.assertNotIn('Old-safe-pass-2049', mail.outbox[0].body)
        unknown = self.client.post(reverse('password_reset'), {'email': 'unknown@example.com'}, follow=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(known.redirect_chain, unknown.redirect_chain)
        self.assertEqual(known.content, unknown.content)
        self.assertContains(unknown, 'If an account exists for this email, a password reset link has been sent.')

    def test_existing_user_without_email_is_unchanged(self):
        user = get_user_model().objects.create_user('legacy', password='Legacy-safe-pass-2049')
        response = self.client.post(reverse('password_reset'), {'email': 'legacy@example.com'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        user.refresh_from_db()
        self.assertEqual(user.email, '')
        self.assertTrue(self.client.login(username='legacy', password='Legacy-safe-pass-2049'))

    def test_valid_link_updates_password_and_cannot_be_reused(self):
        link = self.request_link()
        page = self.client.get(link)
        self.assertTrue(page.context['validlink'])
        self.assertEqual(page['Referrer-Policy'], 'same-origin')
        self.assertIn('no-store', page['Cache-Control'])
        self.assertNotIn('_password_reset_token', self.client.session)
        self.assertNotIn(link.rstrip('/').split('/')[-1], str(dict(self.client.session)))
        response = self.client.post(link, {'new_password1': 'New-safe-pass-2050', 'new_password2': 'New-safe-pass-2050'})
        self.assertRedirects(response, reverse('password_reset_complete'))
        self.assertFalse(self.client.get(link).context['validlink'])
        self.assertFalse(Client().get(link).context['validlink'])
        self.assertFalse(self.client.login(username='returning', password='Old-safe-pass-2049'))
        self.assertTrue(self.client.login(username='returning', password='New-safe-pass-2050'))

    def test_invalid_expired_token_and_weak_password_rejected(self):
        link = self.request_link()
        bad_link = link.rstrip('/') + 'invalid/'
        self.assertFalse(self.client.get(bad_link).context['validlink'])
        response = self.client.post(link, {'new_password1': '123', 'new_password2': '123'})
        self.assertTrue(response.context['form'].errors)
        later = default_token_generator._now() + timedelta(seconds=901)
        with patch.object(default_token_generator, '_now', return_value=later):
            self.assertFalse(self.client.get(link).context['validlink'])
            self.assertFalse(self.client.post(link, {'new_password1': 'Never-used-pass-2050', 'new_password2': 'Never-used-pass-2050'}).context['validlink'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-safe-pass-2049'))

    def test_csrf_protects_request_and_password_change(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(reverse('password_reset'), {'email': self.user.email}).status_code, 403)
        link = self.request_link()
        strict.get(link)
        self.assertEqual(strict.post(link, {'new_password1': 'New-safe-pass-2050', 'new_password2': 'New-safe-pass-2050'}).status_code, 403)
        response = strict.post(link, {'new_password1': 'New-safe-pass-2050', 'new_password2': 'New-safe-pass-2050', 'csrfmiddlewaretoken': strict.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 302)

    @override_settings(ALLOWED_HOSTS=['127.0.0.1', 'localhost', 'careerpilot-example.onrender.com'],
        CSRF_TRUSTED_ORIGINS=[], SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_confirmation_same_origin_post_with_csrf_enforced(self):
        for origin in ['http://127.0.0.1:8000', 'http://localhost:8000',
                       'https://careerpilot-example.onrender.com']:
            with self.subTest(origin=origin):
                self.user.set_password('Old-safe-pass-2049')
                self.user.save(update_fields=['password'])
                mail.outbox.clear()
                headers = {'HTTP_HOST': urlsplit(origin).netloc}
                if origin.startswith('https:'):
                    headers['HTTP_X_FORWARDED_PROTO'] = 'https'
                path = urlsplit(self.request_link(**headers)).path
                strict = Client(enforce_csrf_checks=True)
                page = strict.get(path, **headers)
                self.assertEqual(page.status_code, 200)
                self.assertTrue(page.context['validlink'])
                self.assertEqual(page['Referrer-Policy'], 'same-origin')
                self.assertContains(page, f'action="{path}"')
                csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',
                                 page.content.decode()).group(1)
                data = {'new_password1': 'New-safe-pass-2050', 'new_password2': 'New-safe-pass-2050',
                        'csrfmiddlewaretoken': csrf}
                for bad_origin in ['null', 'https://untrusted.example']:
                    self.assertEqual(strict.post(path, data, HTTP_ORIGIN=bad_origin, **headers).status_code, 403)
                for token in ['', 'invalid']:
                    self.assertEqual(strict.post(path, {**data, 'csrfmiddlewaretoken': token},
                                                HTTP_ORIGIN=origin, **headers).status_code, 403)
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password('Old-safe-pass-2049'))
                response = strict.post(path, data, HTTP_ORIGIN=origin, **headers)
                self.assertRedirects(response, reverse('password_reset_complete'), fetch_redirect_response=False)
                self.assertFalse(strict.login(username=self.user.username, password='Old-safe-pass-2049'))
                self.assertTrue(strict.login(username=self.user.username, password='New-safe-pass-2050'))
                # Use an anonymous client: login rotates the CSRF cookie.
                reuse = Client(enforce_csrf_checks=True)
                reuse.cookies['csrftoken'] = page.cookies['csrftoken'].value
                rejected = reuse.post(path, {**data, 'new_password1': 'Reused-safe-pass-2051',
                                             'new_password2': 'Reused-safe-pass-2051'},
                                      HTTP_ORIGIN=origin, **headers)
                self.assertEqual(rejected.status_code, 200)
                self.assertFalse(rejected.context['validlink'])
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password('New-safe-pass-2050'))

    @override_settings(ALLOWED_HOSTS=['localhost'], CSRF_TRUSTED_ORIGINS=[])
    def test_expired_reset_post_with_valid_csrf_is_rejected(self):
        headers = {'HTTP_HOST': 'localhost:8000'}
        path = urlsplit(self.request_link(**headers)).path
        strict = Client(enforce_csrf_checks=True)
        strict.get(path, **headers)
        now = default_token_generator._now()
        with patch.object(default_token_generator, '_now', return_value=now + timedelta(seconds=899)):
            self.assertTrue(strict.get(path, **headers).context['validlink'])
        with patch.object(default_token_generator, '_now', return_value=now + timedelta(seconds=901)):
            response = strict.post(path, {'new_password1': 'Expired-safe-pass-2050',
                'new_password2': 'Expired-safe-pass-2050', 'csrfmiddlewaretoken': strict.cookies['csrftoken'].value},
                HTTP_ORIGIN='http://localhost:8000', **headers)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context['validlink'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-safe-pass-2049'))

    @override_settings(ALLOWED_HOSTS=['localhost'])
    def test_localhost_link_preserves_port(self):
        self.assertTrue(self.request_link(HTTP_HOST='localhost:8000').startswith('http://localhost:8000/'))

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['careerpilot-example.onrender.com'],
        SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_render_proxy_generates_https_link(self):
        link = self.request_link(HTTP_HOST='careerpilot-example.onrender.com', HTTP_X_FORWARDED_PROTO='https')
        self.assertTrue(link.startswith('https://careerpilot-example.onrender.com/'))

    def test_inactive_and_unusable_password_accounts_receive_no_email(self):
        self.user.is_active = False
        self.user.save()
        self.client.post(reverse('password_reset'), {'email': self.user.email})
        self.user.is_active = True
        self.user.set_unusable_password()
        self.user.save()
        self.client.post(reverse('password_reset'), {'email': self.user.email})
        self.assertEqual(len(mail.outbox), 0)
