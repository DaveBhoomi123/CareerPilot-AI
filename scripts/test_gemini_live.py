"""Exercise real Django view workflows with synthetic data; never log credentials."""
import os
import sys
import json
import re
from time import monotonic
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'careerpilot.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client
from assistant.models import Resume, Analysis, Interview
from assistant.services.matching import match_resume
from assistant.services import ai

print('Gemini key configured:', bool(settings.GEMINI_API_KEY), flush=True)
print('Configured model:', settings.GEMINI_MODEL, flush=True)
print('Read timeout (seconds):', settings.GEMINI_READ_TIMEOUT_SECONDS, flush=True)
print('Max attempts per feature:', ai.MAX_ATTEMPTS, flush=True)
print('Retry window (seconds):', settings.GEMINI_RETRY_BUDGET_SECONDS, flush=True)
if not settings.DEBUG:
    raise SystemExit('This smoke test is for the local development database only (DEBUG=True).')
if not settings.GEMINI_API_KEY:
    raise SystemExit('No configured key; stopped without network requests.')
root = Path(__file__).resolve().parents[1]
user, created = get_user_model().objects.get_or_create(username='GeminiIntegrationTest', defaults={'is_active': True})
if created:
    user.set_unusable_password()
    user.save()
elif user.has_usable_password():
    raise SystemExit('The test account name belongs to an existing login. Stopping without changing it.')
resume = Resume.objects.create(owner=user, title='Synthetic Gemini integration test', text=(root / 'samples/resume.txt').read_text())
job = (root / 'samples/job-description.txt').read_text()
analysis = Analysis.objects.create(owner=user, resume=resume, role='Junior Django Developer', job_description=job, **match_resume(resume.text, job))
client = Client(HTTP_HOST='localhost')
client.force_login(user)
real_post = ai.requests.post
calls = []
feature = 'resume_improvements_and_skill_gap'
real_sleep = ai.time.sleep
retry_delays = []


def observed_sleep(seconds):
    record = {'feature': feature, 'delay_seconds': round(seconds, 2)}
    retry_delays.append(record)
    print('Retry backoff:', json.dumps(record), flush=True)
    real_sleep(seconds)

def observed_post(*args, **kwargs):
    started = monotonic()
    try:
        response = real_post(*args, **kwargs)
        record = {'feature': feature, 'attempt': 1 + sum(c['feature'] == feature for c in calls), 'status': response.status_code, 'elapsed_seconds': round(monotonic() - started, 2)}
        try:
            data = response.json()
            record['finish_reasons'] = [x.get('finishReason') for x in data.get('candidates', [])]
            record['error_status'] = data.get('error', {}).get('status')
            # Deliberately omit error messages, headers, URLs and request credentials.
        except ValueError:
            record['json'] = False
        calls.append(record)
        print('Provider response:', json.dumps(record), flush=True)
        return response
    except ai.requests.RequestException as exc:
        record = {'feature': feature, 'attempt': 1 + sum(c['feature'] == feature for c in calls), 'exception_type': type(exc).__name__, 'elapsed_seconds': round(monotonic() - started, 2)}
        record['windows_error_codes'] = re.findall(r'WinError (\d+)', str(exc))
        calls.append(record)
        print('Provider request failed:', json.dumps(record), flush=True)
        raise

report = {'status': 'incomplete', 'data': 'synthetic samples only', 'model': settings.GEMINI_MODEL, 'read_timeout_seconds': settings.GEMINI_READ_TIMEOUT_SECONDS}
with patch.object(ai.requests, 'post', side_effect=observed_post), patch.object(ai.time, 'sleep', side_effect=observed_sleep):
    response = client.post(f'/analyses/{analysis.pk}/suggestions/', {'consent': 'yes'})
    analysis.refresh_from_db()
    report['resume_improvements_and_skill_gap'] = {'source': analysis.suggestion_source, 'text': analysis.suggestions, 'http_status': response.status_code, 'messages': [str(m) for m in get_messages(response.wsgi_request)]}
    print('Suggestions source:', analysis.suggestion_source, flush=True)
    if analysis.suggestion_source != 'Gemini':
        print('First Gemini feature failed. Stopping to avoid wasting quota; see the report messages.', flush=True)
    else:
        feature = 'interview_questions'
        response = client.post(f'/interviews/start/{analysis.pk}/', {'consent': 'yes'})
        interview = Interview.objects.filter(analysis=analysis).latest('id')
        report['interview_questions'] = {'source': interview.source, 'questions': list(interview.questions.values_list('text', flat=True)), 'http_status': response.status_code, 'messages': [str(m) for m in get_messages(response.wsgi_request)]}
        print('Questions source:', interview.source, flush=True)
        question = interview.questions.first()
        answer = 'I built a student task manager with Django. I implemented authentication and scoped task queries to the logged-in user. I wrote tests confirming another user could not edit private tasks, and I added form validation for due dates. My next step is to deploy the project using PostgreSQL and learn Docker.'
        feature = 'interview_feedback'
        response = client.post(f'/questions/{question.pk}/answer/', {'consent': 'yes', 'answer': answer})
        question.refresh_from_db()
        report['interview_feedback'] = {'source': question.source, 'text': question.feedback, 'http_status': response.status_code, 'messages': [str(m) for m in get_messages(response.wsgi_request)]}
        print('Feedback source:', question.source, flush=True)
        if interview.source == question.source == 'Gemini' and interview.questions.count() == 5 and question.feedback:
            report['status'] = 'passed'
report['provider_calls'] = calls
report['retry_delays'] = retry_delays
report['max_attempts_per_feature'] = ai.MAX_ATTEMPTS
report['retry_budget_seconds'] = settings.GEMINI_RETRY_BUDGET_SECONDS
out = root / 'outputs'
out.mkdir(exist_ok=True)
(out / 'GEMINI_LIVE_TEST.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('Saved secret-free test report to outputs/GEMINI_LIVE_TEST.json', flush=True)
raise SystemExit(0 if report['status'] == 'passed' else 1)
