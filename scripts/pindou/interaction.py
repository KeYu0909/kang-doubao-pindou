"""Context-bound receipts, menus and deterministic routing. No separate model call.
Receipts are host attestations of real presentation, not security authentication.
"""
import json
import re
import time
from types import SimpleNamespace as NS
from .common import *

ACTIONS={'confirm','pixel','png','export_pdf','export_csv','adjust','rollback','denoise','recolor','keep'}

def context(s,conversation):
    require(bool(conversation),'CONVERSATION_REQUIRED')
    return s.setdefault('interaction',{}).setdefault(conversation,{'presented':{},'focus':None,'menu':None})

def stage_of(r):
    if r['kind']=='edit':return 'edit'
    return 'png' if 'pattern' in r['files'] else 'pixel'

def receipt_for(ctx,r,stage):
    return ctx['presented'].get(r['revision_id']+':'+stage)

def visible(project,ctx,r,stage):
    key={'edit':'candidate','pixel':'preview','png':'pattern'}[stage]
    rec=receipt_for(ctx,r,stage)
    if key not in r['files'] or not rec:return False
    f=r['files'][key];checked_file(project,f)
    return rec['artifact_sha256']==f['sha256'] and rec['revision_id']==r['revision_id'] and rec.get('grid_sha256')==r.get('grid_sha256')

def present(a):
    with locked(a.project):
        s=load(a.project);r=current(s,None if getattr(a,'current',False) else a.revision);a.revision=r['revision_id'];ctx=context(s,a.conversation)
        stage={'candidate':'edit','preview':'pixel','pattern':'png'}[a.artifact]
        require(a.artifact in r['files'],'ARTIFACT_NOT_GENERATED')
        require(a.message_ref.strip(),'PRESENTATION_REFERENCE_REQUIRED: record actual host delivery')
        if stage=='png':require(confirmed(r,'pixel'),'PIXEL_NOT_CONFIRMED')
        f=r['files'][a.artifact];checked_file(a.project,f)
        rec={'project_id':s['project_id'],'revision_id':a.revision,'artifact_sha256':f['sha256'],'grid_sha256':r.get('grid_sha256'),'message_ref':a.message_ref,'stage':stage,'presented_at':time.time()}
        ctx['presented'][a.revision+':'+stage]=rec;ctx['focus']=None if getattr(a,'ambiguous',False) else a.revision
        ctx['menu']=None;ctx.pop('pending_cleanup',None);save(a.project,s)
    return {'presented':rec,'focus':ctx['focus']}

def offer(a):
    options=read_json(a.options)
    require(isinstance(options,list) and 1<=len(options)<=4,'OPTIONS: one to four choices')
    require(sum(bool(x.get('recommended')) for x in options)<=1,'OPTIONS: at most one recommendation')
    for x in options:
        require(x.get('action') in ACTIONS and isinstance(x.get('label'),str),'OPTIONS: invalid action or label')
        require(isinstance(x.get('args',{}),dict),'OPTIONS_ARGS')
    with locked(a.project):
        s=load(a.project);ctx=context(s,a.conversation);r=current(s,None if getattr(a,'current',False) else a.revision);a.revision=r['revision_id']
        require(ctx['focus']==a.revision and visible(a.project,ctx,r,stage_of(r)),'OPTIONS: present the specific current result first')
        ctx['menu']={'menu_id':uid('menu'),'revision_id':a.revision,'stage':stage_of(r),'epoch':s['epoch'],'options':options,'consumed':False}
        save(a.project,s);return ctx['menu']

