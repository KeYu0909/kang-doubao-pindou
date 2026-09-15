from .render import PNG_TEMPLATE_VERSION, CSV_TEMPLATE_VERSION
import os
import shutil
import time
from pathlib import Path
from .common import *
from .imaging import *
from .render import *


def deadline():
    require(time.monotonic()<float(os.environ.get('PINDOU_DEADLINE','inf')), 'TIMEOUT: shared local stage budget exhausted')

def snapshot(project):
    with locked(project): return load(project)

def validate_revision(project,r,deep=False):
    for f in r['files'].values(): checked_file(project,f)
    if r['kind']=='pixel':
        g=read_json(checked_file(project,r['files']['grid']))
        require(grid_hash(g)==r['grid_sha256'],'GRID_HASH: mismatch'); grid_check(g)
        if deep:
            png_check(g,checked_file(project,r['files']['preview']),r['revision_id'])
            if 'pattern' in r['files']: png_check(g,checked_file(project,r['files']['pattern']),r['revision_id'],True)
        return g
    return None

def staging(project):
    p=Path(project)/'.staging'/os.environ.get('PINDOU_JOB',uid('job'))
    p.mkdir(parents=True,exist_ok=False)
    return p

def commit_revision(project,s,r,folder,operation=None):
    deadline()
    with locked(project):
        live=load(project)
        require(live['epoch']==s['epoch'] and live['current_revision']==s['current_revision'],'STALE_RESULT: current selection changed; result not activated')
        if operation:
            require(live['operations'].get(operation,{}).get('status')=='pending','OPERATION_CLOSED: cancelled or already used')
            live['operations'][operation]['status']='completed'
        dest=Path(project)/'revisions'/r['revision_id']
        require(not dest.exists(),'REVISION_COLLISION')
        os.replace(folder,dest)
        for key,f in list(r['files'].items()):
            path=dest/f.pop('_name');r['files'][key]=artifact(Path(project),r['revision_id'],key,path,r.get('grid_sha256'),f.get('params'))
        live['revisions'][r['revision_id']]=r;live['current_revision']=r['revision_id'];live['epoch']+=1
        live.pop('pending_modification',None)
        update_stage(live);save(project,live)
    return view(project,live)

def new_revision(kind,s,parent=None):
    return {'revision_id':uid(),'kind':kind,'parent_revision':parent or s.get('current_revision'),'created_at':time.time(),'confirmations':{},'files':{}}

def view(project,s):
    r=current(s)
    return {'project_id':s['project_id'],'project':str(Path(project).resolve()),'revision_id':r['revision_id'],'stage':s['stage'],
            'epoch':s['epoch'],'grid_sha256':r.get('grid_sha256'),'parameters':r.get('parameters'),
            'files':{k:str(checked_file(project,v)) for k,v in r['files'].items() if k not in ('grid','source')},
            'revisions':[{'revision_id':x['revision_id'],'kind':x['kind'],'parent':x['parent_revision']} for x in s['revisions'].values()]}

def init_project(a):
    p=Path(a.project).resolve()
    require(not p.exists(),'PROJECT_EXISTS: choose a new independent work directory')
    im=open_image(a.input)
    p.mkdir(parents=True);(p/'revisions').mkdir()
    s={'schema_version':1,'skill_version':'0.3.0','project_id':uid('p'),'created_at':time.time(),'epoch':0,'current_revision':None,'revisions':{},'operations':{},'preview_reads':{}}
    r=new_revision('edit',s);d=p/'revisions'/r['revision_id'];d.mkdir()
    # Preserve exact provided bytes and record provenance separately from normalized candidate.
    source=d/('original'+Path(a.input).suffix.lower());shutil.copyfile(a.input,source)
    im.save(d/'candidate.png');lightweight(d/'candidate.png',d/'candidate-small.png')
    r.update({'input':{'source':a.source,'original_name':Path(a.input).name,'sha256':sha_file(source),'simulation':a.simulated},'edit_requirements':a.request,'preserve':a.preserve,'parameters':{'background':'keep','crop':None},'generative_calls':0})
    for k,name in [('source',source.name),('candidate','candidate.png'),('candidate_small','candidate-small.png')]:r['files'][k]=artifact(p,r['revision_id'],k,d/name)
    s['revisions'][r['revision_id']]=r;s['current_revision']=r['revision_id'];update_stage(s);save(p,s)
    return view(p,s)

