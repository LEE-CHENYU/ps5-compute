#!/usr/bin/env python3
"""Build a native PS5 compute title on macOS from pinned public sources."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from dependencies import PINS, build_environment

ROOT = Path(__file__).resolve().parent
VK = ROOT / 'vendor/ps5-vulkan'
GEARS = ROOT / 'vendor/ps5-agc-gears'
BASE = ROOT / 'vendor/ps5-native-app-boilerplate'
ENV = build_environment()
SDK = Path(ENV['PS5_PAYLOAD_SDK'])
BUILD = ROOT / 'build'
DIST = ROOT / 'dist/PPSA99991'
CC = ['sh', str(BASE/'tooling/prospero-clang18')]
LD = SDK/'bin/prospero-lld'

def run(*args):
    subprocess.run([str(a) for a in args], env=ENV, check=True)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    unknown = set(sys.argv[1:]) - {'--preflight', '--dashboard'}
    if unknown:
        raise SystemExit('Usage: python build.py [--preflight | --dashboard]')
    preflight = '--preflight' in sys.argv
    dashboard = '--dashboard' in sys.argv
    if preflight and dashboard:raise SystemExit('Choose preflight or dashboard')
    for repo, pin in PINS.items():
        actual = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
        if actual != pin:
            raise SystemExit(f'Unexpected revision: {repo}: {actual}')
    for path in [BUILD/'obj', BUILD/'stubs', DIST/'sce_sys', DIST/'sce_module', BASE/'build/host']:
        path.mkdir(parents=True, exist_ok=True)
    # Public clean-room runtime; compare against the foundation's published digest.
    builder = BASE/'build/host/ps5-native-tool'
    libc_builder = BASE/'build/host/libc-builder'
    if not builder.exists():
        run(os.environ.get('HOST_CXX','clang++'),'-std=c++20','-O2',*[BASE/'tooling/native'/f'{s}.cpp' for s in
            ['native_app_builder','self_container','elf_object','sce_module_writer']],'-lz','-o',builder)
    if not libc_builder.exists():
        run(os.environ.get('HOST_CXX','clang++'),'-std=c++20','-O2',BASE/'tooling/native/libc_builder.cpp','-o',libc_builder)
    run(libc_builder,BASE/'tooling/native/runtime/api-surface.txt',
        BASE/'tooling/native/runtime/imports.txt',BUILD/'libc.raw.elf')
    run(builder,'self','--sign','--in',BUILD/'libc.raw.elf','--out',DIST/'sce_module/libc.prx')
    expected = (BASE/'runtime/libc.prx.sha256').read_text().split()[0]
    if sha(DIST/'sce_module/libc.prx') != expected:
        raise SystemExit('Clean-room libc digest mismatch')
    header = []
    for name,activation in [('matmul',0),('dense',1)]:
        out=BUILD/f'{name}.spv'
        run('glslangValidator','-V','--target-env','vulkan1.0',f'-DACTIVATION={activation}',
            ROOT/'shaders/dense.comp','-o',out)
        run('spirv-val','--target-env','vulkan1.0',out)
        words=struct.unpack('<'+'I'*(out.stat().st_size//4),out.read_bytes())
        header.append(f'static const uint32_t {name}_spirv[]={{'+','.join(hex(w)+'u' for w in words)+'};')
    (BUILD/'shaders.h').write_text('\n'.join(header)+'\n')
    identity=hashlib.sha256()
    for path in sorted([*ROOT.glob('src/*'),*ROOT.glob('shaders/*'),*ROOT.glob('tools/*.py'),*ROOT.glob('*.py'),*ROOT.glob('assets/fonts/*')]):
        identity.update(path.read_bytes())
    identity.update(str(preflight).encode())
    identity.update(str(dashboard).encode())
    build_id=identity.hexdigest()[:16]
    (BUILD/'build_id.h').write_text(f'#define ML_BUILD_ID "{build_id}"\n#define ML_PREFLIGHT {int(preflight)}\n#define ML_DASHBOARD {int(dashboard)}\n')
    if dashboard:run(sys.executable,ROOT/'tools/make_fonts.py')
    run(sys.executable,ROOT/'tools/make_icon.py')
    includes=[ROOT/'src',BUILD,VK/'src',VK/'native',GEARS/'include',
              VK/'third_party/vulkan-headers/include',VK/'third_party/psbc-reference',
              VK/'third_party/psbc-reference/src',VK/'third_party/psbc-reference/libpsbc',
              VK/'third_party/opengnm/include']
    flags=['-std=c11','-O2','-g','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections',
           '-DPS5VK_RUNTIME_COMPILER=1','-DPS5VK_TARGET_PS5=1','-DPS5VK_NO_OFFLINE_LIBRARY=1',
           *['-I'+str(p) for p in includes]]
    # Compile only the compute backend. Public front-end helpers are archived so
    # the linker can select their actual dependencies without graphics backends.
    excluded={'platform_host.c','ps5vk_present.c'}
    sources=[p for p in sorted((VK/'src').glob('*.c')) if p.name not in excluded]
    sources += [VK/'native'/n for n in ['platform_ps5.c','memory_ps5.c','queue_ps5.c']]
    objects=[]
    def compile_source(source):
        obj=BUILD/'obj'/('vk_'+source.stem+'.o')
        run(*CC,*flags,'-c',source,'-o',obj)
        return obj
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        objects=list(executor.map(compile_source,sources))
    run(SDK/'bin/prospero-ar','rcs',BUILD/'libps5vk-compute.a',*objects)
    app=[]
    for name in ['main','log','compute_only']+(['dashboard','dashboard_draw'] if dashboard else []):
        obj=BUILD/'obj'/f'ml_{name}.o'
        run(*CC,*flags,'-c',ROOT/'src'/f'{name}.c','-o',obj);app.append(obj)
    crt=BUILD/'obj/crt.o'
    run(*CC,'-std=c++20','-O2','-fno-exceptions','-fno-rtti','-c',BASE/'tooling/native/app_crt.cpp','-o',crt)
    stubs=[]
    for name in ['libSceAgc','libSceAgcDriver']:
        obj=BUILD/'obj'/f'{name}.o'; so=BUILD/'stubs'/f'{name}.so'
        run(*CC,'-fPIC','-c',GEARS/'native/stubs'/f'{name}.c','-o',obj)
        run(LD,'--shared','-soname',f'{name}.prx','-o',so,obj); stubs.append(so)
    psbc=VK/'build/libpsbc.ps5.a'
    psbc_meta=json.loads(psbc.with_suffix('.json').read_text())
    if psbc_meta['archive_sha256']!=sha(psbc) or psbc_meta['source_commit']!=PINS[VK/'third_party/psbc-reference']:
        raise SystemExit('PSBC archive identity mismatch')
    libraries=[BUILD/'libps5vk-compute.a',psbc,*[SDK/'target/lib'/n for n in
        ['libc++.a','libc++abi.a','libunwind.a','libpthread.a','libc.a']]]
    run(LD,'-L'+str(SDK/'target/lib'),'-T',VK/'native/ps5-pie.ld','--eh-frame-hdr',
        '--version-script',VK/'native/app-symbols.map','-e','_start','--gc-sections',
        '-o',BUILD/'pie.elf',crt,*app,'--start-group',*libraries,'--end-group','--as-needed',
        *sorted((SDK/'target/lib').glob('*.so')),*stubs)
    run(builder,'link','--in',BUILD/'pie.elf','--out',BUILD/'eboot.elf','--stub-dir',SDK/'target/lib',
        '--module-sdk','0x02000009',*[arg for p in stubs for arg in ['--stub',p]],
        '--companion-sdk','0x08050001','--file-name','eboot.elf')
    run(builder,'self','--sign','--in',BUILD/'eboot.elf','--out',DIST/'eboot.bin','--magic','0x1D3D154F')
    param=json.loads((GEARS/'sce_sys/param.json').read_text())
    param.update(titleId='PPSA99991',conceptId='99991',contentId='UP9000-PPSA99991_00-NATIVEMLCOMPUTE1')
    param['localizedParameters']['en-US']['titleName']='PS5 Compute' if dashboard else 'PS5 ML - GPU Test'
    (DIST/'sce_sys/param.json').write_text(json.dumps(param,indent=2)+'\n')
    shutil.copyfile(BUILD/'icon0.png',DIST/'sce_sys/icon0.png')
    manifest={'build_id':build_id,'preflight':preflight,'dashboard':dashboard,'upstream':{str(k.relative_to(ROOT)):v for k,v in PINS.items()},
              'files':{str(p.relative_to(DIST)):sha(p) for p in DIST.rglob('*') if p.is_file()}}
    (BUILD/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'build_id':build_id,'preflight':preflight,'dist':str(DIST)}))

if __name__=='__main__':main()