def classify(message):
    t=re.sub(r'\s+','',message.lower()).strip('。！!，,')
    if re.search(r'不要|先不|别导|不导出|以后|稍后|下次|晚点|暂不',t):return {'action':'no_action'}
    if re.search(r'什么|区别|只分析|分析流程|不生成图片|如何|怎么|解释|吗|[？?]|如果|要是',t):return {'action':'explain'}
    # Exact fast paths only: compound feature changes must go through edit first.
    if re.fullmatch(r'(?:请)?(?:去一点杂色|(?:轻度|轻微|稍微)?(?:去杂色|去除杂色|清理杂色)(?:一点)?)',t):return {'action':'denoise','args':{'mode':'light'}}
    if re.fullmatch(r'(?:请)?平衡(?:去杂色|去除杂色|清理杂色)',t):return {'action':'denoise','args':{'mode':'balanced'}}
    strong=re.fullmatch(r'(?:请)?强力简化(?:[，,]?(?:到|至|为|减到|颜色减到)?(\d+)色)?',t)
    if strong:return {'action':'denoise','args':{'mode':'strong',**({'max_colors':int(strong[1])} if strong[1] else {})}}
    recolor=re.fullmatch(r'(?:请)?(?:(?:颜色|色数)(?:减少到|减少至|减少为|减到|减至|改为|改到|降到)|(?:\d+)色改)(\d+)色',t)
    if recolor:return {'action':'recolor','args':{'max_colors':int(recolor[1])}}
    if re.fullmatch(r'保持现在|保持当前|保持原样',t):return {'action':'keep'}
    t=re.sub(r'图案不改|不改图案|不改变图案','',t)
    t=re.sub(r'(调整|修改)pdf排版','标准版',t)
    if re.search(r'修改|改|调整.*(眼|色|图案)|去除|去掉|颜色少|减少颜色',t):return {'action':'adjust'}
    if re.search(r'大字|标准清晰|标准版|页数少|减少页数|字号.*大|pdf字大',t):
        return {'action':'export_pdf','args':{'layout':'large' if re.search(r'大字|字号.*大|pdf字大',t) else 'standard'}}
    if re.search(r'修改|改|调整|去除|去掉|颜色少|减少颜色',t):return {'action':'adjust'}
    if re.search(r'pdf|打印版',t) and re.search(r'导出|下载|给我|打印版|就用',t):return {'action':'export_pdf'}
    if re.search(r'用量清单|清单|csv',t) and re.search(r'下载|导出|给我',t):return {'action':'export_csv'}
    if re.search(r'生成png|做png|继续.*png|生成图纸',t):return {'action':'png'}
    if re.search(r'像素预览|继续做像素',t):return {'action':'pixel'}
    if re.fullmatch(r'可以|好的|好|没问题|确认|这张可以|这张就行|确认原图|确认像素效果|png没问题',t):return {'action':'confirm'}
    if re.search(r'返回上一版|还是上一版|回退',t):return {'action':'rollback'}
    return {'action':'clarify'}

def choose(message,ctx,s):
    menu=ctx.get('menu');t=message.strip()
    pending=ctx.get('pending_cleanup');number=re.fullmatch(r'(\d+)色',t)
    if pending and number and pending['epoch']==s['epoch'] and pending['revision_id']==ctx.get('focus'):
        return {'action':'denoise','args':{'mode':'strong','max_colors':int(number[1])}}
    choice_index={'1':0,'第一个':0,'第一项':0,'2':1,'第二个':1,'第二项':1,'3':2,'第三个':2,'第三项':2,'4':3,'第四个':3,'第四项':3}.get(t)
    recommended=t in ('按推荐来','按推荐','用推荐的')
    if choice_index is not None or recommended:
        if not menu or menu['consumed'] or menu['epoch']!=s['epoch'] or menu['revision_id']!=ctx.get('focus'):
            return {'action':'clarify','reason':'这些选项已失效，请说明这次想做什么。'}
        opts=menu['options']
        if recommended:
            found=[x for x in opts if x.get('recommended')]
            if not found:return {'action':'clarify','reason':'当前没有已展示的明确推荐。'}
            return dict(found[0],from_menu=True)
        if choice_index>=len(opts):return {'action':'clarify','reason':'当前没有这个选项。'}
        return dict(opts[choice_index],from_menu=True)
    if menu and not menu['consumed'] and menu['epoch']==s['epoch'] and menu['revision_id']==ctx.get('focus'):
        for x in menu['options']:
            if t==x['label'] or t in x.get('aliases',[]):return dict(x,from_menu=True)
    return classify(message)

