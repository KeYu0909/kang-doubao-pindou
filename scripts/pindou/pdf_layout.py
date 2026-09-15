"""A4 vector overview + shared-plan guide + balanced construction pages."""
import math
import time
from collections import Counter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.colors import HexColor
from pypdf import PdfReader
from .common import require
from .imaging import grid_check, grid_hash
from .fonts import register_pdf_font

TEMPLATE_VERSION='overview-guide-build-v3-zh'
MARGIN=28
FONT='Helvetica'

def colors(g):return {c['code']:c['hex'] for c in g['palette']['colors']}
def ink(color):
    r,b,c=[int(color[i:i+2],16) for i in (1,3,5)]
    return '#111111' if .299*r+.587*b+.114*c>145 else '#FFFFFF'

def split(n,k):return [(i*n//k,(i+1)*n//k) for i in range(k)]
def column_name(n):
    s=''
    while n>=0:s=chr(65+n%26)+s;n=n//26-1
    return s

def plan(g,cell=None,layout='standard'):
    require(layout in ('standard','large'),'PDF_LAYOUT: standard or large')
    require(cell is None or 14<=cell<=24,'PDF_CELL: explicit legacy cell override must be 14..24pt')
    used=grid_check(g);font=7.0 if layout=='standard' else 9.0
    hscale=.9 if layout=='standard' else 1.0
    padding=1.0 if layout=='standard' else 2.0
    longest=max((stringWidth(code,FONT,font)*hscale for code in used),default=font)
    minimum=max(longest+padding,font+3,cell or 0)
    candidates=[];w,h=g['width'],g['height']
    # Consider fewer panels first; balanced splits avoid a thin final row/column.
    for orientation,(pw,ph) in [('portrait',A4),('landscape',landscape(A4))]:
        available_w=pw-2*MARGIN-18
        best=None
        for nx,ny in sorted(((x,y) for x in range(1,w+1) for y in range(1,h+1)),key=lambda xy:(xy[0]*xy[1],abs(xy[0]-xy[1]))):
            if best is not None and nx*ny>best:break
            cw=math.ceil(w/nx);ch=math.ceil(h/ny)
            if available_w/cw<minimum or (ph-180)/ch<minimum:continue
            panels=[];max_legend=0
            legend_cols=max(1,int(available_w//78))
            for yi,(y0,y1) in enumerate(split(h,ny)):
                for xi,(x0,x1) in enumerate(split(w,nx)):
                    codes=sorted({g['cells'][y][x] for y in range(y0,y1) for x in range(x0,x1)}-{None})
                    max_legend=max(max_legend,math.ceil(len(codes)/legend_cols))
                    panels.append({'id':column_name(xi)+str(yi+1),'page':3+len(panels),'x0':x0,'x1':x1,'y0':y0,'y1':y1,'xi':xi,'yi':yi,'codes':codes})
            legend_height=14*max_legend
            bottom=MARGIN+34+legend_height+18
            available_h=ph-100-bottom
            actual=min(available_w/cw,available_h/ch,cell or max(26,minimum))
            if actual+1e-6<minimum:continue
            best=nx*ny
            candidates.append({'template_version':TEMPLATE_VERSION,'layout':layout,'orientation':orientation,'page_size_pt':[pw,ph],
                'margin_pt':MARGIN,'cell_pt':round(actual,6),'font_pt':font,'horizontal_scale':hscale,'text_padding_total_pt':padding,
                'longest_code_width_pt':longest,'construction_pages':nx*ny,'total_pages':nx*ny+2,'nx':nx,'ny':ny,
                'panels':panels,'legend_cols':legend_cols,'legend_rows':max_legend,'grid_left':MARGIN+18,'grid_top':ph-100,
                'grid_bottom_limit':bottom})
    require(candidates,'PDF_LAYOUT: no readable A4 layout for these codes')
    chosen=min(candidates,key=lambda p:(p['construction_pages'],-p['cell_pt'],p['orientation']!='portrait'))
    require(chosen['construction_pages']<=240,'PDF_GUIDE_DENSE: use standard layout or a smaller code set; guide cannot fit readably')
    return chosen

def page_ranges(g,cell=None,layout='standard'):
    return [(p['x0'],p['y0'],p['x1'],p['y1']) for p in plan(g,cell,layout)['panels']]

def grid_form(c,g):
    pal=colors(g);w,h=g['width'],g['height'];c.beginForm('PatternGrid',0,0,w,h)
    # One vector form shared by overview, guide and every locator. Run-length fills.
    for y,row in enumerate(g['cells']):
        x=0
        while x<w:
            code=row[x];end=x+1
            while end<w and row[end]==code:end+=1
            c.setFillColor(HexColor(pal[code] if code else '#F0F1F3'));c.rect(x,h-y-1,end-x,1,fill=1,stroke=0);x=end
    c.endForm()

def draw_map(c,g,box):
    x,y,bw,bh=box;unit=min(bw/g['width'],bh/g['height']);x+=(bw-unit*g['width'])/2;y+=(bh-unit*g['height'])/2
    c.saveState();c.translate(x,y);c.scale(unit,unit);c.doForm('PatternGrid');c.restoreState()
    return x,y,unit

def text(c,x,y,value,size=9,bold=False):
    c.setFillColorRGB(.1,.14,.18);c.setFont(register_pdf_font(),size);c.drawString(x,y,str(value))

def footer(c,g,rev,page,total,pw):
    text(c,MARGIN,18,f'第 {page}/{total} 页 | 版本 {rev} | 非实物 1:1 摆豆模板',7)
    text(c,MARGIN,8,'网格校验 SHA256 '+grid_hash(g),5.4)

def panel_label(p):return f"{p['id']} | 第{p['page']}页 | 列{p['x0']+1}-{p['x1']} 行{p['y0']+1}-{p['y1']}"

def overview_box(p):
    pw,ph=p['page_size_pt'];return (MARGIN,65,pw-2*MARGIN,ph-165)

def guide_geometry(p):
    pw,ph=p['page_size_pt'];n=len(p['panels']);cols=2 if n<=36 else (3 if n<=90 else 4)
    rows=math.ceil(n/cols);line=11 if n<=90 else 9
    table_h=rows*line;map_h=min(ph*.46,ph-210-table_h)
    require(map_h>=70,'PDF_GUIDE_DENSE: guide not readable')
    return cols,rows,line,map_h

def render(g,path,rev,cell=None,layout='standard',pagination=None):
    p=pagination or plan(g,cell,layout);pw,ph=p['page_size_pt'];pal=colors(g);counts=grid_check(g);total=p['total_pages']
    c=canvas.Canvas(str(path),pagesize=(pw,ph),pageCompression=1,invariant=1)
    c.setTitle(f'{rev} {g["width"]}x{g["height"]}');c.setSubject('grid_sha256='+grid_hash(g));c.setAuthor('永康玩AI · 拼豆助手')
    c.setKeywords(TEMPLATE_VERSION+' '+layout)
    grid_form(c,g)
    text(c,MARGIN,ph-35,'拼豆图案总览',19,True)
    text(c,MARGIN,ph-54,f'{g["width"]} × {g["height"]} 格 | {len(counts)} 色 | {sum(counts.values())} 颗 | 色板 {g["palette"]["name"]}',10)
    text(c,MARGIN,ph-70,rev,8)
    draw_map(c,g,overview_box(p))
    text(c,MARGIN,45,'整体预览；详细色号与分区见后续页面。',9)
    footer(c,g,rev,1,total,pw);c.showPage()
    text(c,MARGIN,ph-35,'分页定位指南',19,True)
    text(c,MARGIN,ph-54,f'横向 {p["nx"]} 区 × 纵向 {p["ny"]} 区 | X为列，Y为行 | 左上角起，从1开始',9)
    cols,rows,line,map_h=guide_geometry(p);mx,my,unit=draw_map(c,g,(MARGIN,ph-78-map_h,pw-2*MARGIN,map_h))
    for tile in p['panels']:
        xx=mx+tile['x0']*unit;yy=my+(g['height']-tile['y1'])*unit;ww=(tile['x1']-tile['x0'])*unit;hh=(tile['y1']-tile['y0'])*unit
        c.setStrokeColorRGB(.12,.18,.3);c.setLineWidth(1);c.rect(xx,yy,ww,hh,fill=0,stroke=1)
        label=f"{tile['id']} / 第{tile['page']}页";fs=9 if len(p['panels'])<=36 else 6
        label_w=stringWidth(label,register_pdf_font(),fs)+8
        c.setFillColorRGB(1,1,1);c.rect(xx+(ww-label_w)/2,yy+hh/2-3,label_w,fs+6,fill=1,stroke=0)
        text(c,xx+(ww-label_w)/2+4,yy+hh/2,label,fs,True)
        c.linkRect('',tile['id'],(xx,yy,xx+ww,yy+hh),relative=0,thickness=0)
    table_top=ph-96-map_h;colw=(pw-2*MARGIN)/cols
    for i,tile in enumerate(p['panels']):
        text(c,MARGIN+(i//rows)*colw,table_top-(i%rows)*line,panel_label(tile),7 if cols<4 else 6)
    yy=table_top-rows*line-16
    for msg in ['先按定位图找到区域，再按全局坐标拼豆。','空格不是白色豆；页面分区用于阅读，不等于实际拼板分区。','请按舒适尺寸打印；未配置真实豆距，不作为1:1摆豆模板。']:
        text(c,MARGIN,yy,msg,8);yy-=12
    footer(c,g,rev,2,total,pw);c.showPage()
    for tile in p['panels']:
        c.bookmarkPage(tile['id']);text(c,MARGIN,ph-28,f'分区 {tile["id"]} | 第 {tile["page"]}/{total} 页',13,True)
        text(c,MARGIN,ph-43,f'版本 {rev} | 第{tile["x0"]+1}-{tile["x1"]}列；第{tile["y0"]+1}-{tile["y1"]}行',8)
        neighbors=[]
        for label,dx,dy in [('左',-1,0),('右',1,0),('上',0,-1),('下',0,1)]:
            if 0<=tile['xi']+dx<p['nx'] and 0<=tile['yi']+dy<p['ny']:neighbors.append(label+': '+column_name(tile['xi']+dx)+str(tile['yi']+dy+1))
        text(c,MARGIN,ph-58,' | '.join(neighbors) or '完整网格',8)
        text(c,MARGIN,ph-72,f'{"标准清晰版" if layout=="standard" else "大字施工版"} | 色号 {p["font_pt"]:g}pt | 格子 {p["cell_pt"]:.2f}pt | 全局坐标',7)
        # Locator is clear of the header text and grid; narrow, right-aligned.
        lx,ly,lu=draw_map(c,g,(pw-86,ph-77,58,58));c.setStrokeColorRGB(.88,.1,.12);c.setLineWidth(1.3)
        c.rect(lx+tile['x0']*lu,ly+(g['height']-tile['y1'])*lu,(tile['x1']-tile['x0'])*lu,(tile['y1']-tile['y0'])*lu,fill=0,stroke=1)
        left,top,size=p['grid_left'],p['grid_top'],p['cell_pt']
        for x in range(tile['x0'],tile['x1']):
            c.setFont(FONT,7);c.setFillColorRGB(0,0,0);c.drawCentredString(left+(x-tile['x0']+.5)*size,top+5,str(x+1))
        for y in range(tile['y0'],tile['y1']):
            c.setFont(FONT,7);c.setFillColorRGB(0,0,0);c.drawRightString(left-5,top-(y-tile['y0']+.5)*size-2,str(y+1))
            for x in range(tile['x0'],tile['x1']):
                code=g['cells'][y][x];fill=pal[code] if code else '#EEEEEE';xx=left+(x-tile['x0'])*size;yy=top-(y-tile['y0']+1)*size
                c.setFillColor(HexColor(fill));c.setStrokeColor(HexColor('#9EA3AA'));c.setLineWidth(.22);c.rect(xx,yy,size,size,fill=1,stroke=1)
                content=code or '.';width=stringWidth(content,FONT,p['font_pt'])*p['horizontal_scale']
                c.setFillColor(HexColor(ink(fill)));t=c.beginText(xx+(size-width)/2,yy+(size-p['font_pt'])/2+1)
                t.setFont(FONT,p['font_pt']);t.setHorizScale(100*p['horizontal_scale']);t.textOut(content);c.drawText(t)
        bottom=top-(tile['y1']-tile['y0'])*size;legend_top=bottom-22
        text(c,left,legend_top,'本页色号图例（非采购清单）',7,True)
        for i,code in enumerate(tile['codes']):
            xx=left+(i%p['legend_cols'])*78;yy=legend_top-15-(i//p['legend_cols'])*14
            c.setFillColor(HexColor(pal[code]));c.rect(xx,yy-1,8,8,fill=1,stroke=0);text(c,xx+12,yy,f'{code} {pal[code]}',7)
        footer(c,g,rev,tile['page'],total,pw);c.showPage()
    c.save();return p

def check(g,path,rev,cell=None,raster=False,layout='standard',pagination=None):
    p=pagination or plan(g,cell,layout);reader=PdfReader(path)
    require(len(reader.pages)==p['total_pages'],'PDF_PAGES')
    require(reader.metadata.subject=='grid_sha256='+grid_hash(g) and rev in reader.metadata.title,'PDF_VERSION')
    zh=p['template_version'].endswith('-zh')
    require(('拼豆图案总览' if zh else 'PATTERN OVERVIEW') in reader.pages[0].extract_text() and ('分页定位指南' if zh else 'PAGE GUIDE') in reader.pages[1].extract_text(),'PDF_FRONT_PAGES')
    guide=reader.pages[1].extract_text();codes=set(colors(g));counts=Counter()
    for tile,page in zip(p['panels'],reader.pages[2:]):
        label=panel_label(tile) if zh else f"{tile['id']} | PDF {tile['page']} | X{tile['x0']+1}-{tile['x1']} Y{tile['y0']+1}-{tile['y1']}"
        require(label in guide,'PDF_GUIDE_PAGE_MAPPING')
        raw=page.extract_text();coordinate_label=f'第{tile["x0"]+1}-{tile["x1"]}列；第{tile["y0"]+1}-{tile["y1"]}行' if zh else f'Columns {tile["x0"]+1}-{tile["x1"]}; Rows {tile["y0"]+1}-{tile["y1"]}'
        require(coordinate_label in raw,'PDF_COORDINATES')
        grid_text=raw.split(('全局坐标' if zh else 'global coordinates')+'\n',1)[1].split('本页色号图例' if zh else 'LOCAL COLOR KEY',1)[0]
        actual=[x for x in grid_text.split() if x in codes or x=='.']
        expected=[g['cells'][y][x] or '.' for y in range(tile['y0'],tile['y1']) for x in range(tile['x0'],tile['x1'])]
        require(actual==expected,'PDF_ORDERED_CELLS: missing, rotated or mirrored cells')
        counts.update(x for x in actual if x!='.')
        require(not page.images,'PDF_BITMAP: expected vector form')
    require(dict(counts)==grid_check(g),'PDF_COUNTS')
    require(p['font_pt']>=7 and p['longest_code_width_pt']+p['text_padding_total_pt']<=p['cell_pt']+1e-5,'PDF_TEXT_FIT')
    if raster:
        import pypdfium2 as pdfium
        pal=colors(g);doc=pdfium.PdfDocument(str(path));scale=2
        try:
            for i in range(len(doc)):
                page=doc[i];bitmap=page.render(scale=scale);im=bitmap.to_pil().convert('RGB')
                try:
                    require(im.getextrema()!=((255,255),(255,255),(255,255)),'PDF_BLANK_PAGE')
                    if i==0:
                        bx,by,bw,bh=overview_box(p);unit=min(bw/g['width'],bh/g['height']);bx+=(bw-unit*g['width'])/2;by+=(bh-unit*g['height'])/2
                        samples=[(x,y,bx+(x+.5)*unit,by+(g['height']-y-.5)*unit) for y in range(g['height']) for x in range(g['width'])]
                        empty='#F0F1F3'
                    elif i>=2:
                        tile=p['panels'][i-2];size=p['cell_pt'];samples=[(x,y,p['grid_left']+(x-tile['x0']+.17)*size,p['grid_top']-(y-tile['y0']+.18)*size) for y in range(tile['y0'],tile['y1']) for x in range(tile['x0'],tile['x1'])];empty='#EEEEEE'
                    else:samples=[];empty='#EEEEEE'
                    for x,y,px,py in samples:
                        color=pal[g['cells'][y][x]] if g['cells'][y][x] else empty
                        expected=tuple(int(color[k:k+2],16) for k in (1,3,5));actual=im.getpixel((int(px*scale),int((p['page_size_pt'][1]-py)*scale)))
                        require(max(abs(a-b) for a,b in zip(actual,expected))<=4,f'PDF_RENDER_CELL: page {i+1}, cell {x+1},{y+1}')
                finally:bitmap.close();page.close()
        finally:doc.close()
    return p
