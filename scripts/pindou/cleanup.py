"""Deterministic four-neighbour component cleanup. Original implementation, MIT.
Coordinates in public protection files and analysis are one-based (x, y).
No semantic segmentation, random sampling, image generation or changes to empty cells.
"""
from collections import Counter, deque
from copy import deepcopy
import numpy as np
from .colors import srgb_to_lab, ciede2000
from .common import require
from .imaging import grid_check, grid_hash

MODES = {'light': (2, 10.0, .75), 'balanced': (5, 18.0, .6), 'strong': (5, 20.0, .6)}


def neighbours(x, y, w, h):
    for nx, ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
        if 0 <= nx < w and 0 <= ny < h:
            yield nx, ny


def components(g):
    w,h=g['width'],g['height'];cells=g['cells'];seen=set();regions=[]
    for y in range(h):
        for x in range(w):
            code=cells[y][x]
            if code is None or (x,y) in seen: continue
            seen.add((x,y));q=deque([(x,y)]);points=[];boundary=Counter();edge=False
            while q:
                px,py=q.popleft();points.append((px,py))
                edge |= px in (0,w-1) or py in (0,h-1)
                for nx,ny in neighbours(px,py,w,h):
                    other=cells[ny][nx]
                    if other==code:
                        if (nx,ny) not in seen:seen.add((nx,ny));q.append((nx,ny))
                    else:
                        boundary[other]+=1
                        edge |= other is None
            regions.append({'code':code,'points':points,'area':len(points),'boundary':boundary,'edge':edge})
    return regions


def colour_metrics(g):
    colors={c['code']:c['hex'] for c in g['palette']['colors']};codes=sorted(grid_check(g))
    labs=srgb_to_lab(np.array([[int(colors[c][i:i+2],16) for i in (1,3,5)] for c in codes]))
    distances=ciede2000(labs,labs)
    return {c:float(labs[i,0]) for i,c in enumerate(codes)}, {(a,b):float(distances[i,j]) for i,a in enumerate(codes) for j,b in enumerate(codes)}


def protection(g, extra=None):
    specs=[g.get('protection',{}), extra or {}];points=set();codes=set();regions=[];labels=[]
    known={c['code'] for c in g['palette']['colors']}
    for spec in specs:
        require(isinstance(spec,dict),'PROTECTION_FORMAT: expected an object')
        require(not (set(spec)-{'cells','regions','codes','labels'}),'PROTECTION_FORMAT: unknown field')
        codes.update(spec.get('codes',[]));labels.extend(spec.get('labels',[]))
        for point in spec.get('cells',[]):
            require(isinstance(point,list) and len(point)==2 and all(type(v) is int for v in point),'PROTECTION_COORDINATES')
            x,y=point;require(1<=x<=g['width'] and 1<=y<=g['height'],'PROTECTION_COORDINATES: outside grid')
            points.add((x-1,y-1))
        for box in spec.get('regions',[]):
            require(isinstance(box,list) and len(box)==4 and all(type(v) is int for v in box),'PROTECTION_COORDINATES')
            x0,y0,x1,y1=box
            require(1<=x0<=x1<=g['width'] and 1<=y0<=y1<=g['height'],'PROTECTION_COORDINATES: outside grid')
            regions.append(box)
            points.update((x,y) for y in range(y0-1,y1) for x in range(x0-1,x1))
    require(codes<=known,'PROTECTION_COLOR: unknown palette code')
    points.update((x,y) for y,row in enumerate(g['cells']) for x,c in enumerate(row) if c in codes)
    spec={'cells':[[x+1,y+1] for x,y in sorted(points,key=lambda p:(p[1],p[0]))], 'codes':sorted(codes),'regions':regions,'labels':list(dict.fromkeys(labels))}
    return points,spec


def feature_colors(g, requirements):
    """Conservative colour tags protect all used matching shades, not a claimed eye segmentation."""
    import colorsys
    labels=' '.join(requirements).lower();used=grid_check(g);codes=[]
    words={'green':('绿色','绿眼','green'),'red':('红色','红帽','red'),'pink':('粉色','粉鼻','pink'),
           'blue':('蓝色','blue'),'yellow':('黄色','yellow'),'black':('黑色','black'),'white':('白色','white')}
    wanted={key for key,aliases in words.items() if any(alias in labels for alias in aliases)}
    for color in g['palette']['colors']:
        if color['code'] not in used:continue
        r,gg,b=[int(color['hex'][i:i+2],16)/255 for i in (1,3,5)]
        h,s,v=colorsys.rgb_to_hsv(r,gg,b);h*=360
        kinds=set()
        if 65<=h<=170 and s>=.18:kinds.add('green')
        if (h<=25 or h>=335) and s>=.25:kinds.add('red')
        if (h<=25 or h>=300) and r>=.6 and b>=.3 and s>=.1:kinds.add('pink')
        if 170<h<270 and s>=.2:kinds.add('blue')
        if 25<h<65 and s>=.2:kinds.add('yellow')
        if v<.3:kinds.add('black')
        if v>.8 and s<.15:kinds.add('white')
        if kinds & wanted:codes.append(color['code'])
    return {'codes':codes,'labels':requirements}


def stats(g, regions=None):
    counts=grid_check(g);regions=components(g) if regions is None else regions
    sizes=Counter(r['area'] for r in regions)
    rare=[{'code':c,'count':n} for c,n in counts.items() if n<=5]
    return {'width':g['width'],'height':g['height'],'total_cells':g['width']*g['height'],
            'used_colors':len(counts),'nonempty_cells':sum(counts.values()),'components':len(regions),
            'singletons':sizes[1],'doubletons':sizes[2],'small_3_5':sum(sizes[n] for n in (3,4,5)),
            'small_1_2':sizes[1]+sizes[2],'small_1_5':sum(sizes[n] for n in range(1,6)),
            'low_frequency_colors':len(rare),'rare_colors':rare}


