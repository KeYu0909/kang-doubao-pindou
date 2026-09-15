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

class JSONParser(argparse.ArgumentParser):
    def error(self,message):
        print(json.dumps({'ok':False,'code':'ARGUMENT_ERROR','message':'命令参数不完整或不正确，请按用法修正。','error':message},ensure_ascii=False))
        raise SystemExit(2)

def parser():
    p=JSONParser(description='永康玩AI · 拼豆助手：分阶段制作，绑定作品版本，返回JSON结果')
    p.add_argument('--budget-seconds',type=float,default=60,help='本地命令共享预算（大于0且不超过60秒），不代表宿主端到端耗时')
    p.add_argument('--submitted-at',type=float,help='可选：真实提交时间戳，仅使用本阶段剩余预算')
    sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('doctor',help='检查并复用环境；--repair 仅修复缺失项');q.add_argument('--repair',action='store_true');q.add_argument('--link',help='需要恢复的临时技能入口绝对路径')
    def cmd(name):
        q=sub.add_parser(name);q.add_argument('--project',required=True);return q
    def selection(q, flag):
        group=q.add_mutually_exclusive_group(required=True);group.add_argument(flag);group.add_argument('--current',action='store_true',help='在命令内部读取当前版本')
    q=cmd('init');q.add_argument('--input',required=True);q.add_argument('--source',required=True);q.add_argument('--request',default='');q.add_argument('--preserve',action='append',default=[]);q.add_argument('--simulated',action='store_true')
    q=cmd('begin');q.add_argument('--kind',choices=['edit','pixel'],required=True);selection(q,'--base');q.add_argument('--request',required=True);q.add_argument('--preserve',action='append',default=[])
    q=cmd('claim-call');selection(q,'--operation');q.add_argument('--mode',choices=['host','simulated'],required=True)
    q=cmd('edit');selection(q,'--operation');q.add_argument('--input');q.add_argument('--based-on-sha');q.add_argument('--origin',choices=['host','manual','simulated']);q.add_argument('--crop',type=int,nargs=4,metavar=('LEFT','TOP','WIDTH','HEIGHT'));q.add_argument('--remove-edge');q.add_argument('--tolerance',type=int,default=12)
    q=cmd('pixel');selection(q,'--base');q.add_argument('--width',type=int);q.add_argument('--height',type=int);q.add_argument('--max-colors',type=int);q.add_argument('--palette');q.add_argument('--reserve',action='append');q.add_argument('--sampling',choices=['box','nearest']);q.add_argument('--input');q.add_argument('--operation');q.add_argument('--based-on-sha');q.add_argument('--protect',help='JSON保护色号、格子或区域')
    q=cmd('denoise');selection(q,'--base');q.add_argument('--mode',choices=['light','balanced','strong'],default='light');q.add_argument('--max-colors',type=int);q.add_argument('--protect')
    q=cmd('confirm');selection(q,'--revision');q.add_argument('--stage',choices=['edit','pixel','png'],required=True);q.add_argument('--message',required=True)
    q=cmd('png');selection(q,'--revision')
    q=cmd('export');selection(q,'--revision');q.add_argument('--format',choices=['csv','pdf'],required=True);q.add_argument('--spare-percent',type=float,default=0);q.add_argument('--cell-pt',type=int,default=None);q.add_argument('--layout',choices=['standard','large'],default='standard')
    q=cmd('rollback');q.add_argument('--revision',required=True)
    q=cmd('cancel');selection(q,'--operation')
    q=cmd('preview-result');selection(q,'--revision');q.add_argument('--outcome',choices=['success','fail'],required=True)
    q=cmd('present');selection(q,'--revision');q.add_argument('--conversation',required=True);q.add_argument('--artifact',choices=['candidate','preview','pattern'],required=True);q.add_argument('--message-ref',required=True);q.add_argument('--ambiguous',action='store_true')
    q=cmd('offer');selection(q,'--revision');q.add_argument('--conversation',required=True);q.add_argument('--options',required=True)
    q=cmd('route');q.add_argument('--conversation',required=True);q.add_argument('--message',required=True);q.add_argument('--message-ref',required=True);q.add_argument('--revision');q.add_argument('--current',action='store_true');q.add_argument('--layout',choices=['standard','large'])
    cmd('status');cmd('validate');q=cmd('inspect');q.add_argument('--current',action='store_true')
    q=cmd('record-delivery');selection(q,'--revision');q.add_argument('--artifact',required=True);q.add_argument('--scope',choices=['doubao','manual-fallback','local-observation'],required=True);q.add_argument('--user-submitted-at',dest='submitted_at',type=float,required=True);q.add_argument('--delivered-at',type=float,required=True);q.add_argument('--quality',choices=['qualified','unqualified'],required=True);q.add_argument('--evidence',required=True)
    q=cmd('record-stage');q.add_argument('--phase',choices=['ai_thinking','image_tool','preview_delivery','post_script_wait'],required=True);q.add_argument('--scope',choices=['doubao','manual-fallback'],required=True);q.add_argument('--started-at',type=float,required=True);q.add_argument('--ended-at',type=float,required=True);q.add_argument('--evidence',required=True)
    return p