def begin(a):
    with locked(a.project):
        s=load(a.project);r=current(s);require(getattr(a,'current',False) or a.base==r['revision_id'],'STALE_BASE: use current revision')
        validate_revision(a.project,r)
        if a.kind=='pixel':
            edit=r if r['kind']=='edit' else current(s,r['edit_revision'])
            require(confirmed(edit,'edit'),'EDIT_NOT_CONFIRMED')
        require(not any(o.get('status')=='pending' and o.get('epoch')==s['epoch'] for o in s['operations'].values()),'MODIFICATION_PENDING')
        token=uid('op');source=r['files']['candidate' if r['kind']=='edit' else 'source']
        s['operations'][token]={'operation_id':token,'kind':a.kind,'base':r['revision_id'],'epoch':s['epoch'],'status':'pending','source_sha256':source['sha256'],
            'source_path':source['path'],'request':a.request,'preserve':a.preserve or r.get('preserve',[]),'started_at':time.time(),'generative_calls':0,'retries':0,'call_mode':None}
        save(a.project,s)
        return {**s['operations'][token],'source_file':str(checked_file(a.project,source))}

def select_operation(s,a):
    if not getattr(a,'current',False):return a.operation
    pending=[key for key,o in s['operations'].items() if o.get('status')=='pending' and o.get('epoch')==s['epoch'] and o.get('base')==s['current_revision']]
    require(len(pending)==1,'OPERATION_REQUIRED: no single active operation')
    return pending[0]

def claim_call(a):
    with locked(a.project):
        s=load(a.project);a.operation=select_operation(s,a);o=s['operations'].get(a.operation,{})
        require(o.get('status')=='pending' and o['epoch']==s['epoch'],'OPERATION_STALE_OR_CLOSED')
        require(o['generative_calls']==0,'CALL_LIMIT: at most one generative call per operation')
        o['generative_calls']=1;o['call_mode']=a.mode;o['claimed_at']=time.time();save(a.project,s)
        return {'operation_id':a.operation,'call_count':1,'mode':a.mode,'note':'Host invocation must use actual available tools; this command does not invoke one.'}

def operation(s,token,kind,based_on=None):
    o=s['operations'].get(token,{})
    require(o.get('status')=='pending' and o.get('epoch')==s['epoch'] and o.get('base')==s['current_revision'],'OPERATION_STALE_OR_CLOSED')
    require(o['kind']==kind,'OPERATION_KIND: mismatch')
    if based_on is not None: require(based_on==o['source_sha256'],'SOURCE_MISMATCH: result must edit actual current candidate')
    return o

