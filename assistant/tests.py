import io
import json
import runpy
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch, Mock
import requests
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from .models import Resume, Analysis, Application, Interview, Question, AIUsage
from .services.extraction import extract_resume
from .services.matching import match_resume, skills_in
from .services.ai import generate, AIUnavailable

RESUME = 'Python Django SQL Git HTML CSS Bootstrap developer. Built REST APIs and tested a student project with SQLite.'
JOB = 'Seeking a Python Django developer with SQL Git Docker PostgreSQL and communication skills to build REST APIs.'

@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}, GEMINI_API_KEY='', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class WorkflowTests(TestCase):
    def setUp(self):
        sleeper = patch('assistant.services.ai.time.sleep')
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)
        self.user = get_user_model().objects.create_user('candidate', password='Example-test-9482')
        self.other = get_user_model().objects.create_user('other', password='Example-test-9482')
        self.client.force_login(self.user)
        self.resume = Resume.objects.create(owner=self.user, title='Backend resume', text=RESUME)
        self.analysis = Analysis.objects.create(owner=self.user, resume=self.resume, role='Django Developer', job_description=JOB, **match_resume(RESUME, JOB))

    def verify_registered_user(self, username):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        from .verification import make_verification_token
        user = get_user_model().objects.get(username=username)
        url = reverse('verify_email', kwargs={'uidb64': urlsafe_base64_encode(force_bytes(user.pk)), 'token': make_verification_token(user)})
        self.assertContains(self.client.post(url), 'Email verified')

    def test_auth_signup_login_logout(self):
        self.client.logout()
        self.assertEqual(self.client.get('/dashboard/').status_code, 302)
        self.assertEqual(self.client.get('/').status_code, 200)
        response = self.client.post('/accounts/signup/', {'username': 'newperson', 'email': 'newperson@example.com', 'password1': 'New-person-test-2049', 'password2': 'New-person-test-2049'})
        self.assertRedirects(response, reverse('verification_pending'))
        self.verify_registered_user('newperson')
        self.assertTrue(self.client.login(username='newperson', password='New-person-test-2049'))
        self.assertEqual(self.client.get('/accounts/logout/').status_code, 405)
        self.assertEqual(self.client.post('/accounts/logout/').status_code, 302)
        self.assertTrue(self.client.login(username='newperson', password='New-person-test-2049'))

    def test_new_user_dashboard_welcome_is_shown_once(self):
        self.client.logout()
        response = self.client.post(reverse('signup'), {
            'username': 'newperson', 'email': 'newperson@example.com', 'password1': 'New-person-test-2049',
            'password2': 'New-person-test-2049',
        }, follow=True)
        self.verify_registered_user('newperson')
        response = self.client.post(reverse('login'), {'username': 'newperson', 'password': 'New-person-test-2049'}, follow=True)
        self.assertContains(response, 'Welcome, newperson')
        self.assertNotContains(response, 'Welcome back, newperson')
        self.assertNotIn('new_user_welcome', self.client.session)
        self.assertContains(self.client.get(reverse('dashboard')), 'Welcome back, newperson')
        self.client.post(reverse('logout'))
        response = self.client.post(reverse('login'), {
            'username': 'newperson', 'password': 'New-person-test-2049',
        }, follow=True)
        self.assertContains(response, 'Welcome back, newperson')

    def test_existing_user_dashboard_welcome(self):
        self.assertContains(self.client.get(reverse('dashboard')), 'Welcome back, candidate')

    def test_sidebar_logout_secure_login_cycle(self):
        strict = Client(enforce_csrf_checks=True)
        login_url = reverse('login')
        dashboard_url = reverse('dashboard')
        logout_url = reverse('logout')

        def sign_in():
            self.assertEqual(strict.get(login_url).status_code, 200)
            response = strict.post(login_url, {
                'username': 'candidate', 'password': 'Example-test-9482',
                'csrfmiddlewaretoken': strict.cookies['csrftoken'].value,
            })
            self.assertRedirects(response, dashboard_url)

        sign_in()
        dashboard = strict.get(dashboard_url)
        self.assertContains(dashboard, 'class="logout-form"')
        self.assertContains(dashboard, f'action="{logout_url}"')
        self.assertContains(dashboard, 'Logout</button>')
        self.assertEqual(strict.get(logout_url).status_code, 405)
        self.assertEqual(strict.post(logout_url).status_code, 403)
        self.assertEqual(strict.get(dashboard_url).status_code, 200)
        response = strict.post(logout_url, {
            'csrfmiddlewaretoken': strict.cookies['csrftoken'].value,
        })
        self.assertRedirects(response, reverse('home'))
        self.assertNotIn('_auth_user_id', strict.session)
        self.assertRedirects(strict.get(dashboard_url), f'{login_url}?next={dashboard_url}')
        self.assertNotContains(strict.get(reverse('home')), 'class="logout-form"')
        sign_in()
        self.assertEqual(strict.get(dashboard_url).status_code, 200)

    def test_all_pages_render(self):
        for url in ['/dashboard/', '/resumes/', '/resumes/new/', f'/resumes/{self.resume.pk}/edit/', '/analyses/', '/analyses/new/', f'/analyses/{self.analysis.pk}/', '/applications/', '/applications/new/', '/interviews/', '/accounts/password/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_upload_analyze_and_fallback(self):
        response = self.client.post('/resumes/new/', {'title': 'Upload', 'upload': SimpleUploadedFile('resume.txt', RESUME.encode())})
        self.assertRedirects(response, '/resumes/')
        resume = Resume.objects.get(title='Upload')
        self.assertEqual(resume.text, RESUME)
        response = self.client.post('/analyses/new/', {'resume': resume.pk, 'role': 'Engineer', 'job_description': JOB})
        obj = Analysis.objects.get(role='Engineer')
        self.assertRedirects(response, reverse('analysis_detail', args=[obj.pk]))
        self.assertIn('Python', obj.matched)
        self.assertIn('Docker', obj.missing)
        self.client.post(reverse('suggestions', args=[obj.pk]), {'consent': 'yes'})
        obj.refresh_from_db()
        self.assertEqual(obj.suggestion_source, 'Local guidance')
        self.assertIn('rule-based', obj.suggestions)

    def test_application_crud_filter(self):
        data = {'company': 'Acme', 'role': 'Engineer', 'status': 'applied', 'applied_on': '2026-09-18', 'notes': 'Follow up', 'url': 'https://example.com/jobs'}
        self.assertRedirects(self.client.post('/applications/new/', data), '/applications/')
        app = Application.objects.get(company='Acme')
        data['status'] = 'interview'
        self.client.post(reverse('application_edit', args=[app.pk]), data)
        self.assertContains(self.client.get('/applications/?status=interview&q=Acme'), 'Acme')
        self.assertNotContains(self.client.get('/applications/?status=offer'), 'Acme')
        url = reverse('application_delete', args=[app.pk])
        self.client.get(url)
        self.assertTrue(Application.objects.filter(pk=app.pk).exists())
        self.client.post(url)
        self.assertFalse(Application.objects.filter(pk=app.pk).exists())

    def test_interview_answers_and_validation(self):
        self.client.post(reverse('interview_start', args=[self.analysis.pk]))
        interview = Interview.objects.get()
        self.assertEqual(interview.questions.count(), 5)
        self.assertEqual(self.client.get(reverse('interview_detail', args=[interview.pk])).status_code, 200)
        question = interview.questions.first()
        url = reverse('answer', args=[question.pk])
        self.assertEqual(self.client.post(url, {'answer': 'tiny'}).status_code, 400)
        self.client.post(url, {'answer': 'I built a Django project and tested authenticated views to prevent access to another account.'})
        question.refresh_from_db()
        self.assertEqual(question.source, 'Local checklist')
        self.assertTrue(question.feedback)

    def test_owner_isolation(self):
        app = Application.objects.create(owner=self.user, company='Private', role='Engineer')
        interview = Interview.objects.create(owner=self.user, analysis=self.analysis)
        question = Question.objects.create(interview=interview, text='Private question')
        self.client.force_login(self.other)
        for url in [reverse('resume_edit', args=[self.resume.pk]), reverse('analysis_detail', args=[self.analysis.pk]), reverse('application_edit', args=[app.pk]), reverse('interview_detail', args=[interview.pk])]:
            self.assertEqual(self.client.get(url).status_code, 404)
        for url in [reverse('resume_delete', args=[self.resume.pk]), reverse('suggestions', args=[self.analysis.pk]), reverse('interview_start', args=[self.analysis.pk]), reverse('answer', args=[question.pk])]:
            self.assertEqual(self.client.post(url).status_code, 404)
        response = self.client.post('/analyses/new/', {'resume': self.resume.pk, 'role': 'Leak', 'job_description': JOB})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Analysis.objects.filter(role='Leak').exists())

    def test_resume_edit_invalidates_analysis(self):
        self.client.post(reverse('resume_edit', args=[self.resume.pk]), {'title': 'Updated', 'text': RESUME + ' Docker.'})
        self.assertFalse(Analysis.objects.filter(pk=self.analysis.pk).exists())

    def test_csrf_and_no_get_mutations(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post('/applications/new/', {}).status_code, 403)
        self.assertEqual(self.client.get(reverse('suggestions', args=[self.analysis.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse('interview_start', args=[self.analysis.pk])).status_code, 405)

    def test_html_is_escaped(self):
        self.analysis.suggestions = '<script>alert(1)</script>'
        self.analysis.save()
        response = self.client.get(reverse('analysis_detail', args=[self.analysis.pk]))
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;')

    @override_settings(GEMINI_API_KEY='mock-test-key')
    @patch('assistant.services.ai.requests.post')
    def test_gemini_suggestions_questions_feedback(self, post):
        response = Mock()
        response.json.return_value = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'Add evidence of your Django work.'}]}}]}
        post.return_value = response
        self.client.post(reverse('suggestions', args=[self.analysis.pk]), {'consent': 'yes'})
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.suggestion_source, 'Gemini')
        response.json.return_value['candidates'][0]['content']['parts'][0]['text'] = json.dumps(['Explain your Django project in detail.'] * 5)
        self.client.post(reverse('interview_start', args=[self.analysis.pk]), {'consent': 'yes'})
        interview = Interview.objects.get()
        self.assertEqual(interview.source, 'Gemini')
        response.json.return_value['candidates'][0]['content']['parts'][0]['text'] = 'Use a concrete result to finish your example.'
        q = interview.questions.first()
        self.client.post(reverse('answer', args=[q.pk]), {'consent': 'yes', 'answer': 'I built a Django backend and implemented authentication and integration tests.'})
        q.refresh_from_db()
        self.assertEqual(q.source, 'Gemini')

    @override_settings(GEMINI_API_KEY='mock-test-key', AI_DAILY_LIMIT=1)
    @patch('assistant.services.ai.requests.post')
    def test_api_timeout_and_daily_limit(self, post):
        post.side_effect = requests.Timeout()
        with self.assertRaises(AIUnavailable):
            generate(self.user, 'Test', {})
        with self.assertRaisesMessage(AIUnavailable, 'Daily AI limit'):
            generate(self.user, 'Test', {})
        self.assertEqual(post.call_count, 1)

    @override_settings(GEMINI_API_KEY='mock-test-key', GEMINI_READ_TIMEOUT_SECONDS=60)
    @patch('assistant.services.ai.requests.post')
    def test_read_timeout_uses_sixty_seconds_with_bounded_retries(self, post):
        post.side_effect = requests.ReadTimeout('sensitive transport detail')
        with self.assertRaisesMessage(AIUnavailable, 'timed out despite bounded retries') as raised:
            generate(self.user, 'Test', {})
        self.assertEqual(post.call_args.kwargs['timeout'], (5, 60))
        self.assertEqual(post.call_count, 4)
        self.assertNotIn('sensitive transport detail', str(raised.exception))

    @override_settings(GEMINI_API_KEY='mock-test-key', GEMINI_READ_TIMEOUT_SECONDS=45)
    @patch('assistant.services.ai.requests.post')
    def test_custom_read_timeout_is_used(self, post):
        post.return_value.json.return_value = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'Specific advice.'}]}}]}
        self.assertEqual(generate(self.user, 'Test', {}), 'Specific advice.')
        self.assertEqual(post.call_args.kwargs['timeout'], (5, 45))

    @override_settings(GEMINI_API_KEY='mock-test-key')
    @patch('assistant.services.ai.requests.post')
    def test_no_consent_no_api_call(self, post):
        self.client.post(reverse('suggestions', args=[self.analysis.pk]))
        self.client.post(reverse('interview_start', args=[self.analysis.pk]))
        post.assert_not_called()

    @override_settings(GEMINI_API_KEY='mock-test-key')
    @patch('assistant.services.ai.requests.post')
    def test_connection_error_has_actionable_safe_message(self, post):
        post.side_effect = requests.ConnectionError('private diagnostic mock-test-key')
        with self.assertRaises(AIUnavailable) as raised:
            generate(self.user, 'Test', {})
        self.assertIn('Cannot connect to Gemini', str(raised.exception))
        self.assertNotIn('mock-test-key', str(raised.exception))
        self.assertNotIn('private diagnostic', str(raised.exception))

    @override_settings(GEMINI_API_KEY='mock-test-key')
    @patch('assistant.services.ai.requests.post')
    def test_provider_errors_distinguish_quota_key_and_model(self, post):
        for status, expected in [(400, 'rejected'), (401, 'authentication'), (403, 'denied'), (404, 'not found'), (429, 'quota'), (503, 'service error')]:
            with self.subTest(status=status):
                response = requests.Response()
                response.status_code = status
                response._content = b'private provider detail mock-test-key'
                response._content_consumed = True
                post.return_value = response
                with self.assertRaises(AIUnavailable) as raised:
                    generate(self.user, 'Test', {})
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn('mock-test-key', str(raised.exception))

