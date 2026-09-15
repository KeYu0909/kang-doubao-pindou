"""Deterministic image and grid operations; no network or generative calls."""
from collections import Counter, deque
import re
import warnings
import numpy as np
from PIL import Image, ImageOps
from .colors import srgb_to_lab, ciede2000, to_grid
from .common import ROOT, require, read_json, digest, canonical, WorkflowError

Image.MAX_IMAGE_PIXELS = 24_000_000

def open_image(path):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as im:
                require(im.format in ('PNG','JPEG','WEBP'), 'IMAGE_FORMAT: use PNG, JPEG or WEBP')
                require(getattr(im, 'n_frames', 1) == 1, 'IMAGE_ANIMATED: provide one still image')
                im.load()
                return ImageOps.exif_transpose(im).convert('RGBA')
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise WorkflowError(f'INVALID_IMAGE: {exc}') from exc

def crop_image(im, crop):
    if not crop:
        return im
    x,y,w,h = crop
    require(all(type(v) is int for v in crop) and min(x,y)>=0 and min(w,h)>0 and x+w<=im.width and y+h<=im.height,
            f'CROP_OUT_OF_BOUNDS: image={im.size}, crop={crop}')
    return im.crop((x,y,x+w,y+h))

def remove_edge(im, hex_color, tolerance):
    require(re.fullmatch(r'#[0-9A-Fa-f]{6}', hex_color) is not None, 'BACKGROUND_COLOR: use #RRGGBB')
    require(0 <= tolerance <= 80, 'BACKGROUND_TOLERANCE: 0..80')
    a=np.array(im); h,w=a.shape[:2]
    rgb=np.array([int(hex_color[i:i+2],16) for i in (1,3,5)])
    similar=(np.max(np.abs(a[:,:,:3].astype(int)-rgb),axis=2)<=tolerance) | (a[:,:,3]==0)
    seen=np.zeros((h,w),dtype=bool); q=deque()
    for x,y in [(x,y) for x in range(w) for y in (0,h-1)]+[(x,y) for y in range(h) for x in (0,w-1)]:
        if similar[y,x] and not seen[y,x]: seen[y,x]=True; q.append((x,y))
    while q:
        x,y=q.popleft()
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0<=nx<w and 0<=ny<h and similar[ny,nx] and not seen[ny,nx]:
                seen[ny,nx]=True; q.append((nx,ny))
    a[seen,3]=0
    return Image.fromarray(a), int(seen.sum())

def palette_load(path=None):
    p=read_json(path or ROOT/'assets/mard.json')
    require(isinstance(p.get('name'),str) and len(p['name'])<=40 and p['name'].isascii() and re.fullmatch(r'[A-Za-z0-9 _.-]+',p['name']), 'PALETTE_NAME: printable ASCII identifier required')
    require(p.get('source') and p.get('license'), 'PALETTE_PROVENANCE: source and license required; use a verified mapping')
    colors=p.get('colors',[])
    require(1<=len(colors)<=512,'PALETTE_SIZE: 1..512')
    codes=[]
    for c in colors:
        require(re.fullmatch(r'[A-Za-z0-9_-]{1,5}',str(c.get('code',''))) is not None, 'PALETTE_CODE: 1..5 ASCII letters/digits/_/-')
        require(any(ch.isalpha() for ch in c['code']), 'PALETTE_CODE: include a letter to distinguish codes from coordinates')
        require(re.fullmatch(r'#[0-9A-Fa-f]{6}',str(c.get('hex',''))) is not None,'PALETTE_HEX: invalid #RRGGBB')
        codes.append(c['code'])
    require(len(set(codes))==len(codes),'PALETTE_DUPLICATE_CODE')
    return p

def grid_build(im, width, height, palette, max_colors, reserve, sampling='box'):
    require(1<=width<=192 and 1<=height<=192, 'GRID_SIZE: each dimension 1..192')
    require(1<=max_colors<=len(palette['colors']), 'MAX_COLORS: outside palette range')
    codes=[c['code'] for c in palette['colors']]
    require(set(reserve)<=set(codes) and len(set(reserve))<=max_colors, 'RESERVE_COLORS: invalid codes or exceeds cap')
    require(sampling in ('box','nearest'), 'SAMPLING: box or nearest')
    # Reused aspect-preserving transparent padding. Explicit nearest is for existing pixel art.
    if sampling=='box': a=to_grid(im,width,height,True)
    else:
        ratio=min(width/im.width,height/im.height); nw=max(1,round(im.width*ratio)); nh=max(1,round(im.height*ratio))
        canvas=Image.new('RGBA',(width,height)); canvas.paste(im.resize((nw,nh),Image.Resampling.NEAREST),((width-nw)//2,(height-nh)//2)); a=np.array(canvas)
    mask=a[:,:,3]>=128
    require(mask.any(), 'EMPTY_GRID: no opaque cells; inspect input or alpha threshold')
    samples=a[:,:,:3][mask]
    rgb=np.array([[int(c['hex'][i:i+2],16) for i in (1,3,5)] for c in palette['colors']])
    labs=srgb_to_lab(rgb)
    # Bound peak memory: CIEDE2000 operates on <=512 cells at a time.
    def nearest(targets):
        return np.concatenate([np.argmin(ciede2000(srgb_to_lab(samples[i:i+512]), labs[targets]),axis=1) for i in range(0,len(samples),512)])
    all_ids=list(range(len(codes))); initial=nearest(all_ids); counts=Counter(initial.tolist())
    chosen=[codes.index(c) for c in dict.fromkeys(reserve)]
    for i,_ in sorted(counts.items(), key=lambda item:(-item[1],item[0])):
        if i not in chosen and len(chosen)<max_colors: chosen.append(i)
    mapped=nearest(chosen); cells=[[None]*width for _ in range(height)]
    for (y,x),idx in zip(np.argwhere(mask),mapped): cells[int(y)][int(x)]=codes[chosen[int(idx)]]
    ratio=min(width/im.width,height/im.height); nw=max(1,round(im.width*ratio)); nh=max(1,round(im.height*ratio))
    data={'schema_version':1,'width':width,'height':height,'palette':palette,'max_colors':max_colors,'cells':cells,
          'processing':{'fit':'contain','source_size':list(im.size),'scaled_size':[nw,nh],
                        'padding':[ (width-nw)//2,(height-nh)//2,width-nw-(width-nw)//2,height-nh-(height-nh)//2],
                        'crop':None,'sampling':sampling,'alpha_threshold':128,'reserved_codes':reserve,'cleanup':'none'}}
    return data

def grid_check(g):
    require(type(g['width']) is int and type(g['height']) is int and 1<=g['width']<=192 and 1<=g['height']<=192,'GRID_SIZE: corrupt')
    palette_load_data = g['palette']['colors']
    codes={c['code'] for c in palette_load_data}
    require(len(g['cells'])==g['height'] and all(len(row)==g['width'] for row in g['cells']),'GRID_SHAPE: corrupt')
    counts=Counter(c for row in g['cells'] for c in row if c is not None)
    require(set(counts)<=codes and len(counts)<=g['max_colors'],'GRID_COLORS: corrupt')
    return dict(sorted(counts.items()))

def grid_hash(g):
    return digest(canonical(g))
