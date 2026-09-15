#!/usr/bin/env python3
"""Extract, install locked requirements, run tests and a complete synthetic CLI flow."""
import argparse,hashlib,json,os,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--zip',required=True);ap.add_argument('--report',default=str(ROOT/'reports/clean-room.json'));a=ap.parse_args();archive=Path(a.zip).resolve();start=time.monotonic()
    stages=[]
    with tempfile.TemporaryDirectory(prefix='pindou-clean-') as temp:
        temp=Path(temp)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            for n in z.namelist():
                p=Path(n);assert not p.is_absolute() and '..' not in p.parts
                assert p.parts[0]=='kang-doubao-pindou'
                assert not any(x in p.parts for x in ('.venv','node_modules','__pycache__','.research','runs','.git'))
                assert not p.name.startswith('.env')
            z.extractall(temp)
        skill=temp/'kang-doubao-pindou';manifest=json.loads((skill/'MANIFEST.json').read_text())
        for rel,sha in manifest.items():assert hashlib.sha256((skill/rel).read_bytes()).hexdigest()==sha
        def run(label,cmd,timeout=180):
            t=time.monotonic();r=subprocess.run(cmd,cwd=skill,capture_output=True,text=True,timeout=timeout)
            stages.append({'stage':label,'seconds':round(time.monotonic()-t,3),'exit_code':r.returncode})
            if r.returncode:raise RuntimeError(label+'\n'+r.stdout[-3000:]+'\n'+r.stderr[-3000:])
            return r
        run('create-independent-venv',[sys.executable,'-m','venv',str(skill/'.venv')])
        py=str(skill/'.venv/bin/python')
        run('first-install-separate',[py,'-m','pip','install','--require-hashes','-r','requirements.lock'])
        run('doctor',[py,'scripts/pindou.py','doctor','--repair'])
        run('simulate-one-missing-package',[py,'-m','pip','uninstall','-y','PyYAML'])
        repaired=json.loads(run('minimal-repair',[py,'scripts/pindou.py','doctor','--repair']).stdout)
        assert repaired['actions']==[{'action':'repair_dependencies','packages':['PyYAML'],'returncode':0}],repaired
        reused=json.loads(run('healthy-repair-reuse',[py,'scripts/pindou.py','doctor','--repair']).stdout)
        assert reused['ok'] and reused['reused'] and not reused['actions'],reused
        run('automated-tests',[py,'scripts/run_tests.py','--report',str(temp/'tests.json')])
        run('full-synthetic-cli-stages',[py,'scripts/fast_benchmark.py','--runs','1','--out',str(temp/'synthetic-work'),'--report',str(temp/'benchmark.json')])
        # Repack inside the clean root without relying on developer-only files.
        run('repack',[py,'scripts/package_skill.py','--out',str(temp/'repacked.zip')])
        tests=json.loads((temp/'tests.json').read_text())
        report={'scope':'clean local extraction/install/test, NOT Doubao import','zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'manifest_verified':True,'forbidden_paths_absent':True,'repacked':True,'stages':stages,'tests':tests,'seconds':round(time.monotonic()-start,3),'installation_note':'fresh venv, existing pip download cache may be reused; network/environment specific'}
    Path(a.report).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
