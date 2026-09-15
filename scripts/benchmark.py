#!/usr/bin/env python3
"""Synthetic local benchmark only. Simulated confirmations do NOT measure Doubao."""
import argparse,json,subprocess,sys,time
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runs',type=int,default=3);ap.add_argument('--out',default=str(ROOT/'runs/benchmark'));ap.add_argument('--report',default=str(ROOT/'reports/benchmark.json'));ap.add_argument('--synthetic-confirmations',action='store_true',required=True);a=ap.parse_args()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True);require_new=not (out/'run-1').exists()
    if not require_new:raise SystemExit('Benchmark directory already used; choose a new --out path.')
    source=out/'synthetic-geometry.png';im=Image.new('RGB',(1440,1920),'white');d=ImageDraw.Draw(im)
    d.rounded_rectangle((220,450,1220,1660),radius=120,fill='#008CB6',outline='#263341',width=45)
    d.polygon([(400,450),(720,90),(1040,450)],fill='#E64245',outline='#263341',width=35)
    d.ellipse((620,55,820,255),fill='#FFD54A',outline='#263341',width=25)
    d.rounded_rectangle((340,670,1100,1200),radius=80,fill='#F9F0CD',outline='#263341',width=35)
    d.ellipse((430,800,570,940),fill='#388C60');d.ellipse((880,800,1020,940),fill='#388C60')
    d.rectangle((465,840,505,900),fill='#263341');d.rectangle((915,840,955,900),fill='#263341')
    d.rectangle((510,1060,940,1090),fill='#263341')
    for i,color in enumerate(['#FFD54A','#E64245','#7E63A8','#55BFA2']):d.rectangle((355+i*190,1320,490+i*190,1470),fill=color)
    im.save(source)
    timings=[];artifacts={}
    def run(project,command,label=None,**kwargs):
        args=[sys.executable,str(ROOT/'scripts/pindou.py'),command,'--project',str(project)]
        for k,v in kwargs.items():
            if v is True:args.append('--'+k.replace('_','-'))
            elif isinstance(v,list):
                for x in v:args.extend(['--'+k.replace('_','-'),str(x)])
            elif v is not None:args.extend(['--'+k.replace('_','-'),str(v)])
        start=time.monotonic();p=subprocess.run(args,capture_output=True,text=True);seconds=time.monotonic()-start
        try:r=json.loads(p.stdout)
        except ValueError:raise RuntimeError(p.stderr or p.stdout)
        if p.returncode:raise RuntimeError(r)
        if label:timings.append({'run':project.name,'stage':label,'seconds':round(seconds,4),'local_success_under_60':seconds<=60,'generative_calls':0,'retries':0,'scope':'local CLI launch through JSON file delivery, includes validation','segments_seconds':r.get('timings',{})})
        return r
    for i in range(1,a.runs+1):
        p=out/f'run-{i}';r=run(p,'init','stage1-original-candidate',input=source,source='synthetic geometry created by benchmark.py',simulated=True)
        o=run(p,'begin',kind='edit',base=r['revision_id'],request='remove connected white outer background; retain internal pale face')
        r=run(p,'edit','stage1-ordinary-edit',operation=o['operation_id'],remove_edge='#FFFFFF');edit_id=r['revision_id']
        run(p,'confirm',revision=edit_id,stage='edit',message='SIMULATED benchmark confirmation')
        r=run(p,'pixel','stage2-78x78-18colors',base=edit_id,width=78,height=78,max_colors=18)
        r=run(p,'pixel','revision-12colors',base=r['revision_id'],max_colors=12);rev=r['revision_id']
        run(p,'confirm',revision=rev,stage='pixel',message='SIMULATED benchmark confirmation')
        png=run(p,'png','stage3-png',revision=rev)
        run(p,'present',revision=rev,artifact='pattern',conversation='SIMULATED-benchmark',message_ref='SIMULATED PNG delivery; no actual user')
        csv=run(p,'route','export-csv',conversation='SIMULATED-benchmark',message='这张可以，下载用量清单',message_ref='SIMULATED csv request')
        pdf=run(p,'route','export-pdf',conversation='SIMULATED-benchmark',message='导出pdf',message_ref='SIMULATED pdf request')
        cached=run(p,'route','export-pdf-cached',conversation='SIMULATED-benchmark',message='导出pdf',message_ref='SIMULATED repeated pdf request')
        assert cached['reused'] and cached['file']==pdf['file']
        run(p,'validate')
        if i==1:artifacts={'project':str(p),'revision_id':rev,'png':png['file'],'png_preview':png['preview'],'csv':csv['file'],'pdf':pdf['file']}
    report={'scope':'LOCAL SYNTHETIC ONLY; not Doubao E2E; no AI calls','input':'generated geometry, 1440x1920','baseline':'78x78, maximum 18 colors; then 12-color revision','runs':a.runs,'samples':timings,'host_e2e_seconds':None,'host_generation_calls':None,'native_tool_interrupt':'unknown','artifacts_relative_to_benchmark_directory':{k:(str(Path(v).relative_to(out)) if k!='revision_id' else v) for k,v in artifacts.items()}}
    Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report':a.report,'artifacts':artifacts},indent=2))
if __name__=='__main__':main()