def rules(g, extra=None, mode='light'):
    require(mode in MODES,'CLEANUP_MODE')
    regions=components(g);points,spec=protection(g,extra);lightness,dist=colour_metrics(g)
    max_area,threshold,dominance=MODES[mode];counts=grid_check(g);records=[];changes=[]
    for r in regions:
        boundary=r['boundary'];ranked=sorted(((c,n) for c,n in boundary.items() if c is not None),key=lambda a:(-a[1],a[0]))
        target=ranked[0][0] if ranked else None;share=ranked[0][1]/sum(boundary.values()) if ranked else 0
        delta=dist[r['code'],target] if target else None
        reason=None
        if any(p in points for p in r['points']):reason='explicit_protection'
        elif lightness[r['code']]<22:reason='dark_outline'
        elif r['edge']:reason='silhouette_or_decoration'
        elif any(dist[r['code'],c]>=25 for c in boundary if c is not None):reason='high_contrast'
        eligible=r['area']<=max_area or (mode!='light' and r['area']<=8 and counts[r['code']]<=8)
        can_merge=eligible and not reason and target is not None and share>=dominance and delta<=threshold
        # Merge into a strictly more frequent colour: no swapping/toggling islands in a single pass.
        can_merge=can_merge and counts[target]>counts[r['code']]
        if can_merge: changes.extend((x,y,target) for x,y in r['points'])
        if r['area']<=8:
            records.append({'code':r['code'],'area':r['area'],'cells':[[x+1,y+1] for x,y in r['points']],
                'neighbours':[{'code':c,'boundary_edges':n} for c,n in ranked],
                'dominant_color':target,'dominant_share':round(share,4),'delta_e':round(delta,3) if delta is not None else None,
                'protected_reason':reason,'candidate_merge':bool(can_merge),'merge_to':target if can_merge else None})
    return changes,records,regions,spec


def reduce_colors(g, cap, extra=None):
    require(type(cap) is int and 1<=cap<=len(g['palette']['colors']),'COLOR_LIMIT: invalid max-colors')
    counts=grid_check(g);points,spec=protection(g,extra);lightness,dist=colour_metrics(g)
    # Conservative component protection survives global colour convergence too.
    for r in components(g):
        if lightness[r['code']]<22 or (r['area']<=8 and r['edge']) or any(dist[r['code'],c]>=25 for c in r['boundary'] if c is not None):
            points.update(r['points'])
    required={g['cells'][y][x] for x,y in points}-{None}
    require(len(required)<=cap,'PROTECTION_COLOR_CONFLICT: protected colours exceed requested limit')
    chosen=sorted(required)
    for c in sorted(counts,key=lambda c:(-counts[c],c)):
        if c not in chosen and len(chosen)<cap:chosen.append(c)
    out=deepcopy(g);out['max_colors']=cap;out['protection']=spec
    mapping={c:min(chosen,key=lambda target:(dist[c,target],target)) for c in counts if c not in chosen}
    out['cells']=[[mapping.get(c,c) if c is not None else None for c in row] for row in g['cells']]
    grid_check(out);return out


def compare(before, after):
    changes=[{'x':x+1,'y':y+1,'from':c,'to':after['cells'][y][x]} for y,row in enumerate(before['cells']) for x,c in enumerate(row) if c!=after['cells'][y][x]]
    return {'before':stats(before),'after':stats(after),'changed_cells':len(changes),
            'changed_percent':round(100*len(changes)/(before['width']*before['height']),4),'changes':changes}


def clean(g, mode='light', max_colors=None, extra=None):
    require(mode in MODES,'CLEANUP_MODE')
    if mode=='strong':
        require(max_colors is not None,'TARGET_COLORS_REQUIRED: strong mode requires explicit max-colors')
        require(max_colors < len(grid_check(g)),'COLOR_REDUCTION_REQUIRED: choose a lower actual colour count')
        out=reduce_colors(g,max_colors,extra)
    else:
        require(max_colors is None,'CLEANUP_COLOR_LIMIT: max-colors only applies to strong mode')
        out=deepcopy(g)
    changes,_,_,spec=rules(out,extra,mode);out['protection']=spec
    for x,y,target in changes:out['cells'][y][x]=target
    summary=compare(g,out)
    out.setdefault('processing',{})['cleanup']={'method':'components-lab-v1','mode':mode,'base_grid_sha256':grid_hash(g),**summary}
    grid_check(out)
    return out,summary


def analyze(g, extra=None):
    changes,records,regions,_=rules(g,extra,'light');summary=stats(g,regions)
    preview=deepcopy(g)
    for x,y,target in changes:preview['cells'][y][x]=target
    after=stats(preview)
    recommendation='light' if changes else 'keep'
    return {**summary,'small_regions':records,'recommendation':recommendation,
            'estimate':{'mode':'light','changed_cells':len(changes),'used_colors_after':after['used_colors'],'small_1_5_after':after['small_1_5']},
            'hint':f'检测到{summary["small_1_2"]}个1–2格小色块；轻度处理预计修改{len(changes)}格，保留保护区和高对比结构。' if changes else '未发现符合保守合并条件的明显杂色，可以保持当前效果继续。',
            'options':[{'label':'轻度去杂色','action':'denoise','args':{'mode':'light'},'recommended':bool(changes)},
                       {'label':'平衡去杂色','action':'denoise','args':{'mode':'balanced'}},
                       {'label':'强力简化','action':'denoise','args':{'mode':'strong'}},
                       {'label':'保持现在','action':'keep','recommended':not bool(changes)}]}