def edit(a):
    s=snapshot(a.project);a.operation=select_operation(s,a);o=operation(s,a.operation,'edit',a.based_on_sha);base=current(s);validate_revision(a.project,base)
    if a.input:
        require(a.based_on_sha,'SOURCE_REQUIRED: pass --based-on-sha from begin output')
        im=open_image(a.input)
        require(a.origin in ('host','manual','simulated'),'IMPORT_ORIGIN: host/manual/simulated required')
        if a.origin in ('host','simulated'):require(o['generative_calls']==1 and o['call_mode']==a.origin,'CALL_RECORD_REQUIRED')
        original=a.input
    else:
        original=checked_file(a.project,base['files']['candidate' if base['kind']=='edit' else 'source']);im=open_image(original)
        require(a.crop or a.remove_edge,'NO_EDIT: confirm existing candidate or supply an explicit ordinary edit')
    original_size=list(im.size);im=crop_image(im,a.crop);removed=0
    if a.remove_edge: im,removed=remove_edge(im,a.remove_edge,a.tolerance)
    r=new_revision('edit',s);d=staging(a.project);im.save(d/'candidate.png');lightweight(d/'candidate.png',d/'candidate-small.png')
    imported_name='imported-source'+Path(original).suffix.lower()
    shutil.copyfile(original,d/imported_name)
    r.update({'input':{'source':a.origin if a.input else 'local-current-candidate','sha256':sha_file(original),'simulation':a.origin=='simulated' or base.get('input',{}).get('simulation',False)},
        'edit_requirements':o['request'],'preserve':o['preserve'],
        'generative_calls':None if a.origin=='manual' and o['generative_calls']==0 else o['generative_calls'],
        'parameters':{'original_size':original_size,'crop':a.crop,'remove_edge':a.remove_edge,'tolerance':a.tolerance,'removed_pixels':removed}})
    r['files']={'source':{'_name':imported_name},'candidate':{'_name':'candidate.png'},'candidate_small':{'_name':'candidate-small.png'}}
    return commit_revision(a.project,s,r,d,a.operation)

def pixel(a):
    started=time.monotonic();timings={}
    s=snapshot(a.project);base=current(s);require(getattr(a,'current',False) or a.base==base['revision_id'],'STALE_BASE')
    require(not any(o.get('status')=='pending' and o.get('epoch')==s['epoch'] for o in s['operations'].values()) or a.operation,'MODIFICATION_PENDING')
    validate_revision(a.project,base)
    ed=base if base['kind']=='edit' else current(s,base['edit_revision'])
    require(confirmed(ed,'edit'),'EDIT_NOT_CONFIRMED: confirm the specific edited candidate first')
    validate_revision(a.project,ed)
    previous=base.get('parameters',{})
    width=a.width if a.width is not None else previous.get('width',78)
    height=a.height if a.height is not None else previous.get('height',78)
    cap=a.max_colors if a.max_colors is not None else previous.get('max_colors',18)
    reserve=a.reserve if a.reserve is not None else previous.get('reserve',[])
    sampling=a.sampling or previous.get('sampling','box')
    pal=palette_load(a.palette) if a.palette or base['kind']=='edit' else read_json(checked_file(a.project,base['files']['grid']))['palette']
    source=checked_file(a.project,base['files']['candidate' if base['kind']=='edit' else 'source'])
    op=None
    if a.input:
        require(a.operation and a.based_on_sha,'PIXEL_IMPORT: operation and based-on-sha required')
        o=operation(s,a.operation,'pixel',a.based_on_sha)
        require(o['generative_calls']==1,'CALL_RECORD_REQUIRED');source=Path(a.input);op=a.operation
        require(sha_file(source) is not None, 'PIXEL_INPUT_MISSING')
    else: require(not a.operation,'PIXEL_IMPORT: --operation requires --input')
    timings['state_check']=time.monotonic()-started;t=time.monotonic()
    from .cleanup import reduce_colors, protection, feature_colors
    same_grid=base['kind']=='pixel' and not a.input and not a.palette and width==previous.get('width') and height==previous.get('height') and sampling==previous.get('sampling','box') and reserve==previous.get('reserve',[])
    spec=read_json(a.protect) if getattr(a,'protect',None) else {}
    if same_grid:
        # Max-colors-only edits keep the current grid (including earlier cleanup), not the original photograph.
        old=read_json(checked_file(a.project,base['files']['grid']))
        inherited=feature_colors(old,ed.get('preserve',[]))
        spec={**spec,'codes':list(dict.fromkeys(spec.get('codes',[])+reserve+inherited['codes']))}
        g=reduce_colors(old,cap,spec)
    else:
        im=open_image(source);g=grid_build(im,width,height,pal,cap,reserve,sampling)
    if reserve:spec={**spec,'codes':list(dict.fromkeys(spec.get('codes',[])+reserve))}
    # Literal palette labels in recorded preserve requirements are safe to carry; semantic names need explicit mapping.
    import re
    known={c['code'] for c in g['palette']['colors']}
    tags={word for text in ed.get('preserve',[]) for word in re.findall(r'[A-Za-z0-9_-]+',text)} & known
    feature=feature_colors(g,ed.get('preserve',[]))
    spec['codes']=list(dict.fromkeys(spec.get('codes',[])+sorted(tags)+feature['codes']))
    spec['labels']=list(dict.fromkeys(spec.get('labels',[])+feature['labels']))
    _,g['protection']=protection(g,spec)
    timings['grid_processing']=time.monotonic()-t;t=time.monotonic()
    r=new_revision('pixel',s);r.update({'edit_revision':ed['revision_id'],'grid_sha256':grid_hash(g),'preserve':ed['preserve'],
        'parameters':{'width':width,'height':height,'max_colors':cap,'palette':pal['name'],'reserve':reserve,'sampling':sampling,'processing':g['processing']},
        'generative_calls':s['operations'][op]['generative_calls'] if op else 0,'input':{'source':'host-result' if op else 'confirmed-candidate','simulation':ed.get('input',{}).get('simulation',False) or bool(op and s['operations'][op]['call_mode']=='simulated')}})
    d=staging(a.project)
    if same_grid:shutil.copyfile(source,d/'source.png')
    else:im.save(d/'source.png')
    atomic_json(d/'grid.json',g);preview(g,d/'pixel-preview.png',r['revision_id']);lightweight(d/'pixel-preview.png',d/'pixel-small.png')
    png_check(g,d/'pixel-preview.png',r['revision_id'])
    r['files']={k:{'_name':name} for k,name in [('source','source.png'),('grid','grid.json'),('preview','pixel-preview.png'),('preview_small','pixel-small.png')]}
    from .cleanup import analyze
    timings['preview_render']=time.monotonic()-t;t=time.monotonic()
    analysis=analyze(g);atomic_json(d/'analysis.json',analysis);r['files']['analysis']={'_name':'analysis.json'}
    out=commit_revision(a.project,s,r,d,op)
    out['analysis']={k:v for k,v in analysis.items() if k!='small_regions'}
    timings['analysis_and_commit']=time.monotonic()-t;out['timings']=timings
    audit(a.project,{'event':'pixel_pipeline','revision_id':r['revision_id'],'scope':'local-command-only','timings':timings})
    return out


