import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]

def parser():
    p=argparse.ArgumentParser(description='永康玩AI · 拼豆助手：分阶段制作，绑定作品版本，返回JSON结果')
    p.add_argument('--budget-seconds',type=float,default=60,help='本地命令共享预算（大于0且不超过60秒），不代表宿主端到端耗时')
    p.add_argument('--submitted-at',type=float,help='可选：真实提交时间戳，仅使用本阶段剩余预算')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor',help='检查已安装依赖版本，不自动安装')
    def cmd(name):
        q=sub.add_parser(name);q.add_argument('--project',required=True);return q
    q=cmd('init');q.add_argument('--input',required=True);q.add_argument('--source',required=True);q.add_argument('--request',default='');q.add_argument('--preserve',action='append',default=[]);q.add_argument('--simulated',action='store_true')
    q=cmd('begin');q.add_argument('--kind',choices=['edit','pixel'],required=True);q.add_argument('--base',required=True);q.add_argument('--request',required=True);q.add_argument('--preserve',action='append',default=[])
    q=cmd('claim-call');q.add_argument('--operation',required=True);q.add_argument('--mode',choices=['host','simulated'],required=True)
    q=cmd('edit');q.add_argument('--operation',required=True);q.add_argument('--input');q.add_argument('--based-on-sha');q.add_argument('--origin',choices=['host','manual','simulated']);q.add_argument('--crop',type=int,nargs=4,metavar=('LEFT','TOP','WIDTH','HEIGHT'));q.add_argument('--remove-edge');q.add_argument('--tolerance',type=int,default=12)
    q=cmd('pixel');q.add_argument('--base',required=True);q.add_argument('--width',type=int);q.add_argument('--height',type=int);q.add_argument('--max-colors',type=int);q.add_argument('--palette');q.add_argument('--reserve',action='append');q.add_argument('--sampling',choices=['box','nearest']);q.add_argument('--input');q.add_argument('--operation');q.add_argument('--based-on-sha')
    q=cmd('confirm');q.add_argument('--revision',required=True);q.add_argument('--stage',choices=['edit','pixel','png'],required=True);q.add_argument('--message',required=True)
    q=cmd('png');q.add_argument('--revision',required=True)
    q=cmd('export');q.add_argument('--revision',required=True);q.add_argument('--format',choices=['csv','pdf'],required=True);q.add_argument('--spare-percent',type=float,default=0);q.add_argument('--cell-pt',type=int,default=None);q.add_argument('--layout',choices=['standard','large'],default='standard')
    q=cmd('rollback');q.add_argument('--revision',required=True)
    q=cmd('cancel');q.add_argument('--operation',required=True)
    q=cmd('preview-result');q.add_argument('--revision',required=True);q.add_argument('--outcome',choices=['success','fail'],required=True)
    q=cmd('present');q.add_argument('--revision',required=True);q.add_argument('--conversation',required=True);q.add_argument('--artifact',choices=['candidate','preview','pattern'],required=True);q.add_argument('--message-ref',required=True);q.add_argument('--ambiguous',action='store_true')
    q=cmd('offer');q.add_argument('--revision',required=True);q.add_argument('--conversation',required=True);q.add_argument('--options',required=True)
    q=cmd('route');q.add_argument('--conversation',required=True);q.add_argument('--message',required=True);q.add_argument('--message-ref',required=True);q.add_argument('--revision');q.add_argument('--layout',choices=['standard','large'])
    cmd('status');cmd('validate');cmd('inspect')
    q=cmd('record-delivery');q.add_argument('--revision',required=True);q.add_argument('--artifact',required=True);q.add_argument('--scope',choices=['doubao','manual-fallback','local-observation'],required=True);q.add_argument('--user-submitted-at',dest='submitted_at',type=float,required=True);q.add_argument('--delivered-at',type=float,required=True);q.add_argument('--quality',choices=['qualified','unqualified'],required=True);q.add_argument('--evidence',required=True)
    return p

