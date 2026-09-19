import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
if not SECRET_KEY or SECRET_KEY == 'replace-with-a-long-random-secret':
    raise ImproperlyConfigured('Set a random DJANGO_SECRET_KEY in .env or your host environment.')
ALLOWED_HOSTS = [s.strip() for s in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if s.strip()]
if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(os.environ['RENDER_EXTERNAL_HOSTNAME'])
CSRF_TRUSTED_ORIGINS = [s.strip() for s in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if s.strip()]
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'assistant']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'careerpilot.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'careerpilot.wsgi.application'
database_url = os.getenv('DATABASE_URL', '')
if not DEBUG and not database_url.startswith(('postgres://', 'postgresql://')):
    raise ImproperlyConfigured('Production requires a PostgreSQL DATABASE_URL.')
DATABASES = {'default': dj_database_url.parse(database_url, conn_max_age=60, conn_health_checks=True) if database_url else {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
if not DEBUG:
    DATABASES['default']['OPTIONS'] = {'sslmode': 'require'}
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.' + name} for name in ['UserAttributeSimilarityValidator', 'MinimumLengthValidator', 'CommonPasswordValidator', 'NumericPasswordValidator']]
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'home'
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.8-flash')
try:
    GEMINI_READ_TIMEOUT_SECONDS = int(os.getenv('GEMINI_READ_TIMEOUT_SECONDS', '60'))
except ValueError as exc:
    raise ImproperlyConfigured('GEMINI_READ_TIMEOUT_SECONDS must be an integer between 1 and 60.') from exc
if not 1 <= GEMINI_READ_TIMEOUT_SECONDS <= 60:
    raise ImproperlyConfigured('GEMINI_READ_TIMEOUT_SECONDS must be between 1 and 60 (the production worker timeout is 90 seconds).')
# Later attempts use the time left in this window, not another full minute.
GEMINI_RETRY_BUDGET_SECONDS = 80
AI_DAILY_LIMIT = int(os.getenv('AI_DAILY_LIMIT', '15'))
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