@override_settings(GEMINI_API_KEY='test-key-never-log', GEMINI_MODEL='gemini-3.8-flash', GEMINI_READ_TIMEOUT_SECONDS=60, GEMINI_RETRY_BUDGET_SECONDS=80, AI_DAILY_LIMIT=100)
class RetryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('retry-test')
        self.now = 0.0
        for name, options in [
            ('time.monotonic', {'side_effect': lambda: self.now}),
            ('time.sleep', {'side_effect': self.advance}),
            ('random.uniform', {'return_value': 0.125}),
            ('requests.post', {}),
        ]:
            patcher = patch('assistant.services.ai.' + name, **options)
            setattr(self, name.split('.')[-1], patcher.start())
            self.addCleanup(patcher.stop)

    def advance(self, seconds):
        self.now += seconds

    @staticmethod
    def response(status=200, headers=None, content=None):
        response = requests.Response()
        response.status_code = status
        response.headers.update(headers or {})
        response._content = content if content is not None else json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'Useful advice.'}]}}]}).encode()
        response._content_consumed = True
        return response

    def test_every_transient_status_retries_then_recovers(self):
        for status in [408, 429, 500, 502, 503, 504]:
            with self.subTest(status=status):
                self.post.reset_mock()
                self.sleep.reset_mock()
                self.post.side_effect = [self.response(status), self.response()]
                self.assertEqual(generate(self.user, 'Task', {}), 'Useful advice.')
                self.assertEqual(self.post.call_count, 2)
                self.sleep.assert_called_once_with(1.125)

    def test_permanent_errors_never_retry_or_leak(self):
        for status in [400, 401, 403, 404, 405, 422]:
            with self.subTest(status=status):
                self.post.reset_mock()
                self.sleep.reset_mock()
                self.post.return_value = self.response(status, content=b'test-key-never-log')
                with self.assertRaises(AIUnavailable) as raised:
                    generate(self.user, 'Task', {})
                self.assertNotIn('test-key-never-log', str(raised.exception))
                self.assertEqual(self.post.call_count, 1)
                self.sleep.assert_not_called()

    def test_three_backoffs_then_fallback_and_all_attempts_count(self):
        self.post.return_value = self.response(503)
        with self.assertRaisesMessage(AIUnavailable, 'service error'):
            generate(self.user, 'Task', {})
        self.assertEqual(self.post.call_count, 4)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [1.125, 2.125, 4.125])
        self.assertEqual(AIUsage.objects.get(owner=self.user).count, 4)

    def test_network_timeouts_and_connection_errors_recover(self):
        for error in [requests.ReadTimeout, requests.ConnectTimeout, requests.ConnectionError]:
            with self.subTest(error=error):
                self.post.reset_mock()
                self.post.side_effect = [error('private data'), self.response()]
                self.assertEqual(generate(self.user, 'Task', {}), 'Useful advice.')
                self.assertEqual(self.post.call_count, 2)

    def test_tls_error_is_not_retried(self):
        self.post.side_effect = requests.exceptions.SSLError('private certificate data')
        with self.assertRaisesMessage(AIUnavailable, 'securely'):
            generate(self.user, 'Task', {})
        self.assertEqual(self.post.call_count, 1)
        self.sleep.assert_not_called()

    def test_long_timeout_shrinks_later_attempt_and_stops_at_budget(self):
        def timeout(*args, **kwargs):
            self.advance(sum(kwargs['timeout']))
            raise requests.ReadTimeout()
        self.post.side_effect = timeout
        with self.assertRaisesMessage(AIUnavailable, 'timed out'):
            generate(self.user, 'Task', {})
        self.assertEqual(self.post.call_count, 2)
        self.assertEqual(self.post.call_args_list[0].kwargs['timeout'], (5, 60))
        self.assertLess(self.post.call_args_list[1].kwargs['timeout'][1], 14)
        self.assertLessEqual(self.now, 80)

    def test_retry_after_respected_or_stops_if_too_long(self):
        self.post.side_effect = [self.response(429, {'Retry-After': '10'}), self.response()]
        self.assertEqual(generate(self.user, 'Task', {}), 'Useful advice.')
        self.sleep.assert_called_once_with(10)
        self.post.reset_mock()
        self.sleep.reset_mock()
        self.post.side_effect = None
        self.post.return_value = self.response(503, {'Retry-After': '120'})
        with self.assertRaises(AIUnavailable):
            generate(self.user, 'Task', {})
        self.assertEqual(self.post.call_count, 1)
        self.sleep.assert_not_called()

    @override_settings(AI_DAILY_LIMIT=2)
    def test_daily_limit_applies_to_retries(self):
        self.post.return_value = self.response(503)
        with self.assertRaisesMessage(AIUnavailable, 'Daily AI limit'):
            generate(self.user, 'Task', {})
        self.assertEqual(self.post.call_count, 2)
        self.assertEqual(AIUsage.objects.get(owner=self.user).count, 2)

    def test_invalid_json_and_truncated_response_not_retried(self):
        for content in [b'not json', b'{"candidates":[{"finishReason":"MAX_TOKENS"}]}']:
            self.post.reset_mock()
            self.post.return_value = self.response(content=content)
            with self.assertRaisesMessage(AIUnavailable, 'unusable response'):
                generate(self.user, 'Task', {})
            self.assertEqual(self.post.call_count, 1)
        self.sleep.assert_not_called()

    def test_view_keeps_local_fallback_after_retries(self):
        resume = Resume.objects.create(owner=self.user, title='Retry resume', text=RESUME)
        analysis = Analysis.objects.create(owner=self.user, resume=resume, role='Engineer', job_description=JOB, **match_resume(RESUME, JOB))
        self.client.force_login(self.user)
        self.post.return_value = self.response(503)
        response = self.client.post(reverse('suggestions', args=[analysis.pk]), {'consent': 'yes'})
        self.assertEqual(response.status_code, 302)
        analysis.refresh_from_db()
        self.assertEqual(analysis.suggestion_source, 'Local guidance')
        self.assertIn('rule-based', analysis.suggestions)
        self.assertEqual(self.post.call_count, 4)

    @override_settings(DEBUG=True)
    def test_live_script_reports_retry_then_three_successful_features(self):
        questions = json.dumps(['Explain your Django experience in detail.'] * 5)
        def result(text):
            return self.response(content=json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': text}]}}]}).encode())
        self.post.side_effect = [self.response(503), result('Improve your bullets. Learn Docker and PostgreSQL.'), result(questions), result('Explain the result of your example.')]
        stdout = io.StringIO()
        with patch('pathlib.Path.write_text') as write, redirect_stdout(stdout), self.assertRaises(SystemExit) as exited:
            runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/test_gemini_live.py'), run_name='__main__')
        self.assertEqual(exited.exception.code, 0)
        report = json.loads(write.call_args.args[0])
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(len(report['provider_calls']), 4)
        self.assertEqual(report['provider_calls'][1]['attempt'], 2)
        self.assertEqual(len(report['retry_delays']), 1)
        self.assertNotIn('test-key-never-log', stdout.getvalue())
        self.assertNotIn('test-key-never-log', write.call_args.args[0])

    def test_interview_outage_preserves_questions_answer_and_local_feedback(self):
        resume = Resume.objects.create(owner=self.user, title='Outage resume', text=RESUME)
        analysis = Analysis.objects.create(owner=self.user, resume=resume, role='Engineer', job_description=JOB, **match_resume(RESUME, JOB))
        self.client.force_login(self.user)
        self.post.return_value = self.response(503)
        response = self.client.post(reverse('interview_start', args=[analysis.pk]), {'consent': 'yes'})
        self.assertEqual(response.status_code, 302)
        interview = Interview.objects.get(analysis=analysis)
        self.assertEqual(interview.source, 'Local practice')
        self.assertEqual(interview.questions.count(), 5)
        self.assertEqual(self.post.call_count, 4)
        self.post.reset_mock()
        self.post.side_effect = requests.ReadTimeout('private diagnostic')
        question = interview.questions.first()
        answer = 'I built a Django task manager and tested that users could only access their own tasks.'
        response = self.client.post(reverse('answer', args=[question.pk]), {'consent': 'yes', 'answer': answer})
        self.assertEqual(response.status_code, 302)
        question.refresh_from_db()
        self.assertEqual(question.answer, answer)
        self.assertEqual(question.source, 'Local checklist')
        self.assertIn('Situation, Task, Action, and Result', question.feedback)
        self.assertEqual(self.post.call_count, 4)

class MatchingAndExtractionTests(TestCase):
    def test_similarity_and_empty_vocabulary(self):
        self.assertAlmostEqual(match_resume(RESUME, RESUME)['score'], 100)
        self.assertEqual(match_resume('the and', 'or the')['score'], 0)
        self.assertGreater(match_resume(RESUME, JOB)['score'], 0)
        self.assertNotIn('Java', skills_in('JavaScript'))
        self.assertIn('C++', skills_in('C++, C# and .NET'))

    def test_docx_and_txt(self):
        doc = Document()
        doc.add_paragraph(RESUME)
        stream = io.BytesIO()
        doc.save(stream)
        self.assertIn('Django', extract_resume(SimpleUploadedFile('cv.docx', stream.getvalue())))
        self.assertEqual(extract_resume(SimpleUploadedFile('cv.txt', RESUME.encode())), RESUME)

    def test_text_pdf(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        content = DecodedStreamObject()
        content.set_data(('BT /F1 12 Tf 50 700 Td (' + RESUME + ') Tj ET').encode())
        page[NameObject('/Contents')] = writer._add_object(content)
        stream = io.BytesIO()
        writer.write(stream)
        self.assertIn('Django', extract_resume(SimpleUploadedFile('resume.pdf', stream.getvalue())))

    def test_bad_files_and_limits(self):
        for name, content in [('bad.pdf', b'not a pdf'), ('bad.docx', b'not zip'), ('bad.exe', b'hello'), ('short.txt', b'hi'), ('big.txt', b'x' * (5 * 1024 * 1024 + 1))]:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                extract_resume(SimpleUploadedFile(name, content))
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        stream = io.BytesIO()
        writer.write(stream)
        with self.assertRaises(ValidationError):
            extract_resume(SimpleUploadedFile('scanned.pdf', stream.getvalue()))


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}, GEMINI_API_KEY='')
class CareerAssistantTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('chatuser', password='Chat-test-9482')
        self.other = get_user_model().objects.create_user('chatother', password='Chat-test-9482')
        self.client.force_login(self.user)
        self.url = reverse('career_assistant')
        self.resume = Resume.objects.create(owner=self.user, title='Private resume', text=RESUME)
        self.analysis = Analysis.objects.create(owner=self.user, resume=self.resume, role='Django Developer', job_description=JOB, **match_resume(RESUME, JOB))
        self.foreign = Resume.objects.create(owner=self.other, title='Other private resume', text='Other private content')
        self.foreign_analysis = Analysis.objects.create(owner=self.other, resume=self.foreign, role='Private role', job_description=JOB, **match_resume(RESUME, JOB))

    def test_authentication_and_owner_scoped_choices(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'AI Career Assistant')
        self.assertContains(response, 'Private resume')
        self.assertNotContains(response, 'Other private resume')
        self.assertNotContains(response, 'Private role')
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), reverse('login') + '?next=' + self.url)
        self.assertEqual(self.client.post(self.url, {'message': 'Hello'}).status_code, 302)

    @patch('assistant.views.generate')
    def test_context_ownership_consent_and_validation(self, generate_mock):
        for data in [
            {'message': 'Help', 'resume': self.foreign.pk, 'share_context': 'on'},
            {'message': 'Help', 'analysis': self.foreign_analysis.pk, 'share_context': 'on'},
            {'message': 'Help', 'resume': self.resume.pk},
            {'message': 'Help', 'resume': self.resume.pk, 'analysis': self.analysis.pk, 'share_context': 'on'},
            {'message': '   '}, {'message': 'x' * 2001},
        ]:
            with self.subTest(data=data):
                response = self.client.post(self.url, data)
                self.assertTrue(response.context['form'].errors)
        generate_mock.assert_not_called()
        self.assertNotIn('career_chat', self.client.session)

    @patch('assistant.views.generate', return_value='A useful reply')
    def test_minimal_context_and_history_reset(self, generate_mock):
        self.client.post(self.url, {'message': 'Explain a job role'})
        self.assertNotIn('selected_context', generate_mock.call_args.args[2])
        self.client.post(self.url, {'message': 'Improve my resume', 'resume': self.resume.pk, 'share_context': 'on'})
        payload = generate_mock.call_args.args[2]
        self.assertEqual(payload['selected_context'], {'resume_text': RESUME})
        self.assertEqual(payload['recent_conversation'], [])
        self.client.post(self.url, {'message': 'Suggest skills', 'analysis': self.analysis.pk, 'share_context': 'on'})
        context = generate_mock.call_args.args[2]['selected_context']
        self.assertEqual(context['job_description'], JOB)
        self.assertNotIn('resume_text', context)
        self.client.post(self.url, {'message': 'What next?'})
        self.assertEqual(generate_mock.call_args.args[2]['recent_conversation'], [])

    @override_settings(GEMINI_API_KEY='mock-secret-key')
    @patch('assistant.services.ai.time.sleep')
    @patch('assistant.services.ai.requests.post')
    def test_gemini_reply_reuses_retry_service(self, post, sleep):
        response = Mock()
        response.json.return_value = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'Practice a STAR story.'}]}}]}
        post.side_effect = [requests.Timeout(), response]
        page = self.client.post(self.url, {'message': 'Prepare me for an interview'}, follow=True)
        self.assertContains(page, 'Practice a STAR story.')
        self.assertContains(page, 'Gemini')
        self.assertNotContains(page, 'mock-secret-key')
        self.assertEqual(post.call_count, 2)
        self.assertEqual(AIUsage.objects.get(owner=self.user).count, 2)
        self.assertIn('gemini-3.8-flash', post.call_args.args[0])
        sleep.assert_called_once()

    def test_missing_key_fallback_and_session_isolation(self):
        page = self.client.post(self.url, {'message': 'Create a preparation plan'}, follow=True)
        self.assertContains(page, 'Local guidance')
        self.assertContains(page, 'Week 1:')
        self.assertContains(page, 'Gemini is unavailable')
        other_client = Client()
        other_client.force_login(self.other)
        self.assertNotContains(other_client.get(self.url), 'Week 1:')
        self.client.logout()
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(self.url), 'Week 1:')

    @patch('assistant.views.generate', side_effect=AIUnavailable('unavailable'))
    def test_outage_and_quota_fallback(self, generate_mock):
        self.assertContains(self.client.post(self.url, {'message': 'Prepare me for an interview'}, follow=True), 'STAR stories')
        self.assertEqual(self.client.session['career_chat']['messages'][-1]['source'], 'Local guidance')

    @patch('assistant.views.generate', return_value='<script>alert(1)</script>')
    def test_history_is_bounded_escaped_and_clearable(self, generate_mock):
        for i in range(7):
            self.client.post(self.url, {'message': f'Resume question {i}'})
        self.assertEqual(len(self.client.session['career_chat']['messages']), 10)
        self.assertLessEqual(len(generate_mock.call_args.args[2]['recent_conversation']), 6)
        page = self.client.get(self.url)
        self.assertNotContains(page, '<script>alert(1)</script>')
        self.assertNotContains(page, 'alert(1)')
        self.client.post(self.url, {'action': 'clear'})
        self.assertNotIn('career_chat', self.client.session)

    def test_csrf_protects_send_and_clear(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(self.url, {'message': 'Help'}).status_code, 403)
        self.assertEqual(strict.post(self.url, {'action': 'clear'}).status_code, 403)
        strict.get(self.url)
        self.assertEqual(strict.post(self.url, {'message': 'Help', 'csrfmiddlewaretoken': strict.cookies['csrftoken'].value}).status_code, 302)

    def test_deleted_context_clears_history(self):
        self.client.post(self.url, {'message': 'Improve my resume', 'resume': self.resume.pk, 'share_context': 'on'})
        self.resume.delete()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertNotIn('career_chat', self.client.session)


