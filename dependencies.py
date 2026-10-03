"""Public source revisions and configurable host toolchain paths."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DEPS = {
    'ps5-vulkan': ('mpereiraesaa/ps5-vulkan', 'e6d3c3f82f3c8a574e28c174b15b287f9c0ecc6d'),
    'ps5-agc-gears': ('mpereiraesaa/ps5-agc-gears', '1ae1f9182abd2770c131b97419034fb85173c2dc'),
    'ps5-native-app-boilerplate': ('blackbearreloaded/ps5-native-app-boilerplate', '37dd53602bdead63936f718004555ba10154be48'),
    'ps5-vulkan/third_party/psbc-reference': ('mpereiraesaa/opengnm-psbc', '4fe7264a0cab9feb531a156e8a810b3e39cfe42c'),
    'ps5-vulkan/third_party/opengnm': ('PS4-OpenGNM/opengnm', '4b295ca54c82c83acf308d1c646a2dfa9ae57350'),
    'ps5-vulkan/third_party/vulkan-headers': ('KhronosGroup/Vulkan-Headers', 'b51f6b865c18fc5b33990d12f75e8dfd672cede6'),
}
PINS = {ROOT / 'vendor' / path: pin for path, (_, pin) in DEPS.items()}
SDK_URL = 'https://github.com/ps5-payload-dev/sdk/releases/download/v0.43/ps5-payload-sdk.zip'
SDK_SHA256 = 'a9cc9929f21b2b2c5d5b309f3bab4997067c45281c0622cf4838b1aecba66fcb'


def build_environment():
    env = dict(os.environ)
    sdk = Path(env.get('PS5_PAYLOAD_SDK', ROOT / 'vendor/ps5-payload-sdk')).expanduser().resolve()
    llvm = env.get('LLVM_CONFIG') or shutil.which('llvm-config-18')
    if not llvm:
        for prefix in ['/opt/homebrew/opt/llvm@18', '/usr/local/opt/llvm@18']:
            candidate = Path(prefix) / 'bin/llvm-config'
            if candidate.is_file():
                llvm = str(candidate)
                break
    if not llvm:
        raise SystemExit('LLVM 18 is required; set LLVM_CONFIG to llvm-config from LLVM 18')
    version = subprocess.check_output([llvm, '--version'], text=True).strip()
    if not version.startswith('18.'):
        raise SystemExit(f'Expected LLVM 18, got {version}')
    bindir = subprocess.check_output([llvm, '--bindir'], text=True).strip()
    env.update(PS5_PAYLOAD_SDK=str(sdk), LLVM_CONFIG=llvm,
               PS5_CLANG=env.get('PS5_CLANG', str(Path(bindir) / 'clang')))
    env['PATH'] = os.pathsep.join([str(Path(sys.executable).parent), bindir, env.get('PATH', '')])
    return env
