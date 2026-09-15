"""Standard-library preflight and opt-in minimal repair; no clone or full test run."""
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
MODULES={'numpy':'numpy','Pillow':'PIL.Image','reportlab':'reportlab.pdfgen.canvas','charset-normalizer':'charset_normalizer','pypdf':'pypdf','pypdfium2':'pypdfium2','PyYAML':'yaml'}


def check(root=None, probe=False):
    root=Path(root or ROOT);errors=[];versions={};needed=[]
    if sys.version_info<(3,10):errors.append('需要 Python 3.10 或更新版本')
    if os.name!='posix':errors.append('需要 POSIX 文件锁；Windows 请使用 WSL')
    for line in (root/'requirements.txt').read_text().splitlines():
        if not line.strip() or line.startswith('#'):continue
        name,expected=line.split('==')
        try:actual=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:actual='missing'
        versions[name]=actual
        if actual!=expected:needed.append(name);errors.append(f'{name}：需要 {expected}，当前 {actual}')
    if probe and not needed:
        # One fresh child catches a broken binary install without contaminating the supervisor.
        code="import importlib,json;bad=[]\nfor name,mod in "+repr(MODULES)+".items():\n try: importlib.import_module(mod)\n except Exception: bad.append(name)\nprint(json.dumps(bad))"
        try:
            p=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
            bad=json.loads(p.stdout) if p.returncode==0 else list(MODULES)
        except (OSError,ValueError,subprocess.TimeoutExpired):bad=list(MODULES)
        needed.extend(bad)
        errors.extend(f'{name}：无法正常导入，需要修复' for name in bad)
    return {'ok':not errors,'code':'READY' if not errors else 'DEPENDENCY_ERROR',
            'message':'环境已就绪，可复用。' if not errors else '环境未就绪，请修复列出的依赖。',
            'python':sys.version.split()[0],'python_path':sys.executable,'skill_path':str(root.resolve()),
            'versions':versions,'errors':errors,'needed':needed,'doubao_host':'unverified',
            'persistence':'unknown; must be verified by the host','host_interrupt':'unknown','host_timestamps':'unknown'}


def selected_lock(root, needed):
    content=(Path(root)/'requirements.lock').read_text();blocks=re.split(r'(?m)(?=^[A-Za-z0-9][A-Za-z0-9_.-]*==)',content)
    selected=[]
    for block in blocks:
        match=re.match(r'([A-Za-z0-9_.-]+)==',block)
        if match and match[1] in needed:
            if '--hash=sha256:' not in block:raise ValueError('锁定文件缺少哈希')
            selected.append(block)
    if len(selected)!=len(needed):raise ValueError('锁定文件缺少所需依赖')
    return '\n'.join(selected)


def doctor(repair=False, link=None):
    start=time.monotonic();result=check(probe=True);actions=[]
    if link and not repair:return {**result,'ok':False,'code':'REPAIR_REQUIRED','message':'重建链接需要 --repair。'}
    if repair and result['needed']:
        if sys.prefix==sys.base_prefix:
            return {**result,'ok':False,'code':'VENV_REQUIRED','message':'请使用持久安装目录的虚拟环境 Python 运行修复，不修改系统环境。','actions':actions}
        from .cli import run_bounded
        try:
            text=selected_lock(ROOT,result['needed'])
            with tempfile.TemporaryDirectory(prefix='pindou-repair-') as tmp:
                lock=Path(tmp)/'repair.lock';lock.write_text(text)
                code,out,err=run_bounded([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-input','--no-deps','--require-hashes','--force-reinstall','-r',str(lock)],max(.1,55-(time.monotonic()-start)))
            actions.append({'action':'repair_dependencies','packages':result['needed'],'returncode':code})
            if code:return {**result,'ok':False,'code':'REPAIR_FAILED','message':'依赖修复未完成；保留已有环境，请检查网络或所需平台发行包。','actions':actions,'details':err[-1000:]}
            result=check(probe=True)
        except (OSError,ValueError) as exc:return {**result,'ok':False,'code':'REPAIR_FAILED','message':str(exc),'actions':actions}
    if repair and result['ok'] and link:
        target=Path(link).expanduser().absolute()
        if target.is_symlink() and target.resolve()==ROOT.resolve():actions.append({'action':'reuse_link','path':str(target)})
        elif target.exists() or target.is_symlink():
            return {**result,'ok':False,'code':'LINK_CONFLICT','message':'链接位置已有其他文件或目标；未覆盖，请指定空位置。','actions':actions}
        else:
            target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(ROOT.resolve(),target_is_directory=True)
            actions.append({'action':'create_link','path':str(target)})
    return {**result,'actions':actions,'reused':result['ok'] and not any(a['action']=='repair_dependencies' for a in actions), 'seconds':round(time.monotonic()-start,6)}
