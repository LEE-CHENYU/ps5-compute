"""Create a per-user macOS app that opens this checkout's local dashboard."""
import plistlib
import shlex
import subprocess
from pathlib import Path
from PIL import Image
from make_icon import make_icon

ROOT = Path(__file__).resolve().parents[1]
app = Path.home() / 'Applications/PS5 Compute Dashboard.app'
marker = app / 'Contents/Resources/project.txt'
if app.exists() and (not marker.exists() or marker.read_text().strip() != str(ROOT)):
    raise SystemExit('An unrelated app already occupies the requested launcher path')
for folder in ['Contents/MacOS', 'Contents/Resources']:
    (app / folder).mkdir(parents=True, exist_ok=True)
marker.write_text(str(ROOT) + '\n')
image = make_icon()
iconset = ROOT / 'build/dashboard.iconset'
iconset.mkdir(parents=True, exist_ok=True)
for size in [16, 32, 128, 256, 512]:
    for scale, suffix in [(1, ''), (2, '@2x')]:
        image.resize((size * scale, size * scale), Image.Resampling.LANCZOS).save(iconset / f'icon_{size}x{size}{suffix}.png')
subprocess.run(['/usr/bin/iconutil', '-c', 'icns', str(iconset), '-o', str(app / 'Contents/Resources/AppIcon.icns')], check=True)
launcher = app / 'Contents/MacOS/launcher'
launcher.write_text('#!/bin/zsh\nexec ' + shlex.quote(str(ROOT / 'Launch Dashboard.command')) + '\n')
launcher.chmod(0o755)
with (app / 'Contents/Info.plist').open('wb') as f:
    plistlib.dump({
        'CFBundleName': 'PS5 Compute Dashboard', 'CFBundleDisplayName': 'PS5 Compute Dashboard',
        'CFBundleIdentifier': 'local.ps5compute.dashboard', 'CFBundleExecutable': 'launcher',
        'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1', 'CFBundleIconFile': 'AppIcon',
        'LSUIElement': True}, f)
print(app)