class ChatMarkdownTests(TestCase):
    def test_supported_markdown(self):
        from assistant.templatetags.chat_markdown import chat_markdown
        output = chat_markdown('### Plan\n\n**Focus** on `Python`.\n\n- Resume\n- Practice\n\n1. Learn\n2. Build\n\n```python\nprint("hello")\n```')
        for fragment in ['<h3>Plan</h3>', '<strong>Focus</strong>', '<code>Python</code>',
                         '<ul>', '<li>Resume</li>', '<ol>', '<li>Build</li>', '<pre><code>print("hello")']:
            self.assertIn(fragment, output)

    def test_xss_allowlist(self):
        from html.parser import HTMLParser
        from assistant.templatetags.chat_markdown import chat_markdown, ALLOWED_TAGS
        class Collector(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tags = []
            def handle_starttag(self, tag, attrs):
                self.tags.append((tag, attrs))
        payloads = [
            '<script>alert(1)</script><p onclick="alert(1)" style="position:fixed">Safe</p>',
            '<img src=x onerror=alert(1)><iframe srcdoc="<script>alert(1)</script>"></iframe>',
            '<svg/onload=alert(1)><a href="javascript:alert(1)">x</a></svg>',
            '[click](javascript:alert%281%29) ![image](https://example.com/tracker)',
            '<a href="jav&#x61;script:alert(1)">click</a><input autofocus onfocus=alert(1)>',
            '<math><mtext><img src=x onerror=alert(1)></mtext></math>',
            '<form><button formaction="javascript:alert(1)">go</button></form><!-- comment -->',
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                output = chat_markdown(payload)
                parser = Collector()
                parser.feed(output)
                self.assertTrue(all(tag in ALLOWED_TAGS and not attrs for tag, attrs in parser.tags))
                self.assertNotIn('<!--', output)

    def test_code_html_remains_inert_text(self):
        from assistant.templatetags.chat_markdown import chat_markdown
        output = chat_markdown('```html\n<script>alert(1)</script>\n```')
        self.assertIn('&lt;script&gt;', output)
        self.assertNotIn('<script>', output)

    @override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
    def test_template_formats_only_assistant_without_changing_history(self):
        from django.template.loader import render_to_string
        from assistant.forms import CareerChatForm
        user = get_user_model().objects.create_user('markdownuser')
        text = '**Bold** <img src=x onerror=alert(1)> <script>alert(1)</script>'
        chat = [{'role': 'user', 'text': text}, {'role': 'assistant', 'text': text, 'source': 'Gemini'}]
        html = render_to_string('career_assistant.html', {'user': user, 'form': CareerChatForm(user), 'chat_messages': chat})
        self.assertIn('<strong>Bold</strong>', html)
        self.assertIn('**Bold** &lt;img', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('<img src=x', html)
        self.assertNotIn('<script>alert(1)', html)
        self.assertEqual(chat[1]['text'], text)