def denoise(a):
    from .cleanup import clean, analyze
    started=time.monotonic();timings={}
    s=snapshot(a.project);base=current(s)
    require(getattr(a,'current',False) or a.base==base['revision_id'],'STALE_BASE')
    require(base['kind']=='pixel','PIXEL_REQUIRED')
    require(not s.get('pending_modification') and not any(o.get('status')=='pending' and o.get('epoch')==s['epoch'] for o in s['operations'].values()),'MODIFICATION_PENDING')
    g=validate_revision(a.project,base)
    extra=read_json(a.protect) if getattr(a,'protect',None) else None
    timings['state_check']=time.monotonic()-started;t=time.monotonic()
    out,summary=clean(g,a.mode,getattr(a,'max_colors',None),extra)
    timings['cleanup']=time.monotonic()-t;t=time.monotonic()
    r=new_revision('pixel',s)
    r.update({'edit_revision':base['edit_revision'],'grid_sha256':grid_hash(out),'preserve':base.get('preserve',[]),
              'parameters':{**base['parameters'],'max_colors':out['max_colors'],'processing':out['processing']},
              'generative_calls':0,'input':base.get('input',{})})
    d=staging(a.project);shutil.copyfile(checked_file(a.project,base['files']['source']),d/'source.png')
    atomic_json(d/'grid.json',out);preview(out,d/'pixel-preview.png',r['revision_id']);lightweight(d/'pixel-preview.png',d/'pixel-small.png')
    png_check(out,d/'pixel-preview.png',r['revision_id'])
    analysis=analyze(out);atomic_json(d/'analysis.json',analysis)
    r['files']={k:{'_name':n} for k,n in [('source','source.png'),('grid','grid.json'),('preview','pixel-preview.png'),('preview_small','pixel-small.png'),('analysis','analysis.json')]}
    result=commit_revision(a.project,s,r,d)
    timings['render_analysis_commit']=time.monotonic()-t
    public={k:v for k,v in summary.items() if k!='changes'}
    audit(a.project,{'event':'cleanup','mode':a.mode,'base_revision':base['revision_id'],'revision_id':r['revision_id'],**public})
    return {**result,'timings':timings,'cleanup':public,'analysis':{k:v for k,v in analysis.items() if k!='small_regions'}}


