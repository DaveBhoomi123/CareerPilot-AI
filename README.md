# CareerPilot AI – AI Job Application & Interview Assistant

A medium-level Django portfolio project that helps candidates compare a resume with a job, prepare for interviews, and track applications. Server-rendered HTML, CSS, JavaScript and Bootstrap keep the code easy to follow. No paid model training, vector database, React build, or background worker is required.

## Features

- Signup, login, POST logout, password change, Django password validation and session authentication.
- Upload text-based PDF, DOCX or UTF-8 TXT resumes (5 MB maximum), or paste/edit text. Only extracted text is retained in the database; original files are discarded.
- TF-IDF and cosine similarity via Scikit-learn; dictionary-based matched/missing skills.
- Optional Gemini resume improvements and skill-gap learning plans.
- Five-question mock interviews, saved answers, and optional Gemini feedback.
- Clear rule-based fallbacks when no key is configured, quota is exhausted, or the API fails.
- Application CRUD, stages, dates, notes, links, search and filtering.
- Owner-scoped records, CSRF protection, escaped output, bounded inputs and per-user daily AI request limits.
- Responsive interface, locally bundled Bootstrap, SQLite development and PostgreSQL production configuration.
- Automated tests, migrations, GitHub Actions and a Render deployment blueprint.

## Run locally

Use Python 3.12 and run these commands from this repository's root. A virtual environment and migrated SQLite database have already been prepared in the current workspace.

```powershell
# Windows, first-time setup on another machine
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/setup_env.py
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

```bash
# macOS / Linux
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_env.py
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000 and create your own account. There are no shared/default production credentials. On this workstation Python is bundled with Codex rather than on PATH; the prepared `.venv\Scripts\python.exe` works directly.

Optional admin account: `python manage.py createsuperuser` (use the virtual environment interpreter). Visit `/admin/`. Email/password-reset delivery is intentionally outside this project's scope; a local administrator can use `python manage.py changepassword USERNAME` if needed.

## Try a complete workflow

1. Create an account, then open **My resumes → Add resume**.
2. Upload `samples/resume.txt`, or paste its contents. Give it a title.
3. Open **Job match → New job match**, select the resume and paste `samples/job-description.txt`.
4. Inspect the score, matched/missing skills and local improvement plan.
5. Optionally enable Gemini below and use **Generate AI improvement plan**.
6. Open **Interview studio**, start a session, answer a question, and save feedback.
7. Open **Applications**, add a role, edit its stage, filter the list and test deletion.

Editing a resume deletes its existing analyses and associated interviews to prevent outdated scores. The UI warns before editing; delete screens explain cascading deletion. Deleting an application does not affect resumes.

## Add Gemini

