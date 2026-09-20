# Deploy CareerPilot AI with Render PostgreSQL

Deploy the Django web service on Render and connect it to a separately provisioned Render PostgreSQL database. Choose service plans according to your persistence and availability requirements. Gemini remains optional and quota-limited.

Official references checked during development: [Render free services](https://render.com/docs/free), [Render Django deployment](https://render.com/docs/deploy-django), [Render PostgreSQL setup](https://render.com/docs/postgresql-creating-connecting), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).

## 1. Prepare the repository

Push this project to your GitHub account using README instructions. Run tests and `collectstatic` first. Commit `assistant/migrations/0001_initial.py`. Do not commit `.env`, SQLite, virtual environments, personal resumes or API keys.

## 2. Create the production database

1. In the Render dashboard, select **New → Postgres** and choose a plan appropriate for your required data lifetime.
2. Choose the same region and account as the web service, and PostgreSQL 16 or newer.
3. Once the database is available, copy its **Internal Database URL** from the connection details. The application already enforces `sslmode=require`, which Render internal connections support.
4. Use this URL only as a secret environment variable named `DATABASE_URL` on the Render web service. Never put the real value in the repository. The existing Blueprint creates only the web service; provision this database separately.

Production refuses to start with SQLite or an absent database URL. The app enforces database SSL when `DEBUG=False`. SQLite data is not automatically transferred; create a new production account and use sample data for your first verification.

## 3. Create the Render service

Create the web service in the same region as the database. Either choose **New → Blueprint**, connect the GitHub repository and use `render.yaml`, or choose **New → Web Service**, connect the repo and enter:

| Setting | Value |
|---|---|
| Runtime | Python |
| Instance | Free |
| Python | 3.12.10 |
| Build | `pip install -r requirements.txt && python manage.py collectstatic --noinput` |
| Start | `python manage.py migrate --noinput && gunicorn careerpilot.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 90` |
| Health check | `/health/` |

Use these environment variables:

| Name | Value |
|---|---|
| `DJANGO_SECRET_KEY` | New random secret; blueprint generates it |
| `DEBUG` | `False` |
| `DATABASE_URL` | Render PostgreSQL Internal Database URL |
| `ALLOWED_HOSTS` | Your exact hostname if custom; Render's assigned hostname is auto-added |
| `CSRF_TRUSTED_ORIGINS` | `https://YOUR-SERVICE.onrender.com` (and custom HTTPS origin if used) |
| `GEMINI_API_KEY` | Optional Google AI Studio key; blank keeps local mode |
| `GEMINI_MODEL` | `gemini-3.8-flash`; verify free-tier availability in your account |
| `AI_DAILY_LIMIT` | `15` or a smaller application-level daily cap |
| `PYTHON_VERSION` | `3.12.10` |

If configuring manually, generate a secret locally with `python -c "import secrets; print(secrets.token_urlsafe(64))"` and copy it into Render's secret field. For Blueprint, review the assigned service URL and set the matching CSRF origin before testing forms. A free instance may require provider account verification; do not select an upgrade unless you want to pay.

Migrations run at startup because free web services may not offer a separate pre-deploy command. This is appropriate for one small service instance; with multiple instances or complex migrations use a coordinated release step instead.

## 4. Verify the deployed app

1. Confirm deploy logs show successful migrations and Gunicorn startup.
2. Open `/health/` over HTTPS: expect `{"status":"ok"}`. This is a liveness endpoint, not a database diagnostic.
3. Visit the home page; check CSS loads, then sign up and log out/in.
4. Upload the synthetic sample TXT and run a job match.
5. Add an application, change its stage, reload and check persistence.
6. Start an interview and save an answer without AI.
7. If you configured Gemini, opt in to suggestions and verify the result source says **Gemini**.
8. Redeploy/restart and verify saved records remain (they live in PostgreSQL).

For production checks from a trusted local shell with production environment variables set, run `python manage.py check --deploy`. Never copy credentials into command history unnecessarily; a separate ignored local env file or host secret manager is preferable.

## Free-tier constraints

Free Render PostgreSQL databases expire after 30 days. Use a paid database for persistent hosting beyond that period. Free web services can sleep after inactivity and have an ephemeral filesystem; application records, including extracted resume text, are stored in PostgreSQL. Check Render's dashboard and documentation for current plan limits.

Gemini free-tier model availability and rate limits vary. The app retains your selected model and never silently switches models. Use AI Studio's current pricing/usage display and keep billing disabled if you want a strict no-charge demo. Transient failures receive at most three retries with 1/2/4-second backoff and small jitter within an 80-second retry window. Later request timeouts shrink to the remaining window; `Retry-After` is respected or the app falls back. Every attempt counts against the daily request limit. Permanent errors fall back immediately. Read-inactivity/DNS limitations mean this window is not a strict wall-clock guarantee; the existing worker timeout remains 90 seconds.

## Troubleshooting and maintenance

- **DisallowedHost / 400:** add the exact hostname to `ALLOWED_HOSTS`, with no scheme or path.
- **CSRF / 403:** use an HTTPS origin in `CSRF_TRUSTED_ORIGINS`; refresh the form after deployment.
- **Database connection error:** verify the Render PostgreSQL database is available, credentials are current, and SSL is enabled. Use a new secret connection string if a credential was exposed.
- **Missing CSS:** ensure `collectstatic` completed and the vendored stylesheet was committed.
- **Gemini local fallback:** inspect the on-screen reason, key, model access and provider quota. The app deliberately avoids displaying raw provider errors or keys.
- **Cold start / timeout:** wait for the sleeping service to wake up. One worker limits memory use; two threads keep small requests responsive during an AI call.
- **PDF unreadable:** use text-based, unencrypted documents, at most 20 pages and 5 MB. OCR is not included.
- **Admin:** create a superuser through a trusted environment connected to production, or use the provider's shell if available on your plan. No admin creation endpoint is exposed.

Keep regular PostgreSQL backups before schema changes. Review dependencies and rerun tests when updating. Do not remove migration files after deployment. Production uses secure cookies, HTTPS redirects and HSTS; its proxy-header setting assumes Render is the trusted TLS-terminating proxy.

Live deployment and PostgreSQL smoke tests remain account-dependent. The repository includes a PostgreSQL GitHub Actions job, which runs after you push; a successful local SQLite run does not claim PostgreSQL was already tested live.