def confirm(a):
    require(a.message.strip(),'CONFIRMATION_MESSAGE: record the explicit user message')
    with locked(a.project):
        s=load(a.project);r=current(s,a.revision) if getattr(a,'allow_historical',False) else current(s)
        require(getattr(a,'current',False) or a.revision==r['revision_id'],'CONFIRMATION_STALE: select exact current revision')
        validate_revision(a.project,r)
        require(not s.get('pending_modification') and not any(o.get('status')=='pending' and o.get('epoch')==s['epoch'] for o in s['operations'].values()),'MODIFICATION_PENDING')
        require((a.stage=='edit' and r['kind']=='edit') or (a.stage in ('pixel','png') and r['kind']=='pixel'),'CONFIRMATION_STAGE: mismatch')
        if a.stage=='png':require('pattern' in r['files'] and confirmed(r,'pixel'),'PNG_MISSING_OR_PIXEL_UNCONFIRMED')
        source=getattr(a,'source','explicit')
        require(source in ('explicit','contextual_export'),'CONFIRMATION_SOURCE')
        if source=='contextual_export':
            from .interaction import context,visible
            require(a.stage=='png' and visible(a.project,context(s,a.conversation),r,'png'),'PNG_NOT_PRESENTED')
            require(not s.get('pending_modification'),'MODIFICATION_PENDING')
        r['confirmations'][a.stage]={'project_id':s['project_id'],'source':source,'message_ref':getattr(a,'message_ref',None),'conversation':getattr(a,'conversation',None),'stage':a.stage,'revision_id':r['revision_id'],'grid_sha256':r.get('grid_sha256'),
             'artifact_sha256':r['files'].get('pattern',{}).get('sha256') if a.stage=='png' else None,'message':a.message[:180],'confirmed_at':time.time()}
        s['epoch']+=1;update_stage(s);save(a.project,s);return view(a.project,s)

