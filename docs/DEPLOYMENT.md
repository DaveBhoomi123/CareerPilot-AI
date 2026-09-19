# Deploy CareerPilot AI with Render + Neon PostgreSQL

This route uses a Render free web service and an external Neon free PostgreSQL database, subject to current regional availability and provider limits. No paid service is required for local matching. Gemini is optional and separately quota-limited.

Official references checked during development: [Render free services](https://render.com/docs/free), [Render Django deployment](https://render.com/docs/deploy-django), [Neon free plan](https://neon.com/docs/introduction/plans), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).

## 1. Prepare the repository

Push this project to your GitHub account using README instructions. Run tests and `collectstatic` first. Commit `assistant/migrations/0001_initial.py`. Do not commit `.env`, SQLite, virtual environments, personal resumes or API keys.

## 2. Create the production database

1. Sign in to Neon and create a project on the **Free** plan.
2. Choose a region near the Render service and a PostgreSQL version supported by Django (16 or newer is a reasonable choice).
3. In Neon's connection dialog select the database and copy the PostgreSQL connection string. The direct connection is suitable for this small, single-worker app. Retain `sslmode=require`.
4. Use this string only as a Render secret environment variable named `DATABASE_URL`. Never put the real value in the repository.

Production refuses to start with SQLite or an absent database URL. The app enforces database SSL when `DEBUG=False`. SQLite data is not automatically transferred; create a new production account and use sample data for your first verification.

## 3. Create the Render service

Either choose **New → Blueprint**, connect the GitHub repository and use `render.yaml`, or choose **New → Web Service**, connect the repo and enter:

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
| `DATABASE_URL` | Neon secret connection string |
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
8. Redeploy/restart and verify saved records remain (they live in Neon).

For production checks from a trusted local shell with production environment variables set, run `python manage.py check --deploy`. Never copy credentials into command history unnecessarily; a separate ignored local env file or host secret manager is preferable.

## Free-tier constraints

Render free web services sleep after inactivity and use an ephemeral filesystem. This project stores extracted resume text in PostgreSQL rather than saving uploaded files to that filesystem. Free Render PostgreSQL databases expire after 30 days; the guide uses external Neon storage to avoid that specific expiry. Neon also has free-plan storage/compute quotas and scale-to-zero behavior. Check dashboards for current allowances. Neither provider promises unlimited capacity or a permanently unchanged free plan.

Gemini free-tier model availability and rate limits vary. The app retains your selected model and never silently switches models. Use AI Studio's current pricing/usage display and keep billing disabled if you want a strict no-charge demo. Transient failures receive at most three retries with 1/2/4-second backoff and small jitter within an 80-second retry window. Later request timeouts shrink to the remaining window; `Retry-After` is respected or the app falls back. Every attempt counts against the daily request limit. Permanent errors fall back immediately. Read-inactivity/DNS limitations mean this window is not a strict wall-clock guarantee; the existing worker timeout remains 90 seconds.

## Troubleshooting and maintenance

- **DisallowedHost / 400:** add the exact hostname to `ALLOWED_HOSTS`, with no scheme or path.
- **CSRF / 403:** use an HTTPS origin in `CSRF_TRUSTED_ORIGINS`; refresh the form after deployment.
- **Database connection error:** verify the Neon project is available, credentials are current, and SSL is enabled. Use a new secret connection string if a credential was exposed.
- **Missing CSS:** ensure `collectstatic` completed and the vendored stylesheet was committed.
- **Gemini local fallback:** inspect the on-screen reason, key, model access and provider quota. The app deliberately avoids displaying raw provider errors or keys.
- **Cold start / timeout:** wait for the sleeping service to wake up. One worker limits memory use; two threads keep small requests responsive during an AI call.
- **PDF unreadable:** use text-based, unencrypted documents, at most 20 pages and 5 MB. OCR is not included.
- **Admin:** create a superuser through a trusted environment connected to production, or use the provider's shell if available on your plan. No admin creation endpoint is exposed.

Keep regular PostgreSQL backups before schema changes. Review dependencies and rerun tests when updating. Do not remove migration files after deployment. Production uses secure cookies, HTTPS redirects and HSTS; its proxy-header setting assumes Render is the trusted TLS-terminating proxy.

Live deployment and PostgreSQL smoke tests remain account-dependent. The repository includes a PostgreSQL GitHub Actions job, which runs after you push; a successful local SQLite run does not claim PostgreSQL was already tested live.