def doctor():
    from .environment import check
    return check()

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
    if a.command in ('present','offer','preview-result','record-delivery') and getattr(a,'current',False):
        a.revision=w.snapshot(a.project)['current_revision']
    if a.command in ('present','offer','route','inspect'):
        from . import interaction
        return getattr(interaction,a.command)(a)
    if a.command=='init':return w.init_project(a)
    if a.command=='status':return w.view(a.project,w.snapshot(a.project))
    if a.command=='png':return w.attach(a,'pattern')
    if a.command=='export':return w.attach(a,a.format)
    return {'begin':w.begin,'claim-call':w.claim_call,'edit':w.edit,'pixel':w.pixel,'denoise':w.denoise,'confirm':w.confirm,'rollback':w.rollback,'cancel':w.cancel,'preview-result':w.preview_result,'validate':w.validate,'record-delivery':w.delivery,'record-stage':w.record_stage}[a.command](a)

MESSAGES={'EDIT_NOT_CONFIRMED':'请先确认当前编辑图。','PIXEL_NOT_CONFIRMED':'请先确认当前像素预览。',
'PNG_NOT_CONFIRMED':'请先展示并确认当前正式 PNG。','MODIFICATION_PENDING':'当前有未完成修改，请先完成或取消该修改。',
'PROTECTION_COLOR_CONFLICT':'保护色数量超过目标色数；请提高色数，或由用户明确调整保护范围。',
'TARGET_COLORS_REQUIRED':'强力简化需要明确目标色数，请选择例如 16、12 或 8 色。',
'COLOR_REDUCTION_REQUIRED':'强力简化的目标色数需小于当前实际色数。',
'STALE_BASE':'当前版本已变化，请使用 --current 执行当前版本。',
'STALE_RESULT':'执行期间版本已变化，本次结果没有覆盖当前作品。',
'TIMEOUT':'本阶段已超时；已有作品保留，请查看失败阶段。'}

def error_result(exc):
    raw=str(exc);code=raw.split(':',1)[0]
    if not code or not all(c.isupper() or c=='_' or c.isdigit() for c in code):code='EXECUTION_ERROR'
    return {'ok':False,'code':code,'message':MESSAGES.get(code,'操作未完成，请根据错误详情处理当前步骤。'),'error':raw}

def main():
    started=time.time();mono=time.monotonic();a=parser().parse_args()
    if a.command=='doctor':
        from .environment import doctor as environment_doctor
        try:result=environment_doctor(a.repair,a.link)
        except Exception as exc:result=error_result(exc)
        print(json.dumps(result,ensure_ascii=False));return 0 if result['ok'] else 2
    if os.environ.get('PINDOU_WORKER')=='1':
        try:
            result=worker(a);print(json.dumps({'ok':True,**result},ensure_ascii=False));return 0
        except Exception as exc:
            print(json.dumps(error_result(exc),ensure_ascii=False));return 2
    check=doctor()
    if not check['ok']:print(json.dumps({'ok':False,'code':'DEPENDENCY_ERROR','message':'缺少所需依赖，请使用现有环境运行 doctor --repair。','error':'DEPENDENCY_ERROR','details':check}));return 2
    if not 0<a.budget_seconds<=60: print(json.dumps(error_result('BUDGET: 0 < seconds <= 60'),ensure_ascii=False));return 2
    remaining=a.budget_seconds-(time.monotonic()-mono)
    if a.submitted_at is not None and a.command!='record-delivery':
        if a.submitted_at>started+1:print(json.dumps(error_result('SUBMISSION_TIME: cannot be in future'),ensure_ascii=False));return 2
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
    if not result.get('ok') and 'code' not in result:result.update(error_result(result.get('error','WORKER_FAILED')))
    if a.command!='status':
        result.pop('revisions',None)
        if result.get('parameters'):result['parameters']={k:v for k,v in result['parameters'].items() if k!='processing'}
    result['timing']=event;result['host_e2e_seconds']=None
    print(json.dumps(result,ensure_ascii=False));return code
