"""Build a portable source archive using an explicit allowlist (no .env/data)."""
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent.parent
out = root / 'outputs'
out.mkdir(exist_ok=True)
files = ['.env.example', '.gitignore', 'LICENSE', 'README.md', 'manage.py', 'render.yaml', 'requirements.txt', 'requirements-lock.txt']
folders = ['assistant', 'careerpilot', 'templates', 'static', 'docs', 'scripts', 'samples', '.github']
paths = [root / name for name in files]
for folder in folders:
    paths.extend(p for p in (root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
with ZipFile(out / 'CareerPilot-AI-source.zip', 'w', ZIP_DEFLATED) as archive:
    for path in sorted(paths):
        archive.write(path, Path('CareerPilot-AI') / path.relative_to(root))
(out / 'README.md').write_text((root / 'README.md').read_text(encoding='utf-8').replace('(docs/', '('), encoding='utf-8')
for name in ['DEPLOYMENT.md', 'INTERVIEW_GUIDE.md', 'NEXT_STEPS.md']:
    copyfile(root / 'docs' / name, out / name)
print(f'Packaged {len(paths)} source files. Secrets and user data excluded.')
