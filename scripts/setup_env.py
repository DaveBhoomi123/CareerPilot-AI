"""Create a local .env once, without printing or overwriting secrets."""
from pathlib import Path
import secrets
root = Path(__file__).resolve().parent.parent
target = root / '.env'
if target.exists():
    print('.env already exists; left unchanged.')
else:
    text = (root / '.env.example').read_text(encoding='utf-8')
    target.write_text(text.replace('replace-with-a-long-random-secret', secrets.token_urlsafe(64)), encoding='utf-8')
    print('Created .env with a random local secret. Gemini is optional.')
