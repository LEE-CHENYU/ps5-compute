"""Independently verify exact rational answers in captured PS5 readback logs."""
import json
import gzip
from fractions import Fraction
from pathlib import Path
import re
import sys

def expected(round,kind,index):
    row,col=divmod(index,13)
    x=[Fraction(((row*16+k)*7+round*3)%19-9,8) for k in range(16)]
    w=[Fraction(((k*13+col)*11+round*5)%23-11,8) for k in range(16)]
    answer=sum(a*b for a,b in zip(x,w))
    return max(answer+Fraction((col*3+round)%7-3,4),0) if kind else answer

def verify(path):
    suites=[];current=None
    wanted={(r,k,i) for r in range(3) for k in range(2) for i in range(91)}
    cases={(r,k) for r in range(3) for k in range(2)}
    content=gzip.decompress(path.read_bytes()).decode() if path.suffix=='.gz' else path.read_text()
    for line in content.splitlines():
        if line.startswith('ML_FAIL') or 'RETAIN' in line:
            raise ValueError('Capture contains a failure or retained resources')
        if line.startswith('ML_BOOT '):
            if current is not None:raise ValueError('Previous suite had no pass marker')
            current={'seen':set(),'dispatches':set(),'results':set()}
        elif line.startswith('ML_VALUE '):
            fields=dict(re.findall(r'(\w+)=([^ ]+)',line));key=tuple(int(fields[k]) for k in ['round','kind','index'])
            if current is None or key in current['seen']:raise ValueError('Value without suite or duplicate readback')
            if key not in wanted:raise ValueError('Out-of-range readback: '+str(key))
            if Fraction(fields['actual'])!=expected(*key):raise ValueError('GPU result mismatch: '+str(key))
            current['seen'].add(key)
        elif line.startswith('PS5VK_QUEUE_COMPLETED '):
            if current is None:raise ValueError('Dispatch without a suite')
            fields=dict(re.findall(r'(\w+)=([^ ]+)',line))
            token=fields['token']
            if token in current['dispatches']:raise ValueError('Duplicate completion token')
            current['dispatches'].add(token)
        elif line.startswith('ML_RESULT '):
            fields=dict(re.findall(r'(\w+)=([^ ]+)',line))
            key=tuple(int(fields[k]) for k in ['round','kind'])
            if current is None or key not in cases or key in current['results']:
                raise ValueError('Missing suite, unknown case or duplicate result')
            if int(fields['checked'])!=91:raise ValueError('Incomplete result')
            if any(int(fields[k]) for k in ['errors','guard_errors','input_errors']):raise ValueError('Device reported a validation error')
            current['results'].add(key)
        elif line.startswith('ML_PASS '):
            if current is None or current['seen']!=wanted or len(current['dispatches'])!=6 or current['results']!=cases:
                raise ValueError('Incomplete suite')
            suites.append(current);current=None
    if current is not None or not suites:raise ValueError('Incomplete capture')
    result={'verified':True,'suites':len(suites),'gpu_dispatches':len(suites)*6,'values':len(suites)*546,'exact_rational_match':True}
    return result

if __name__=='__main__':print(json.dumps(verify(Path(sys.argv[1]))))
