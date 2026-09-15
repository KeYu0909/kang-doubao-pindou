#!/usr/bin/env python3
"""Save a project-visible locator; never claim filesystem access registers a host skill."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from pindou.environment import ROOT, temporary_path, storage_status

NAME='pindou-install.json'


def probe(skill, python):
    if not (skill/'SKILL.md').is_file() or not (skill/'scripts/pindou.py').is_file():
        raise ValueError('记录的技能文件已不可用；从完整技能包恢复，保留原作品。')
    if not python.is_file():
        raise ValueError('记录的 Python 已不可用；在最终持久目录重建虚拟环境。')
    p=subprocess.run([str(python),str(skill/'scripts/pindou.py'),'doctor'],
                     cwd=skill,capture_output=True,text=True,timeout=30)
    result=json.loads(p.stdout)
    if p.returncode or not result.get('ok'):
        raise ValueError('记录的环境未就绪；使用该安装的 doctor --repair 修复必要依赖。')
    return result


def record(project, retention_note):
    project=Path(project).expanduser().resolve()
    if not retention_note.strip():raise ValueError('请记录宿主提供的真实保存范围与依据。')
    status=storage_status(ROOT)
    if status['temporary'] or temporary_path(project):
        raise ValueError('不能将临时目录登记为持久安装；先将源码、虚拟环境及项目放入宿主确认保留的目录。')
    # Keep the venv interpreter path: resolving its symlink would select system Python.
    python=Path(os.path.abspath(sys.executable))
    if sys.prefix==sys.base_prefix:raise ValueError('请用最终安装目录内的虚拟环境 Python 运行。')
    if ROOT.resolve() not in Path(sys.prefix).resolve().parents:
        raise ValueError('虚拟环境应建在最终技能目录内；不要登记外部或已搬迁的环境。')
    probe(ROOT,python)
    data={'schema':1,'skill_path':str(ROOT.resolve()),'python_path':str(python),
          'project_path':str(project),'retention_note':retention_note,
          'cross_session_verified':False,'host_registration':'unverified'}
    project.mkdir(parents=True,exist_ok=True)
    path=project/NAME
    if path.exists():
        previous=json.loads(path.read_text())
        if previous.get('skill_path')!=data['skill_path'] or previous.get('python_path')!=data['python_path']:
            raise ValueError('项目已有其他安装记录；先核对并备份原记录，不自动覆盖。')
    temp=path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temp.replace(path)
    return {'ok':True,'record':str(path),'message':'安装位置已记录；尚未验证新窗口可发现。请将此记录加入宿主项目说明或可持续读取的项目文件。',**data}


def check(path):
    data=json.loads(Path(path).read_text())
    if data.get('schema')!=1:raise ValueError('不支持的安装记录格式。')
    for key in ('skill_path','python_path','project_path'):
        if not Path(data[key]).is_absolute():raise ValueError('安装记录必须使用绝对路径。')
    if not Path(data['project_path']).is_dir():raise ValueError('记录的作品目录不可用；请打开原项目或恢复真实备份。')
    result=probe(Path(data['skill_path']),Path(data['python_path']))
    return {'ok':True,'code':'REACHABLE_NOW','message':'记录的安装在当前窗口可访问；跨窗口保留范围与技能入口仍由宿主核实。',
            'installation':data,'environment':result}


def main():
    parser=argparse.ArgumentParser(description='记录或检查拼豆安装位置，不自动注册宿主技能。')
    sub=parser.add_subparsers(dest='action',required=True)
    create=sub.add_parser('record');create.add_argument('--project',required=True);create.add_argument('--retention-note',required=True)
    read=sub.add_parser('check');read.add_argument('--record',required=True)
    args=parser.parse_args()
    try:
        result=record(args.project,args.retention_note) if args.action=='record' else check(args.record)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        result={'ok':False,'code':'INSTALL_RECORD_ERROR','message':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ok'] else 2


if __name__=='__main__':sys.exit(main())