def attach(a,kind):
    timing={};t=time.monotonic();s=snapshot(a.project)
    r=current(s,a.revision) if getattr(a,'allow_historical',False) else current(s)
    require(getattr(a,'current',False) or a.revision==r['revision_id'],'STALE_REVISION');require(r['kind']=='pixel','PIXEL_REQUIRED')
    g=validate_revision(a.project,r)
    if kind=='pattern':
        require(confirmed(r,'pixel'),'PIXEL_NOT_CONFIRMED')
        require(not s.get('pending_modification') and not any(o.get('status')=='pending' and o.get('epoch')==s['epoch'] for o in s['operations'].values()),'MODIFICATION_PENDING')
    else:
        require(confirmed(r,'png'),'PNG_NOT_CONFIRMED: confirm the displayed PNG version or use contextual route')
        require(r['confirmations']['png'].get('project_id',s['project_id'])==s['project_id'],'CONFIRMATION_PROJECT_MISMATCH')
        require(not s.get('pending_modification'),'MODIFICATION_PENDING')
        require(not any(o.get('status')=='pending' and o.get('epoch')==s['epoch'] for o in s.get('operations',{}).values()),'MODIFICATION_PENDING')
    timing['state_check']=time.monotonic()-t
    layout=getattr(a,'layout','standard');cell=getattr(a,'cell_pt',None)
    params={'template_version':PNG_TEMPLATE_VERSION} if kind=='pattern' else ({'spare_percent':a.spare_percent,'template_version':CSV_TEMPLATE_VERSION} if kind=='csv' else {'cell_pt':cell,'layout':layout,'template_version':TEMPLATE_VERSION})
    if kind=='csv':require(0<=a.spare_percent<=100,'SPARE_PERCENT: 0..100')
    key=kind if kind=='pattern' else kind+'_'+digest(canonical(params))[:10]
    refresh_labels=kind=='pattern' and key in r['files'] and r['files'][key].get('params',{})!=params
    if key in r['files'] and not refresh_labels:
        f=r['files'][key];path=checked_file(a.project,f)
        require(f['revision_id']==r['revision_id'] and f['grid_sha256']==r['grid_sha256'],'EXPORT_VERSION_MISMATCH')
        return {'reused':True,'revision_id':r['revision_id'],'kind':kind,'file':str(path),'grid_sha256':r['grid_sha256'],'timings':timing,'layout_plan':f.get('layout_plan')}
    t=time.monotonic();pagination=pdf_plan(g,cell,layout) if kind=='pdf' else None;timing['pagination']=time.monotonic()-t
    d=staging(a.project);name={'pattern':'pattern.png','csv':'bom.csv','pdf':'pattern.pdf'}[kind];path=d/name
    t=time.monotonic()
    if kind=='pattern':png_render(g,path,r['revision_id']);lightweight(path,d/'pattern-small.png')
    elif kind=='csv':csv_render(g,path,r['revision_id'],a.spare_percent)
    else:pdf_render(g,path,r['revision_id'],cell,layout,pagination)
    timing['drawing']=time.monotonic()-t;t=time.monotonic()
    if kind=='pattern':png_check(g,path,r['revision_id'],True)
    elif kind=='csv':csv_check(g,path,r['revision_id'])
    else:pdf_check(g,path,r['revision_id'],cell,True,layout,pagination)
    timing['validation']=time.monotonic()-t;deadline();t=time.monotonic()
    with locked(a.project):
        live=load(a.project);require(live['epoch']==s['epoch'] and live['current_revision']==s['current_revision'],'STALE_RESULT: export not activated')
        lr=current(live,r['revision_id']);destination_key=key+'_'+digest(canonical(params))[:10] if refresh_labels else key
        dest=Path(a.project)/'revisions'/r['revision_id']/destination_key
        require(not dest.exists(),'ORPHAN_OUTPUT: inspect previous interrupted commit')
        if refresh_labels:
            legacy_key='pattern_legacy_'+lr['files']['pattern']['sha256'][:10]
            lr['files'][legacy_key]=lr['files']['pattern']
            if 'pattern_small' in lr['files']:lr['files'][legacy_key+'_small']=lr['files']['pattern_small']
            if 'png' in lr['confirmations']:
                lr.setdefault('confirmation_history',[]).append(lr['confirmations'].pop('png'))
        os.replace(d,dest);lr['files'][key]=artifact(Path(a.project),r['revision_id'],kind,dest/name,r['grid_sha256'],params)
        if pagination:lr['files'][key]['layout_plan']=pagination
        if kind=='pattern':lr['files']['pattern_small']=artifact(Path(a.project),r['revision_id'],'pattern_small',dest/'pattern-small.png',r['grid_sha256'])
        live['epoch']+=1;update_stage(live);save(a.project,live)
    timing['file_delivery']=time.monotonic()-t
    audit(a.project,{'event':'artifact_pipeline','revision_id':r['revision_id'],'kind':kind,'scope':'local-command-only','timings':timing})
    return {'reused':False,'revision_id':r['revision_id'],'kind':kind,'file':str((dest/name).resolve()),'grid_sha256':r['grid_sha256'],'stage':live['stage'],'timings':timing,'layout_plan':pagination,
            **({'preview':str((dest/'pattern-small.png').resolve())} if kind=='pattern' else {})}

