import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from .models import UserState


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class DashboardStateTests(TestCase):
    def test_registration_verification_and_dashboard_in_different_browsers(self):
        registration_browser = Client()
        registration_browser.post(reverse('signup'), {'username': 'traveller', 'email': 'traveller@example.com',
            'password1': 'Travel-safe-pass-2049', 'password2': 'Travel-safe-pass-2049'})
        user = get_user_model().objects.get(username='traveller')
        self.assertFalse(UserState.objects.get(user=user).has_seen_dashboard)
        self.assertEqual(registration_browser.get(reverse('dashboard')).status_code, 302)
        link = re.search(r'https?://[^\s]+', mail.outbox[-1].body).group()
        verification_browser = Client()
        self.assertContains(verification_browser.post(link), 'Email verified')
        self.assertNotIn('new_user_welcome', verification_browser.session)
        self.assertFalse(UserState.objects.get(user=user).has_seen_dashboard)
        dashboard_browser = Client()
        self.assertTrue(dashboard_browser.login(username='traveller', password='Travel-safe-pass-2049'))
        self.assertContains(dashboard_browser.get(reverse('dashboard')), 'Welcome, traveller')
        self.assertTrue(UserState.objects.get(user=user).has_seen_dashboard)
        self.assertContains(dashboard_browser.get(reverse('dashboard')), 'Welcome back, traveller')
        dashboard_browser.post(reverse('logout'))
        self.assertTrue(dashboard_browser.login(username='traveller', password='Travel-safe-pass-2049'))
        self.assertContains(dashboard_browser.get(reverse('dashboard')), 'Welcome back, traveller')
        self.assertTrue(registration_browser.login(username='traveller', password='Travel-safe-pass-2049'))
        self.assertContains(registration_browser.get(reverse('dashboard')), 'Welcome back, traveller')

    def test_state_is_user_specific_and_ignores_stale_session_flag(self):
        returning = get_user_model().objects.create_user('returning')
        newcomer = get_user_model().objects.create_user('newcomer')
        UserState.objects.create(user=returning, has_seen_dashboard=True)
        self.client.force_login(returning)
        session = self.client.session
        session['new_user_welcome'] = returning.pk
        session.save()
        self.assertContains(self.client.get(reverse('dashboard')), 'Welcome back, returning')
        self.client.force_login(newcomer)
        self.assertContains(self.client.get(reverse('dashboard')), 'Welcome, newcomer')
        self.assertTrue(UserState.objects.get(user=newcomer).has_seen_dashboard)

    def test_failed_render_does_not_consume_first_visit(self):
        user = get_user_model().objects.create_user('retry')
        state = UserState.objects.create(user=user)
        self.client.force_login(user)
        with patch('assistant.views.render', side_effect=RuntimeError('Synthetic render failure')):
            with self.assertRaises(RuntimeError):
                self.client.get(reverse('dashboard'))
        state.refresh_from_db()
        self.assertFalse(state.has_seen_dashboard)
        self.assertContains(self.client.get(reverse('dashboard')), 'Welcome, retry')


class DashboardStateMigrationTests(TransactionTestCase):
    def test_existing_users_backfilled_and_new_users_default_unseen(self):
        previous = [('assistant', '0001_initial')]
        current = [('assistant', '0002_userstate')]
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        # Always restore the current schema, including when an assertion fails.
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(current))
        old_apps = executor.loader.project_state(previous).apps
        User = old_apps.get_model('auth', 'User')
        Group = old_apps.get_model('auth', 'Group')
        returning = User.objects.create(username='legacy', is_active=True)
        disabled = User.objects.create(username='disabled', is_active=False)
        pending = User.objects.create(username='pending', is_active=False)
        pending.groups.add(Group.objects.create(name='CareerPilot email verification pending'))
        executor = MigrationExecutor(connection)
        executor.migrate(current)
        apps = executor.loader.project_state(current).apps
        State = apps.get_model('assistant', 'UserState')
        self.assertTrue(State.objects.get(user_id=returning.pk).has_seen_dashboard)
        self.assertTrue(State.objects.get(user_id=disabled.pk).has_seen_dashboard)
        self.assertFalse(State.objects.get(user_id=pending.pk).has_seen_dashboard)
        new_user = apps.get_model('auth', 'User').objects.create(username='after_migration')
        self.assertFalse(State.objects.create(user_id=new_user.pk).has_seen_dashboard)
        self.assertEqual(User.objects.get(pk=returning.pk).is_active, True)
        self.assertEqual(User.objects.get(pk=disabled.pk).is_active, False)