def doctor():
    errors=[];versions={}
    if sys.version_info<(3,10):errors.append('需要Python 3.10或更新版本')
    if os.name!='posix':errors.append('需要POSIX进程组与文件锁；Windows请使用WSL')
    for line in (ROOT/'requirements.txt').read_text().splitlines():
        name,expected=line.split('==')
        try: actual=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: actual='missing'
        versions[name]=actual
        if actual!=expected:errors.append(f'{name} expected {expected}, found {actual}')
    return {'ok':not errors,'python':sys.version.split()[0],'versions':versions,'errors':errors,'install_command':'python -m pip install --require-hashes -r requirements.lock','doubao_host':'unverified','host_interrupt':'unknown','host_timestamps':'unknown'}

def run_bounded(command,budget,env=None):
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,env=env)
    try:
        out,err=proc.communicate(timeout=budget)
        return proc.returncode,out,err
    except (subprocess.TimeoutExpired,KeyboardInterrupt):
        # Kill the complete owned process group, then reap the child, not merely stop waiting.
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        proc.communicate()
        return 124,'','TIMEOUT: owned process group terminated; no successful delivery claimed'

def worker(a):
    from . import workflow as w
    if a.command in ('present','offer','route','inspect'):
        from . import interaction
        return getattr(interaction,a.command)(a)
    if a.command=='init':return w.init_project(a)
    if a.command=='status':return w.view(a.project,w.snapshot(a.project))
    if a.command=='png':return w.attach(a,'pattern')
    if a.command=='export':return w.attach(a,a.format)
    return {'begin':w.begin,'claim-call':w.claim_call,'edit':w.edit,'pixel':w.pixel,'confirm':w.confirm,'rollback':w.rollback,'cancel':w.cancel,'preview-result':w.preview_result,'validate':w.validate,'record-delivery':w.delivery}[a.command](a)

def main():
    started=time.time();mono=time.monotonic();a=parser().parse_args()
    if a.command=='doctor':
        result=doctor();print(json.dumps(result));return 0 if result['ok'] else 2
    if os.environ.get('PINDOU_WORKER')=='1':
        try:
            result=worker(a);print(json.dumps({'ok':True,**result},ensure_ascii=False));return 0
        except Exception as exc:
            print(json.dumps({'ok':False,'error':f'{type(exc).__name__}: {exc}'},ensure_ascii=False));return 2
    check=doctor()
    if not check['ok']:print(json.dumps({'ok':False,'error':'DEPENDENCY_ERROR','details':check}));return 2
    if not 0<a.budget_seconds<=60: print(json.dumps({'ok':False,'error':'BUDGET: 0 < seconds <= 60'}));return 2
    remaining=a.budget_seconds-(time.monotonic()-mono)
    if a.submitted_at is not None and a.command!='record-delivery':
        if a.submitted_at>started+1:print(json.dumps({'ok':False,'error':'SUBMISSION_TIME: cannot be in future'}));return 2
        remaining=min(remaining,a.budget_seconds-(time.time()-a.submitted_at))
    job='job'+uuid.uuid4().hex;env=os.environ.copy();env.update(PINDOU_WORKER='1',PINDOU_JOB=job,PINDOU_DEADLINE=str(time.monotonic()+remaining))
    if remaining<=0:code,out,err=124,'','TIMEOUT: stage budget already exhausted; worker not started'
    else:code,out,err=run_bounded([sys.executable,str(ROOT/'scripts/pindou.py'),*sys.argv[1:]],remaining,env)
    try:result=json.loads(out)
    except ValueError:result={'ok':False,'error':err.strip() or 'WORKER_FAILED: no valid result'}
    seconds=time.monotonic()-mono
    event={'event':'local_command','job_id':job,'command':a.command,'started_at':started,'seconds':round(seconds,6),'status':'success' if code==0 else ('timeout' if code==124 else 'error'),'scope':'local-command-only','error':result.get('error'),'retries':0,'generative_calls_performed_by_script':0}
    project=Path(a.project).resolve()
    if project.is_dir():
        from .common import audit
        audit(project,event)
        shutil.rmtree(project/'.staging'/job,ignore_errors=True)
    result['timing']=event;result['host_e2e_seconds']=None
    print(json.dumps(result,ensure_ascii=False));return code
