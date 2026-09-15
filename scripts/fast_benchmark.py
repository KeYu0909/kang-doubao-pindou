#!/usr/bin/env python3
"""Real local CLI timings on a synthetic cat; host image editing is not measured."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
TARGETS={'pixel':15,'denoise':15,'recolor':15,'png':10,'csv':5,'pdf':10,'pdf_large':10}


def cat(path, hat=False):
    im=Image.new('RGBA',(312,312),(0,0,0,0));d=ImageDraw.Draw(im)
    d.ellipse((46,54,264,266),fill='#B4A497',outline='#30251F',width=5)
    d.polygon([(58,98),(52,25),(113,71)],fill='#B4A497',outline='#30251F')
    d.polygon([(206,73),(266,25),(256,111)],fill='#B4A497',outline='#30251F')
    d.ellipse((91,115,116,144),fill='#006630');d.ellipse((192,115,217,144),fill='#006630')
    d.polygon([(143,153),(170,153),(156,164)],fill='#D18587')
    d.line((156,164,156,188,141,190),fill='#30251F',width=4)
    for x,y in [(88,180),(112,212),(184,208),(208,176),(156,236),(72,144)]:d.rectangle((x,y,x+3,y+3),fill='#BDA9AB')
    if hat:
        d.polygon([(122,63),(167,4),(207,63)],fill='#BE342C');d.rectangle((119,60,209,70),fill='#EFE8DC')
    im.save(path)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--runs',type=int,default=3);ap.add_argument('--report',default=str(ROOT/'reports/fast-path-benchmark.json'));a=ap.parse_args()
    dest=Path(a.out).resolve();dest.mkdir(parents=True,exist_ok=False);source=dest/'synthetic-cat.png';edited=dest/'synthetic-cat-hat.png';cat(source);cat(edited,True)
    records=[];timeline=[]
    for run in range(a.runs):
        project=dest/f'run-{run+1}';session=f'synthetic-{run+1}'
        def call(label,command,*flags):
            t=time.monotonic();p=subprocess.run([sys.executable,str(ROOT/'scripts/pindou.py'),command,'--project',str(project),*flags],capture_output=True,text=True,timeout=65)
            wall=time.monotonic()-t
            try:out=json.loads(p.stdout)
            except ValueError:raise RuntimeError(p.stdout+p.stderr)
            if (p.returncode or not out['ok']) and not (label=='recolor' and out.get('code')=='PROTECTION_COLOR_CONFLICT'):raise RuntimeError(label+': '+str(out))
            records.append({'run':run+1,'stage':label,'seconds':round(wall,6),'script_seconds':out.get('timing',{}).get('seconds'),
                            'timings':out.get('timings',{}),'revision_id':out.get('revision_id'),'grid_sha256':out.get('grid_sha256'),
                            'ok':out['ok'],'code':out.get('code'),'target_seconds':TARGETS.get(label),'exceeds_60_seconds':wall>60,'reused':out.get('reused')})
            return out
        def show(artifact):call('simulated_receipt','present','--current','--artifact',artifact,'--conversation',session,'--message-ref','SIMULATED user-visible receipt; NOT actual delivery')
        def route(label,text):return call(label,'route','--current','--conversation',session,'--message',text,'--message-ref','SIMULATED USER: '+text)
        call('init','init','--input',str(source),'--source','synthetic cat; NOT user photograph','--simulated')
        op=call('begin','begin','--current','--kind','edit','--request','SIMULATED remove background, add hat; preserve eyes and pose','--preserve','green eyes')
        call('claim','claim-call','--operation',op['operation_id'],'--mode','simulated')
        call('import_edit','edit','--operation',op['operation_id'],'--input',str(edited),'--origin','simulated','--based-on-sha',op['source_sha256'])
        show('candidate');route('edit_confirm','确认原图')
        call('pixel','pixel','--current','--width','78','--height','78','--max-colors','18')
        show('preview');route('denoise','轻度去杂色');show('preview');route('rollback','还是上一版');show('preview')
        recolored=route('recolor','颜色减到12色')
        if not recolored['ok']:
            # Explicitly simulated follow-up, not a silent product fallback. Record the blocked 12-colour request.
            recolored=route('recolor_16','颜色减到16色')
        show('preview');route('png','生成PNG');show('pattern')
        pdf=route('pdf','导出PDF');large=route('pdf_large','PDF字大一点');csv=route('csv','下载清单')
        assert pdf['grid_sha256']==large['grid_sha256']==csv['grid_sha256']
        route('pdf_cached','导出PDF')
        timeline.extend(json.loads(line) for line in (project/'events.jsonl').read_text().splitlines())
    summary={}
    for stage in TARGETS:
        values=[r['seconds'] for r in records if r['ok'] and (r['stage']==stage or (stage=='recolor' and r['stage']=='recolor_16'))]
        summary[stage]={'min':min(values),'max':max(values),'mean':sum(values)/len(values),'target_seconds':TARGETS[stage],'all_within_target':all(v<=TARGETS[stage] for v in values)}
    report={'scope':'real local CLI execution, synthetic fixture and explicitly simulated user messages; NOT Doubao',
            'runs':a.runs,'grid':'78x78','initial_max_colors':18,'requested_recolor_max_colors':12,'fallback_recolor_max_colors':16,'blocked_requests':[r for r in records if not r['ok']],'summary':summary,'records':records,
            'host_times':{'ai_thinking':None,'image_tool':None,'preview_delivery':None,'post_script_wait':None,'doubao_e2e':None},
            'over_60_seconds':[r for r in records if r['exceeds_60_seconds']],
            'limitations':['No actual host image call or actual user presentation; synthetic edit imported once.','If 12 colours conflicts with protection, the synthetic user explicitly selects 16; blocked requests remain in this report.','Local commands include interpreter startup and supervisor; durations are not host end-to-end.']}
    Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'reports/fast-path-events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in timeline))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
