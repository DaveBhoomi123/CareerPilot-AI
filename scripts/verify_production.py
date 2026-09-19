"""Check production settings without contacting a real database or exposing secrets."""
import os
import secrets
import subprocess
import sys
env = os.environ.copy()
env.update(DEBUG='False', DJANGO_SECRET_KEY=secrets.token_urlsafe(64),
           DATABASE_URL='postgresql://check:unused@localhost/careerpilot',
           ALLOWED_HOSTS='careerpilot.example.com',
           CSRF_TRUSTED_ORIGINS='https://careerpilot.example.com')
subprocess.run([sys.executable, 'manage.py', 'check', '--deploy', '--fail-level', 'WARNING'], env=env, check=True)