def rollback(a):
    with locked(a.project):
        s=load(a.project);r=current(s,a.revision);validate_revision(a.project,r)
        s['current_revision']=a.revision;s['epoch']+=1;s.pop('pending_modification',None);update_stage(s);save(a.project,s);return view(a.project,s)

def cancel(a):
    with locked(a.project):
        s=load(a.project);a.operation=select_operation(s,a);o=s['operations'].get(a.operation,{})
        require(o.get('status')=='pending','OPERATION_CLOSED');o['status']='cancelled';s['epoch']+=1;save(a.project,s)
    return {'operation_id':a.operation,'status':'cancelled','host_tool_interrupt':'unknown; this only rejects its later import'}

def preview_result(a):
    with locked(a.project):
        s=load(a.project);r=current(s);require(getattr(a,'current',False) or a.revision==r['revision_id'],'STALE_REVISION')
        key=r['revision_id']+':'+s['stage'];rec=s['preview_reads'].setdefault(key,{'attempts':0,'status':'unverified'})
        require(rec['attempts']<2 and rec['status']!='verified','PREVIEW_STOP: no more reads for this stage; visual check incomplete if failed')
        rec['attempts']+=1;rec['status']='verified' if a.outcome=='success' else 'incomplete';save(a.project,s)
        small='candidate_small' if r['kind']=='edit' else ('pattern_small' if 'pattern' in r['files'] else 'preview_small')
        return {'visual_check':rec['status'],'attempts':rec['attempts'],'fallback':str(checked_file(a.project,r['files'][small])) if rec['attempts']==1 and a.outcome=='fail' else None,'stop':rec['attempts']>=2 or a.outcome=='success'}

def validate(a):
    s=snapshot(a.project);r=current(s);g=validate_revision(a.project,r,deep=True)
    if g:
        for f in r['files'].values():
            if f['kind']=='csv':csv_check(g,checked_file(a.project,f),r['revision_id'])
            if f['kind']=='pdf':
                if 'template_version' in f['params']:pdf_check(g,checked_file(a.project,f),r['revision_id'],f['params'].get('cell_pt'),True,f['params'].get('layout','standard'),f.get('layout_plan'))
                else:legacy_pdf_check(g,checked_file(a.project,f),r['revision_id'],f['params']['cell_pt'],True)
    return {'valid':True,**view(a.project,s)}

def delivery(a):
    require(a.delivered_at>=a.submitted_at>0 and a.delivered_at<=time.time()+5,'TIMESTAMPS: invalid submission/delivery order')
    s=snapshot(a.project);r=current(s,a.revision);validate_revision(a.project,r)
    require(a.artifact in r['files'],'DELIVERY_ARTIFACT: not generated')
    path=checked_file(a.project,r['files'][a.artifact]);seconds=a.delivered_at-a.submitted_at
    event={'event':'delivery','scope':a.scope,'revision_id':a.revision,'artifact':a.artifact,'artifact_sha256':sha_file(path),'seconds':seconds,
        'submitted_at':a.submitted_at,'delivered_at':a.delivered_at,'quality':a.quality,'evidence':a.evidence,
        'result':'pass' if a.quality=='qualified' and seconds<=60 else ('slow' if a.quality=='qualified' else 'not-qualified')}
    require(bool(a.evidence.strip()),'DELIVERY_EVIDENCE: actual host tool record or manual observation required');audit(a.project,event);return event


def record_stage(a):
    require(a.ended_at>=a.started_at>0 and a.ended_at<=time.time()+5,'TIMESTAMPS: invalid stage times')
    require(a.evidence.strip(),'TIMING_EVIDENCE_REQUIRED')
    s=snapshot(a.project);r=current(s)
    event={'event':'host_stage','phase':a.phase,'scope':a.scope,'revision_id':r['revision_id'],
           'started_at':a.started_at,'ended_at':a.ended_at,'seconds':a.ended_at-a.started_at,'evidence':a.evidence,
           'exceeds_60_seconds':a.ended_at-a.started_at>60}
    audit(a.project,event);return event
