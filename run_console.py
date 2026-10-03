#!/usr/bin/env python3
"""Stage, byte-verify and launch only this project's native test title."""
import argparse
import ftplib
import hashlib
import io
import json
from pathlib import Path
import socket
import time
from settings import require_host

ROOT=Path(__file__).resolve().parent

def shell(command, timeout=8):
    config=require_host()
    with socket.create_connection((config['host'],config['shell_port']),4) as s:
        s.settimeout(timeout); s.sendall((command+'\necho ML_COMMAND_END\n').encode())
        chunks=b''
        try:
            while b'ML_COMMAND_END' not in chunks:
                chunk=s.recv(65536)
                if not chunk:break
                chunks+=chunk
        except TimeoutError:pass
        # shsrv's greeting contains a device serial; do not persist it.
        text=chunks.decode(errors='replace')
        return text[text.find('/$'):] if '/$' in text else ''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=45)
    parser.add_argument('--resume-staging',action='store_true')
    parser.add_argument('--reuse-installed',action='store_true')
    parser.add_argument('--update-installed',action='store_true')
    args=parser.parse_args()
    config=require_host()
    if args.seconds < 1:raise SystemExit('--seconds must be positive')
    manifest=json.loads((ROOT/'build/manifest.json').read_text())
    build_id=manifest['build_id']; dist=ROOT/'dist/PPSA99991'
    for name,digest in manifest['files'].items():
        if hashlib.sha256((dist/name).read_bytes()).hexdigest()!=digest:
            raise SystemExit('Local artifact differs from its manifest')
    processes=shell('ps')
    if not processes or 'ML_COMMAND_END' not in processes:
        raise SystemExit('Console shell did not respond; no files were changed')
    if any('eboot.bin' in line for line in processes.splitlines()):
        raise SystemExit('An eboot process is running; inspect before launching a new title')
    f=ftplib.FTP();f.connect(config['host'],config['ftp_port'],5);f.login();f.timeout=20
    # ftpsrv SELF is a session toggle, not a per-transfer command. Disable
    # automatic decryption once, so both the SELF and PRX preserve their bytes.
    if 'disabled' not in f.sendcmd('SELF').lower():
        raise SystemExit('Could not select byte-preserving FTP mode')
    def mkdir(path):
        try:f.mkd(path)
        except ftplib.error_perm:
            f.cwd(path);f.cwd('/')
    mkdir('/data/ps5-ml');mkdir('/data/homebrew')
    destination='/data/homebrew/PPSA99991'
    staging=f'/data/homebrew/.ps5ml-{build_id}'
    rootlist=[];f.retrlines('LIST /data/homebrew',rootlist.append)
    existing={line.split(None,8)[-1] for line in rootlist}
    if args.update_installed:
        if args.reuse_installed:raise SystemExit('Choose update or reuse')
        data=io.BytesIO();f.retrbinary('RETR '+destination+'/ml-manifest.json',data.write)
        old=json.loads(data.getvalue())
        if set(old['files'])!=set(manifest['files']):raise SystemExit('Installed file set changed; inspect manually')
        backup=f"/data/ps5-ml/backup-{old['build_id']}-{time.time_ns()}"
        mkdir(backup)
        for folder in ['sce_sys','sce_module']:mkdir(backup+'/'+folder)
        # Preserve the registered directory inode: ShadowMount's nullfs mount
        # points there. Back up and verify old files, then replace each file.
        for name,digest in old['files'].items():
            previous=io.BytesIO();f.retrbinary('RETR '+destination+'/'+name,previous.write)
            if hashlib.sha256(previous.getvalue()).hexdigest()!=digest:
                raise SystemExit('Installed source differs from its manifest: '+name)
            previous.seek(0);f.storbinary('STOR '+backup+'/'+name,previous)
            check=hashlib.sha256();f.retrbinary('RETR '+backup+'/'+name,check.update)
            if check.hexdigest()!=digest:raise SystemExit('Backup mismatch: '+name)
        f.storbinary('STOR '+backup+'/ml-manifest.json',io.BytesIO(json.dumps(old).encode()))
        for name,digest in manifest['files'].items():
            if old['files'][name]==digest:continue
            temporary=destination+'/'+name+'.ml-next'
            with (dist/name).open('rb') as source:f.storbinary('STOR '+temporary,source,65536)
            check=hashlib.sha256();f.retrbinary('RETR '+temporary,check.update,65536)
            if check.hexdigest()!=digest:raise SystemExit('Update readback mismatch: '+name)
            f.rename(temporary,destination+'/'+name)
        f.storbinary('STOR '+destination+'/ml-manifest.json',io.BytesIO(json.dumps(manifest).encode()))
        args.reuse_installed=True
    if (destination.rsplit('/',1)[-1] in existing and not args.reuse_installed) or (staging.rsplit('/',1)[-1] in existing and not args.resume_staging):
        raise SystemExit('Build already staged: inspect it instead of overwriting')
    target=destination if args.reuse_installed else staging
    if not args.reuse_installed:
        mkdir(staging)
        for folder in ['sce_sys','sce_module']:mkdir(staging+'/'+folder)
    for name,digest in manifest['files'].items():
        folder,_,basename=name.rpartition('/')
        entries=[];f.retrlines('LIST '+target+('/'+folder if folder else ''),entries.append)
        present={line.split(None,8)[-1] for line in entries}
        if basename not in present:
            if args.reuse_installed:raise SystemExit('Installed file missing: '+name)
            with (dist/name).open('rb') as source:f.storbinary('STOR '+target+'/'+name,source,65536)
        result=hashlib.sha256();f.retrbinary('RETR '+target+'/'+name,result.update,65536)
        if result.hexdigest()!=digest:raise SystemExit('Upload readback mismatch: '+name)
    if not args.reuse_installed:
        f.storbinary('STOR '+staging+'/ml-manifest.json',io.BytesIO(json.dumps(manifest).encode()))
        f.rename(staging,destination)
        # Registration is asynchronous; launching immediately races the scan.
        for _ in range(20):
            rows=[]
            try:f.retrlines('LIST /user/appmeta/PPSA99991',rows.append)
            except ftplib.error_perm:pass
            if any('param.json' in row for row in rows):break
            time.sleep(1)
        else:raise SystemExit('Title not registered yet; retry with --reuse-installed')
    evidence=ROOT/'runs'/(build_id+'-'+str(time.time_ns()));evidence.mkdir(parents=True,exist_ok=False)
    (evidence/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (evidence/'deployment.json').write_text(json.dumps({'destination':destination,'readback_verified':True},indent=2)+'\n')
    # Delete only our previous log so this launch cannot reuse stale evidence.
    try:f.delete('/data/ps5-ml/latest.log')
    except ftplib.error_perm as error:
        if not str(error).startswith('550'):raise
    launch=shell('launch PPSA99991',timeout=8)
    (evidence/'launch.log').write_text(launch)
    print(launch,flush=True)
    time.sleep(args.seconds)
    data=io.BytesIO()
    try:f.retrbinary('RETR /data/ps5-ml/latest.log',data.write)
    except ftplib.all_errors:pass
    f.close()
    local=data.getvalue();(evidence/'console.log').write_bytes(local)
    # A previous run's persistent log cannot validate this build.
    combined=local if build_id.encode() in local else b''
    print(combined.decode(errors='replace')[-6000:])
    print('Evidence:',evidence)
    if not combined:raise SystemExit('No log from this build received')
    if b'ML_FAIL' in combined or b'RETAIN' in combined:raise SystemExit('Console test failed or retained resources')
    expected=b'DASHBOARD_READY' if manifest.get('dashboard') else b'ML_PREFLIGHT_PASS' if manifest['preflight'] else b'ML_PASS'
    if expected not in combined:raise SystemExit('No pass marker: inspect logs')

if __name__=='__main__':main()