def route(a):
    from . import workflow as w
    timings={};t=time.monotonic();s=w.snapshot(a.project);ctx=context(s,a.conversation)
    decision=choose(a.message,ctx,s);timings['intent']=time.monotonic()-t
    action=decision['action'];args=decision.get('args',{})
    def result(status,**extra):
        child_timings=extra.pop('timings',{})
        timings.update({('export_'+k if k in timings else k):v for k,v in child_timings.items()})
        event={'event':'interaction_route','scope':'local-command-only','conversation':a.conversation,'message_ref':a.message_ref,'intent':action,'result':status,'timings':timings}
        audit(a.project,event)
        return {'status':status,'intent':action,'timings':timings,**extra}
    if action=='no_action':return result('no_action',message='这次不导出。')
    if action=='explain':return result('explanation',message='PNG是图纸图片；PDF将同一网格排成整体预览、分页指南和施工页；用量清单可另存CSV。')
    if action=='clarify':return result('needs_input',question=decision.get('reason','你想调整当前图案，还是继续制作图纸？'))
    t=time.monotonic()
    target=getattr(a,'revision',None) or args.get('revision') or ctx.get('focus')
    if '上一版' in a.message or (action=='rollback' and not (getattr(a,'revision',None) or args.get('revision'))):
        base=current(s,target) if target else current(s)
        parent=base.get('parent_revision')
        if action.startswith('export'):
            # Traverse real pattern lineage; never synthesize an older image.
            while parent and 'pattern' not in current(s,parent)['files']:parent=current(s,parent).get('parent_revision')
        target=parent
    if not target or target not in s['revisions']:
        return result('needs_input',question='请指出要使用的版本。')
    if target!=s['current_revision'] and not (getattr(a,'revision',None) or args.get('revision') or '上一版' in a.message):
        return result('needs_input',question='当前已有新版本，要使用哪一版？')
    r=current(s,target);stage=stage_of(r);timings['state_check']=time.monotonic()-t
    if decision.get('from_menu'):
        with locked(a.project):
            live=load(a.project);lc=context(live,a.conversation)
            require(live['epoch']==s['epoch'] and lc.get('menu',{}).get('menu_id')==ctx['menu']['menu_id'],'STALE_MENU')
            lc['menu']['consumed']=True;save(a.project,live)
    if action=='adjust':
        with locked(a.project):
            live=load(a.project);require(live['epoch']==s['epoch'],'STALE_REQUEST')
            live['pending_modification']={'revision_id':target,'message_ref':a.message_ref,'summary':a.message[:180]};live['epoch']+=1;save(a.project,live)
        return result('modification_required',revision_id=target,message='先完成这次修改并展示新版本，再继续导出。')
    pending=s.get('pending_modification') or any(o.get('status')=='pending' and o.get('epoch')==s['epoch'] for o in s.get('operations',{}).values())
    if action=='rollback':
        out=w.rollback(NS(project=a.project,revision=target));return result('restored',**out)
    if pending:return result('modification_required',revision_id=target,message='当前有尚未完成的修改，先处理修改。')
    if action in ('denoise','recolor','keep'):
        if target!=s['current_revision']:return result('needs_input',question='请先选择要修改的当前版本。')
        if r['kind']!='pixel':return result('needs_input',question='请先确认素材图并生成真实像素预览。')
        if not visible(a.project,ctx,r,stage):return result('needs_presentation',revision_id=target,artifact='preview' if stage=='pixel' else 'pattern')
        if action=='keep':
            with locked(a.project):
                live=load(a.project);require(live['epoch']==s['epoch'],'STALE_REQUEST')
                context(live,a.conversation).pop('pending_cleanup',None);save(a.project,live)
            return result('kept',revision_id=target,message='保留当前像素结果；满意后可确认并生成PNG。')
        if action=='denoise':
            if args.get('mode','light')=='strong' and not args.get('max_colors'):
                with locked(a.project):
                    live=load(a.project);require(live['epoch']==s['epoch'],'STALE_REQUEST')
                    context(live,a.conversation)['pending_cleanup']={'epoch':s['epoch'],'revision_id':target};save(a.project,live)
                return result('needs_input',question='强力简化要收敛到多少色？例如16色、12色或8色。')
            out=w.denoise(NS(project=a.project,current=False,base=target,mode=args.get('mode','light'),max_colors=args.get('max_colors'),protect=args.get('protect')))
        else:
            out=w.pixel(NS(project=a.project,current=False,base=target,width=None,height=None,max_colors=args['max_colors'],palette=None,reserve=None,sampling=None,input=None,operation=None,based_on_sha=None,protect=None))
        return result('file_ready',**out)
    if action.startswith('export') and 'pattern' not in r['files']:
        if r['kind']=='pixel' and confirmed(r,'pixel'):
            if target!=s['current_revision']:return result('needs_input',question='请先选定这版像素图作为当前版本。')
            out=w.attach(NS(project=a.project,revision=target),'pattern')
            return result('png_needs_presentation',message='已先生成PNG供核对；实际展示后再接受导出请求。',**out)
        return result('needs_input',question='先看当前像素效果，是否按这版生成PNG？')
    # Every contextual confirmation requires actual presentation in this conversation.
    if not visible(a.project,ctx,r,stage):return result('needs_presentation',revision_id=target,artifact={'edit':'candidate','pixel':'preview','png':'pattern'}[stage])
    if action in ('pixel','png') and stage!=('edit' if action=='pixel' else 'pixel'):
        return result('needs_input',question='请明确要继续的阶段或要修改的内容。')
    source='contextual_export' if action.startswith('export') else 'explicit'
    t=time.monotonic()
    w.confirm(NS(project=a.project,revision=target,stage=stage,message=a.message,source=source,message_ref=a.message_ref,conversation=a.conversation,allow_historical=True))
    timings['confirmation']=time.monotonic()-t
    if action=='confirm':
        menu=ctx.get('menu')
        if menu and menu['epoch']==s['epoch'] and menu['revision_id']==target:
            recommended=[x for x in menu['options'] if x.get('recommended')]
            if recommended and recommended[0]['action']=={'edit':'pixel','pixel':'png'}.get(stage):action=recommended[0]['action'];args=recommended[0].get('args',{})
        if action=='confirm':return result('confirmed',revision_id=target,stage=stage,message='已确认当前版本。')
    t=time.monotonic()
    if action=='pixel':
        if target!=s['current_revision']:return result('needs_input',question='请先将这版设为当前版本。')
        defaults=dict(width=None,height=None,max_colors=None,palette=None,reserve=None,sampling=None,input=None,operation=None,based_on_sha=None)
        for key in ('width','height','max_colors','palette','reserve','sampling'):
            if key in args:defaults[key]=args[key]
        out=w.pixel(NS(project=a.project,base=target,**defaults))
    elif action=='png':out=w.attach(NS(project=a.project,revision=target),'pattern')
    else:
        fmt=action.removeprefix('export_')
        layout=args.get('layout') or getattr(a,'layout',None) or s.get('preferences',{}).get('pdf_layout','standard')
        out=w.attach(NS(project=a.project,revision=target,cell_pt=None,spare_percent=0,layout=layout,allow_historical=True),fmt)
        if fmt=='pdf':
            with locked(a.project):
                live=load(a.project);live.setdefault('preferences',{})['pdf_layout']=layout;save(a.project,live)
    timings['export_or_render']=time.monotonic()-t
    return result('file_ready',**out)


def inspect(a):
    from . import workflow as w
    s=w.snapshot(a.project);r=current(s);g=w.validate_revision(a.project,r)
    if not g:
        im=w.open_image(checked_file(a.project,r['files']['candidate']));alpha=im.getchannel('A')
        transparent=alpha.getextrema()[0]<255
        return {'revision_id':r['revision_id'],'image_size':list(im.size),'has_transparency':transparent,
                'suggestion':'图片已有透明区域，建议先保留主体做像素预览。' if transparent else '建议先明确是否保留背景，再做像素预览。'}
    from .cleanup import analyze
    analysis=analyze(g)
    return {'revision_id':r['revision_id'],'color_limit':g['max_colors'],**{k:v for k,v in analysis.items() if k!='small_regions'}}
