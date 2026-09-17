#!/usr/bin/env python3
"""Copy a verified release into a real Doubao user-skill directory."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

NAME = 'kang-doubao-pindou'
ROOT = Path(__file__).resolve().parent
TOP = {'SKILL.md', 'README.md', 'install.py', 'LICENSE', 'requirements.txt',
       'requirements.lock', '.gitignore'}
TREES = {'scripts', 'tests', 'references', 'licenses', 'assets', 'reports'}


class InstallError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def temporary_location(path):
    actual = Path(path).resolve()
    for item in ('/runtime', '/tmp', '/var/tmp', '/var/folders', tempfile.gettempdir()):
        parent = Path(item).resolve()
        if actual == parent or parent in actual.parents:
            return True
    return False


def real_path(path):
    """Do not follow a directory link while copying executable release files."""
    path = Path(os.path.abspath(Path(path).expanduser()))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise InstallError('SYMLINK_CONFLICT', f'路径包含软链接，未覆盖：{path}')
    return path


def release_files(source):
    source = Path(source).resolve()
    manifest_path = source / 'MANIFEST.json'
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise InstallError('MANIFEST_MISSING', '包根目录缺少真实 MANIFEST.json，请使用完整发布包。')
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or not TOP.difference({'.gitignore'}).issubset(manifest):
        raise InstallError('INCOMPLETE_RELEASE', '发布包缺少必要文件，请下载完整新版包。')
    if len(manifest) + 1 > 200:
        raise InstallError('INVALID_RELEASE', '发布包文件数量超过 200。')
    total = 0
    files = {}
    for name, digest in manifest.items():
        rel = Path(name)
        if (rel.is_absolute() or '..' in rel.parts or str(rel) != name or
                not rel.parts or (len(rel.parts) == 1 and name not in TOP) or
                (len(rel.parts) > 1 and rel.parts[0] not in TREES) or
                any(p.startswith('.') or p == '__pycache__' for p in rel.parts if p != '.gitignore')):
            raise InstallError('INVALID_RELEASE', f'清单包含不允许的路径：{name}')
        path = source / rel
        # Check every relative parent using its actual absolute location.
        if any((source / p).is_symlink() for p in (rel, *rel.parents)):
            raise InstallError('INVALID_RELEASE', f'包目录不能是软链接：{name}')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise InstallError('HASH_MISMATCH', f'文件校验失败，未安装：{name}')
        files[name] = data
        total += len(data)
    if total + manifest_path.stat().st_size > 10_000_000:
        raise InstallError('INVALID_RELEASE', '发布包总大小超过 10 MB。')
    files['MANIFEST.json'] = manifest_path.read_bytes()
    text = files['SKILL.md'].decode('utf-8')
    if not text.startswith('---\n') or len(text.split('---', 2)) != 3 or not re.search(
            r'^name: kang-doubao-pindou$', text.split('---', 2)[1], re.M):
        raise InstallError('INVALID_SKILL', 'SKILL.md 元信息缺失或技能名称不匹配。')
    return files


def run(command, cwd, seconds):
    proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=seconds)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        raise InstallError('INSTALL_TIMEOUT', '安装超时或中断；目标文件和已有环境保留，可重新运行安装器。')
    if proc.returncode:
        raise InstallError('ENVIRONMENT_FAILED', '环境步骤失败，未宣告安装成功：' + (err or out)[-1200:])
    return out


def prepare_environment(target):
    env = target / '.venv'
    if env.is_symlink():
        raise InstallError('VENV_LINK_CONFLICT', '目标 .venv 是软链接；请保留旧环境，在目标目录另建真实虚拟环境。')
    python = env / 'bin/python'
    created = not env.exists()
    if created:
        run([sys.executable, '-m', 'venv', str(env)], target, 60)
    if not python.is_file():
        raise InstallError('VENV_BROKEN', '目标已有虚拟环境无法使用；保留旧环境后在此位置重建。')
    prefix = json.loads(run([str(python), '-c',
        'import json,sys;print(json.dumps({"prefix":sys.prefix,"base":sys.base_prefix}))'], target, 10))
    if Path(prefix['prefix']).resolve() != env.resolve() or prefix['prefix'] == prefix['base']:
        raise InstallError('VENV_BROKEN', '目标解释器没有使用此位置的虚拟环境，未修改系统依赖。')
    if created:
        print('首次安装固定依赖；后续安装将复用可用环境。', file=sys.stderr)
        run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
             '--no-input', '--require-hashes', '-r', str(target / 'requirements.lock')], target, 180)
    result = json.loads(run([str(python), str(target / 'scripts/pindou.py'),
                             'doctor', '--repair'], target, 60))
    if not result.get('ok'):
        raise InstallError('ENVIRONMENT_FAILED', result.get('message', '依赖检查失败。'))
    return str(python), result


def install(source=ROOT, skills_dir=None):
    if sys.version_info < (3, 10) or os.name != 'posix':
        raise InstallError('PYTHON_REQUIRED', '请使用 Python 3.10+ 和 Linux/macOS；Windows 请使用 WSL。')
    files = release_files(source)
    scan = real_path(skills_dir or Path.home() / '.doubao/agent_mode/workspace/.user_skills')
    if scan.name != '.user_skills' or temporary_location(scan):
        raise InstallError('INVALID_SKILLS_DIR', '目标必须是宿主实际扫描的非临时 .user_skills 目录，不能使用 .skills 或 /runtime。')
    if not scan.is_dir():
        raise InstallError('SKILLS_DIR_MISSING', f'用户技能目录不存在：{scan}。请先核实宿主路径，再创建该目录并重试。')
    target = real_path(scan / NAME)
    if target.exists() and not target.is_dir():
        raise InstallError('TARGET_CONFLICT', f'目标不是文件夹，未覆盖：{target}')
    if (target / '.venv').is_symlink():
        raise InstallError('VENV_LINK_CONFLICT', '目标已有 .venv 软链接，未覆盖；请先保留旧环境并在目标目录重建。')
    path = real_path(target / 'INSTALLATION.json')
    if path.exists() and not path.is_file():
        raise InstallError('TARGET_CONFLICT', 'INSTALLATION.json 已是目录，未覆盖。')
    # Preflight every public file before changing the installation.
    changed = []
    for rel, data in files.items():
        dest = real_path(target / rel)
        if any(p.exists() and not p.is_dir() for p in dest.parents if p != target):
            raise InstallError('TARGET_CONFLICT', f'父路径不是文件夹：{dest}')
        if dest.exists() and not dest.is_file():
            raise InstallError('TARGET_CONFLICT', f'发布文件位置已有其他目录：{dest}')
        if not dest.exists() or dest.read_bytes() != data:
            changed.append(rel)
    backups = scan.parent / 'pindou-install-backups'
    existing = [rel for rel in changed if (target / rel).exists()]
    backup = None
    if existing:
        real_path(backups).mkdir(exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-'), dir=backups))
        for rel in existing:
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / rel, dest)
    target.mkdir(exist_ok=True)
    for rel in changed:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent, prefix='.pindou-', delete=False) as temp:
            temp.write(files[rel])
            staged = Path(temp.name)
        try:
            staged.replace(dest)
        finally:
            if staged.exists():
                staged.unlink()
    python, doctor = prepare_environment(target)
    record = {'schema': 1, 'skill_path': str(target), 'python_path': python,
              'scan_path': str(scan), 'changed_files': changed,
              'backup_path': str(backup) if backup else None,
              'cross_session_verified': False, 'host_registration': 'unverified'}
    with tempfile.NamedTemporaryFile(dir=target, prefix='.installation-', mode='w', delete=False) as temp:
        json.dump(record, temp, ensure_ascii=False, indent=2)
        temp.write('\n')
        staged = Path(temp.name)
    staged.replace(path)
    return {'ok': True, 'code': 'INSTALLED_LOCAL', **record, 'environment': doctor,
            'message': '已复制到真实用户技能目录，依赖检查通过。请重启对话后检查生效；宿主发现与跨窗口保留尚未验证。'}


def main():
    parser = argparse.ArgumentParser(description='将完整拼豆技能复制到豆包真实用户技能目录。')
    parser.add_argument('--skills-dir', help='仅当宿主明确使用其他 .user_skills 路径时指定。')
    args = parser.parse_args()
    try:
        result = install(skills_dir=args.skills_dir)
    except (InstallError, OSError, ValueError, KeyError, TypeError) as exc:
        result = {'ok': False, 'code': getattr(exc, 'code', 'INSTALL_FAILED'), 'message': str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
