# CareerPilot AI: final local testing, folder setup, GitHub and deployment

Current source workspace:

```text
C:\Users\ADMIN\Documents\Codex\2026-09-18\build-a-medium-level-ready-to
```

The model remains `gemini-3.8-flash`. Your `.env` and API key have not been changed or printed. The app uses the existing Requests REST transport with bounded retries; the optional SDK migration was not performed because its package could not be installed in the restricted session.

## 1. Local testing in the current workspace

Open normal PowerShell:

```powershell
Set-Location 'C:\Users\ADMIN\Documents\Codex\2026-09-18\build-a-medium-level-ready-to'
.\.venv\Scripts\python.exe manage.py test --verbosity 2
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

If port 8000 is already serving the app, use that instance or stop it before starting another. Open http://127.0.0.1:8000. Register a new test account and verify:

1. Sign out and sign back in.
2. Upload `samples/resume.txt` and a text-based PDF, then check the extracted text with **View / edit**.
3. Analyze `samples/job-description.txt`; inspect the score and skills.
4. Add an application, edit its status/notes, filter the list, and delete that test application.
5. Start an interview without Gemini, save an answer, and check that it persists with local feedback.
6. Optionally opt into Gemini using synthetic data. A provider outage should show labelled local guidance rather than lose your data.

For the real provider smoke test, run in a second PowerShell window from the same folder:

```powershell
.\.venv\Scripts\python.exe scripts\test_gemini_live.py
```

This script does not need the development server running. It exercises Django views with real outbound Gemini requests and writes `outputs\GEMINI_LIVE_TEST.json`. It can make up to 12 provider attempts across the three AI actions, subject to the test account's daily allowance. Retries use approximately 1/2/4 seconds plus jitter, stop at four attempts, and share an 80-second best-effort window per action. A 503/timeout followed by fallback is correct failure handling, but is not a successful live Gemini response. Do not reset usage counters just to keep retrying an unavailable provider; retry later.

## 2. Set up your final CareerPilot-AI folder

These commands use **C:\Users\ADMIN\Documents\CareerPilot-AI** as the final location. This folder has not been created or moved for you. Keep the current workspace as a backup until the new location works.

Stop the original Django server with Ctrl+C in its terminal before copying the database, and close other processes using that database. Copying via the clean source ZIP avoids copying a virtual environment whose scripts still reference the old path.

```powershell
$careerSource = 'C:\Users\ADMIN\Documents\Codex\2026-09-18\build-a-medium-level-ready-to'
$careerFinal = 'C:\Users\ADMIN\Documents\CareerPilot-AI'
if (Test-Path -LiteralPath $careerFinal) { throw 'The final folder already exists. Choose an empty destination instead of overwriting it.' }

# Refresh the portable source archive, then extract its CareerPilot-AI folder.
& "$careerSource\.venv\Scripts\python.exe" "$careerSource\scripts\package_source.py"
Expand-Archive -LiteralPath "$careerSource\outputs\CareerPilot-AI-source.zip" -DestinationPath 'C:\Users\ADMIN\Documents'

# Preserve your local key/configuration and data privately; both are gitignored.
Copy-Item -LiteralPath "$careerSource\.env" -Destination "$careerFinal\.env"
Copy-Item -LiteralPath "$careerSource\db.sqlite3" -Destination "$careerFinal\db.sqlite3"

# Recreate the environment rather than copying .venv.
& "$careerSource\.venv\Scripts\python.exe" -m venv "$careerFinal\.venv"
Set-Location $careerFinal
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

If you want an empty database, omit only the `db.sqlite3` copy; `migrate` will create a new database and you will register again. If you want a fresh `.env` instead, omit its copy, run `python scripts/setup_env.py` using the new virtual environment, and enter your key locally. Do not delete the original folder until the final folder's app is verified.

## 3. GitHub setup from the final folder

Create an empty repository named `CareerPilot-AI` in your GitHub account (without an initial README/license). Replace `YOUR_USERNAME` below with your GitHub username.

```powershell
Set-Location 'C:\Users\ADMIN\Documents\CareerPilot-AI'
git init
git add .
git status --short
git ls-files -- .env db.sqlite3 .venv outputs
```

The last command must produce **no output**. `.env.example` is intentionally tracked. Then:

```powershell
git commit -m "Build CareerPilot AI with tested Gemini retries and local fallbacks"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/CareerPilot-AI.git
git push -u origin main
```

Use GitHub's normal authentication prompts. Open the repository's **Actions** tab and confirm the included PostgreSQL test workflow passes. Local verification used SQLite; PostgreSQL CI has not been run from this workspace.

## 4. Deploy the portfolio demo

1. Create a Neon PostgreSQL project on its Free plan and obtain its SSL connection string. Keep this value private.
2. In Render, choose **New → Blueprint**, connect your GitHub repository, and select its `render.yaml`. Confirm the web service uses the **Free** plan.
3. Set `DATABASE_URL` to the Neon connection string, `DEBUG=False`, `GEMINI_MODEL=gemini-3.8-flash`, and `CSRF_TRUSTED_ORIGINS=https://YOUR-SERVICE.onrender.com`. Add `GEMINI_API_KEY` privately in Render. The blueprint generates a production `DJANGO_SECRET_KEY` and auto-detects the assigned Render hostname. Do not upload your local `.env` or SQLite database.
4. Deploy. The build installs dependencies and collects static files; startup applies migrations and runs Gunicorn. Create a fresh production account.
5. Verify `/health/`, registration/login, sample upload/matching, application edits and interview persistence. For AI, check the saved source says **Gemini** before claiming live AI success.
6. Redeploy once and confirm records remain in Neon.

The full environment-variable table, manual build/start commands and troubleshooting steps are in [DEPLOYMENT.md](DEPLOYMENT.md). Check current [Render free-service limits](https://render.com/docs/free) and [Neon plans](https://neon.com/docs/introduction/plans). Render's free filesystem is temporary and its own free Postgres expires after 30 days; this configuration uses external Neon for database storage. Free services are appropriate for a portfolio demo, with quotas and cold starts.

No GitHub push, folder move, public deployment or real PostgreSQL verification has been performed on your behalf.
