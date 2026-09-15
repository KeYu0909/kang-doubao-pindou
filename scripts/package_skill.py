#!/usr/bin/env python3
"""Allowlist archive: excludes dependencies, inputs, runtime data, credentials and research."""
import argparse,hashlib,json,re,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES={'SKILL.md','README.md','LICENSE','requirements.txt','requirements.lock','.gitignore'}
TREES={'scripts':{'.py'},'tests':{'.py'},'references':{'.md','.json','.csv'},'licenses':{'.txt'},'assets':{'.json','.ttf'},'reports':{'.json','.md','.jsonl'}}
REPORTS={'test-results.json','benchmark.json','development-report.md','experiment-notes.md','pdf-comparison.json','v3-baseline-tests.json','v3-acceptance.md','fast-path-benchmark.json','fast-path-events.jsonl'}

def collect():
    paths=[ROOT/f for f in sorted(FILES)]
    for dirname,suffixes in TREES.items():
        for p in (ROOT/dirname).rglob('*'):
            if p.is_file() and not p.is_symlink() and p.suffix in suffixes and '__pycache__' not in p.parts:
                if dirname=='reports' and p.name not in REPORTS:continue
                paths.append(p)
    for p in paths:
        if not p.is_file() or p.is_symlink():raise ValueError(f'Required file missing or symlink: {p}')
        if p.stat().st_size>1_000_000:raise ValueError(f'Unexpected large file: {p}')
    return sorted(paths)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default=str(ROOT/'dist/kang-doubao-pindou.zip'));args=parser.parse_args()
    skill=(ROOT/'SKILL.md').read_text();assert skill.startswith('---\n')
    front=skill.split('---',2)[1]
    assert re.search(r'^name: kang-doubao-pindou$',front,re.M)
    assert re.search(r'^description: .+',front,re.M)
    paths=collect();out=Path(args.out).resolve();out.parent.mkdir(parents=True,exist_ok=True)
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in paths:z.write(p,'kang-doubao-pindou/'+str(p.relative_to(ROOT)))
        z.writestr('kang-doubao-pindou/MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        for rel,sha in manifest.items():assert hashlib.sha256(z.read('kang-doubao-pindou/'+rel)).hexdigest()==sha
    print(json.dumps({'zip':str(out),'files':len(paths)+1,'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'doubao_import':'not tested'},indent=2))
if __name__=='__main__':main()
