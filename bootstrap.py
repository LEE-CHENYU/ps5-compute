#!/usr/bin/env python3
"""Fetch pinned public dependencies and build the PS5 shader compiler."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dependencies import DEPS, ROOT, SDK_SHA256, SDK_URL, build_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=6)
    parser.add_argument('--skip-compiler', action='store_true', help='Fetch sources and SDK only')
    parser.add_argument('--clean-compiler', action='store_true', help='Rebuild PSBC after changing the SDK/toolchain')
    args = parser.parse_args()
    env = build_environment()
    for name, (origin, pin) in DEPS.items():
        dest = ROOT / 'vendor' / name
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'init', str(dest)], check=True)
            subprocess.run(['git', '-C', str(dest), 'remote', 'add', 'origin', f'https://github.com/{origin}.git'], check=True)
            subprocess.run(['git', '-C', str(dest), 'fetch', '--depth=1', 'origin', pin], check=True)
            subprocess.run(['git', '-C', str(dest), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
        actual = subprocess.check_output(['git', '-C', str(dest), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(dest), 'diff', 'HEAD', '--'], text=True)
        if actual != pin or dirty:
            raise SystemExit(f'Inspect {dest}: revision differs or tracked sources are modified; nothing was reset')
        print(f'{name}: {pin}', flush=True)
    sdk = Path(env['PS5_PAYLOAD_SDK'])
    if not sdk.exists():
        sdk.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=sdk.parent) as temporary:
            archive = Path(temporary) / 'sdk.zip'
            urllib.request.urlretrieve(SDK_URL, archive)
            if hashlib.sha256(archive.read_bytes()).hexdigest() != SDK_SHA256:
                raise SystemExit('SDK archive digest mismatch')
            # Extraction is permitted only after the pinned archive digest matches.
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(temporary)
                for item in bundle.infolist():
                    mode = (item.external_attr >> 16) & 0o777
                    if mode:
                        (Path(temporary) / item.filename).chmod(mode)
            shutil.move(str(Path(temporary) / 'ps5-payload-sdk'), sdk)
    if not (sdk / 'bin/prospero-clang').is_file():
        raise SystemExit(f'Incomplete SDK at {sdk}; no existing files were replaced')
    vk = ROOT / 'vendor/ps5-vulkan'
    for script in ['prepare_vulkan_headers.py', 'prepare_compiler_deps.py']:
        subprocess.run([sys.executable, str(vk / 'tools' / script), '--check'], env=env, check=True)
    if not args.skip_compiler:
        subprocess.run([sys.executable, str(vk / 'tools/build_psbc.py'), '--target', 'ps5', '-j', str(args.jobs),
                        *(['--clean'] if args.clean_compiler else [])], env=env, check=True)
    print('Dependencies ready. Run: python build.py --dashboard')


if __name__ == '__main__':
    main()
