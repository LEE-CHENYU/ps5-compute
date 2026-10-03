#!/usr/bin/env python3
"""Local-only dashboard bridge. Reads actual PS5 state; queues bounded jobs."""
import ftplib
import http.server
import io
import json
import secrets
import socket
import sys
import threading
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from run_console import shell
from settings import require_host
PORT=8894
LOCK=threading.Lock();TOKEN=secrets.token_urlsafe(32)
STORE=ROOT/'web/state';STORE.mkdir(exist_ok=True)
CACHE={'online':False,'data':None,'error':'Waiting for the PS5 dashboard','history':[],'age_s':None}
try:CACHE['history']=json.loads((STORE/'history.json').read_text())
except (OSError,ValueError):pass
try:CACHE['data']=json.loads((STORE/'latest.json').read_text())
except (OSError,ValueError):pass

def ftp():
    config=require_host()
    f=ftplib.FTP();f.connect(config['host'],config['ftp_port'],3);f.login();f.timeout=3;return f

def poll():
    previous=None;last_change=0
    while True:
        start=time.monotonic()
        try:
            f=ftp();buf=io.BytesIO()
            try:f.retrbinary('RETR /data/ps5-ml/status.json',buf.write)
            finally:f.close()
            data=json.loads(buf.getvalue())
            if data.get('schema')!=1:raise ValueError('Unsupported console status format')
            beat=(data.get('pid'),data.get('heartbeat'))
            if previous is not None and beat!=previous:last_change=start
            previous=beat;age=start-last_change if last_change else None
            live=age is not None and age<5
            with LOCK:
                CACHE.update(data=data,online=live,age_s=round(age,1) if age is not None else None,
                             error=None if live else 'Waiting for a fresh dashboard heartbeat')
                if live and data.get('phase')=='Passed' and not data.get('running'):
                    key=f"{data.get('pid')}:{data.get('run_id')}:{data.get('completed')}:{data.get('elapsed_s')}"
                    if not any(h['id']==key for h in CACHE['history']):
                        CACHE['history'].insert(0,{'id':key,'recorded_at':time.strftime('%Y-%m-%d %H:%M:%S'),**data})
                        CACHE['history']=CACHE['history'][:20]
                        (STORE/'history.json').write_text(json.dumps(CACHE['history'],indent=2))
            (STORE/'latest.json').write_text(json.dumps(data,indent=2))
        except (OSError,ValueError,ftplib.Error) as error:
            with LOCK:CACHE.update(online=False,error='PS5 dashboard unavailable. Open PS5 Compute on the console.',age_s=None)
        delay=1-(time.monotonic()-start)
        if delay>0:time.sleep(delay)

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,format,*args):pass
    def local_request(self):
        # Reject foreign Host/Origin headers, including DNS-rebinding requests.
        hosts={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        return self.headers.get('Host') in hosts and self.headers.get('Origin') in ({None}|{'http://'+host for host in hosts})
    def respond(self,code,body,kind='application/json'):
        if isinstance(body,(dict,list)):body=json.dumps(body).encode()
        if isinstance(body,str):body=body.encode()
        self.send_response(code);self.send_header('Content-Type',kind)
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if not self.local_request():return self.respond(403,{'error':'Local dashboard requests only'})
        if self.path=='/api/status':
            with LOCK:payload={**CACHE,'csrf':TOKEN}
            self.respond(200,payload)
        elif self.path in ['/','/index.html']:
            self.respond(200,(ROOT/'web/index.html').read_bytes(),'text/html; charset=utf-8')
        else:self.respond(404,{'error':'Not found'})
    def do_POST(self):
        if not self.local_request():return self.respond(403,{'error':'Local dashboard requests only'})
        if self.path!='/api/task':return self.respond(404,{'error':'Not found'})
        if self.headers.get('X-Dashboard-Token')!=TOKEN:return self.respond(403,{'error':'Reload the dashboard before sending a task'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<1024:raise ValueError('Invalid request')
            command=json.loads(self.rfile.read(length)).get('task')
            if command not in ['once','repeat','launch']:raise ValueError('Unknown task')
            with LOCK:current=dict(CACHE)
            if command=='launch':
                if current['online']:return self.respond(200,{'message':'Dashboard is already open'})
                processes=shell('ps')
                if not processes or 'ML_COMMAND_END' not in processes:raise ValueError('Console shell did not respond')
                if any('eboot' in row for row in processes.splitlines()):raise ValueError('Close the running game first, then launch the dashboard')
                output=shell('launch PPSA99991')
                if 'Resource temporarily unavailable' in output or 'failed' in output.lower():raise ValueError('Console did not accept the launch request')
                return self.respond(202,{'message':'Launch requested. Waiting for the console heartbeat.'})
            if not current['online']:raise ValueError('Open PS5 Compute on the console first')
            if current['data'].get('running') or current['data'].get('failed'):raise ValueError('The runner is busy or needs to be closed after an error')
            f=ftp()
            try:
                f.storbinary('STOR /data/ps5-ml/command.next',io.BytesIO((command+'\n').encode()))
                f.rename('/data/ps5-ml/command.next','/data/ps5-ml/command.txt')
            finally:f.close()
            self.respond(202,{'message':'Task queued on PS5'})
        except (OSError,ValueError,ftplib.Error) as error:self.respond(409,{'error':str(error)})

if __name__=='__main__':
    server=http.server.ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    threading.Thread(target=poll,daemon=True).start()
    print(f'PS5 Compute dashboard: http://127.0.0.1:{PORT}',flush=True)
    server.serve_forever()