Create a key in [Google AI Studio](https://aistudio.google.com/apikey), select a model currently available on the free tier, and edit the ignored `.env` file:

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.8-flash
GEMINI_READ_TIMEOUT_SECONDS=60
AI_DAILY_LIMIT=15
```

Restart Django after changing configuration. The server uses Gemini's REST `generateContent` API through `requests`; no key reaches JavaScript. The model name is configurable because model availability changes. Check [model pricing](https://ai.google.dev/gemini-api/docs/pricing) and [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) for your project/region before use. A free tier is quota-limited, not an unlimited service; this app never enables billing for you.

Requests use a 5-second connection timeout and a configurable 60-second read-inactivity timeout. Transient HTTP 408, 429, 500, 502, 503, 504, network timeouts and connection errors receive at most three retries (four attempts total), with 1/2/4-second backoff plus 0–0.25 seconds of jitter. Permanent HTTP errors including 400/401/403/404, TLS certificate errors, and malformed/incomplete outputs are not retried. Exhaustion returns the existing local guidance. Retries improve resilience but cannot guarantee availability during a provider outage.

An 80-second shared retry window includes backoff; later connection/read timeouts shrink to the remaining window so a slow first request does not get three additional full minutes. This is a best-effort window, not a hard wall-clock deadline: Requests read timeouts measure inactivity and DNS/OS delays can exceed them. The existing 90-second production worker timeout is unchanged. A longer `Retry-After` response causes fallback rather than retrying prematurely. Each network attempt consumes a daily usage slot and can also consume provider quota. There are no stacked library retries or changes to the chosen model.

The official `google-genai` SDK was evaluated, but package installation was unavailable in the restricted development session; the tested REST transport is retained and no SDK dependency is required. See the [official API reference](https://ai.google.dev/api/generate-content) and [SDK retry implementation](https://github.com/googleapis/python-genai/blob/main/google/genai/_api_client.py). No key, request headers, raw provider error body or private prompt is logged by retry handling.

AI buttons explain which text is shared and require opt-in. Free-tier content may be used to improve Google's products: use synthetic/redacted resumes for a public demonstration. Matching itself sends nothing externally. Request attempts, including failures, count toward the daily application limit. Limits are per account and do not replace a provider quota or protect against mass signup. Local fallback feedback is a writing checklist, not an AI assessment of correctness.

Live Gemini integration was verified locally using synthetic test data. Resume improvement and interview-question generation successfully returned Gemini responses. Retry/backoff handling was verified, and local fallback works when Gemini quota limits or provider availability prevent a response.

To verify the real integration locally after adding your key, run `.venv\Scripts\python.exe scripts/test_gemini_live.py` from PowerShell. It uses synthetic samples and a dedicated non-login test account, exercises resume improvements/skill-gap advice, five interview questions and answer feedback through Django views, and saves `outputs/GEMINI_LIVE_TEST.json`. It exits successfully only when all results come from Gemini. It makes up to four attempts per feature (12 maximum across three calls), retains test records, respects the daily limit, and stops early if suggestions fail after retries. The report lists feature names, attempt numbers, elapsed times and retry delays. It can take about 80 seconds per feature during failures. Network access is required; no credentials are printed. A configured key alone does not establish success.

## Project structure

```text
careerpilot/          Django settings, root URLs, WSGI
assistant/
  models.py          Resume, Analysis, Application, Interview, Question, AIUsage
  forms.py           Validation and user-scoped resume selection
  views.py           Request handlers and owner checks
  services/
    matching.py      TF-IDF, cosine similarity and skill dictionary
    extraction.py    PDF/DOCX/TXT text extraction
    ai.py            Gemini calls, daily usage and local guidance
  migrations/        Versioned database schema
  tests.py           Workflow, isolation, extraction and AI tests
templates/           Server-rendered Bootstrap pages
static/              CSS, progressive JavaScript, bundled Bootstrap
samples/             Synthetic resume and job description
scripts/setup_env.py Secure local environment initializer
docs/                Deployment and placement-interview explanations
render.yaml          Free Render web-service blueprint
.github/workflows/   Tests against PostgreSQL in CI
```

## Matching explained

The vectorizer fits on the selected resume and job description only, using English stop-word removal and word unigrams/bigrams. TF-IDF weights each term; cosine similarity measures the angle between the two document vectors. `score = cosine_similarity × 100`, rounded to one decimal. No arbitrary skill-score weight is mixed in.

Skills are a separate, case-insensitive dictionary with aliases and word boundaries (`Java` does not match `JavaScript`). It compares skills explicitly mentioned in the job with those in the resume. This does not understand negation, experience depth or all possible technologies. It can miss synonyms and non-English phrasing. A 70% score is **not** a 70% chance of being hired, an ATS pass, or a calibrated measure of candidate quality.

## Tests and checks

```powershell
.\.venv\Scripts\python.exe manage.py test --verbosity 2
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\.venv\Scripts\python.exe -m pip check
```

Use `requirements-lock.txt` to reproduce the tested direct and transitive package versions. `requirements.txt` expresses compatible ranges for security patch updates. The lock includes platform markers for Windows Waitress/Linux Gunicorn.

## Push to GitHub

Create an empty repository in your GitHub account, then:

```bash
git init
git add .
git status
# Confirm .env, db.sqlite3 and .venv are NOT staged.
git commit -m "Build CareerPilot AI career assistant"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/careerpilot-ai.git
git push -u origin main
```

If a remote already exists, inspect `git remote -v` before adding/changing it. Authenticate using GitHub's normal login/token flow; never paste tokens into source files or remote URLs. `.env.example` contains placeholders only. The GitHub Actions database password is a disposable CI fixture, not a deployed credential.

## Deploy

Follow [the complete Render + Neon guide](docs/DEPLOYMENT.md). It covers free-tier accounts, PostgreSQL, environment variables, migrations, static files, HTTPS, smoke tests and common errors. Deployment to your account and real PostgreSQL integration require your hosting credentials/connection URL and have not been performed in this workspace.

For placement preparation, read [the architecture and interview guide](docs/INTERVIEW_GUIDE.md).

## Scope and practical limitations

This is a portfolio application, not a commercial recruitment platform. Text-based PDFs are supported; scanned PDFs need OCR elsewhere. There is no email verification, background queue, account recovery email, antivirus scanning, or distributed abuse protection. API calls are synchronous with a timeout. Free hosts can sleep and cold starts can be slow. Resume text and feedback persist until their records are deleted. Before inviting many public users, add signup/login rate limiting, monitoring, a retention policy and backups; keep this demo's data synthetic.

## License

Project: MIT. Bootstrap 5.3.8 is bundled under MIT; its copyright/license banner remains in the stylesheet. Its optional source-map reference is removed so WhiteNoise can collect static files without a missing map.


## AI Career Assistant

Open **AI Career Assistant** in the sidebar after signing in. Ask a career question or use a quick prompt. Optionally select one of your own resumes or job analyses and confirm sharing it with Gemini. Selecting a different context starts a fresh chat. No document is sent when no context is selected; an analysis shares job details and skill matches, not its linked resume.

The feature uses a normal Django POST form with CSRF protection and the existing server-side Gemini service (`gemini-3.8-flash`), retry budget, daily usage limit, and rule-based fallback. The API key never enters the browser. The Django session retains the last five exchanges, cleared by **Clear chat** or logout; only the last three exchanges and bounded selected context are sent with a new message. No new database models or migrations are required. Quick prompts and the loading indicator are progressive JavaScript enhancements; sending still works without JavaScript.
