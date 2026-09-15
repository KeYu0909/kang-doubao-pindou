"""All renderers consume a frozen grid. PDF uses vectors and original grid codes."""
import csv
import io
import json
import math
from collections import Counter
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader
from .common import require, WorkflowError
from .fonts import png_font
from .imaging import grid_check, grid_hash, open_image

PNG_TEMPLATE_VERSION="png-zh-v1"
CSV_TEMPLATE_VERSION="csv-zh-v1"
CELL=32
LEFT=64
TOP=108

def palette(g): return {c['code']: c['hex'] for c in g['palette']['colors']}
def ink(hex_color):
    r,g,b=[int(hex_color[i:i+2],16) for i in (1,3,5)]
    return '#111111' if r*.299+g*.587+b*.114>145 else '#FFFFFF'

def meta(g,r):
    m=PngImagePlugin.PngInfo()
    for key,val in {'grid_sha256':grid_hash(g),'revision_id':r,'counts':json.dumps(grid_check(g),sort_keys=True)}.items(): m.add_text(key,val)
    return m

def preview(g,path,rev,scale=8):
    colors=palette(g); im=Image.new('RGB',(g['width']*scale,g['height']*scale)); d=ImageDraw.Draw(im)
    for y,row in enumerate(g['cells']):
        for x,code in enumerate(row):
            fill=colors[code] if code else ('#DADDE2' if (x+y)%2 else '#F0F1F3')
            d.rectangle((x*scale,y*scale,(x+1)*scale-1,(y+1)*scale-1),fill=fill)
    im.save(path,pnginfo=meta(g,rev))

def lightweight(source,target):
    im=open_image(source); im.thumbnail((1000,1000)); im.convert('RGB').save(target)

def png_render(g,path,rev):
    colors=palette(g); counts=grid_check(g); w,h=g['width'],g['height']; legend_y=TOP+h*CELL+42
    im=Image.new('RGB',(max(LEFT+w*CELL+32,640),legend_y+70+math.ceil(len(counts)/4)*28),'white'); d=ImageDraw.Draw(im)
    font=png_font(12); large=png_font(20)
    d.text((LEFT,16),f'永康玩AI · 拼豆助手 / {rev} / {w} × {h}格',fill='black',font=large)
    d.text((LEFT,46),f'色板 {g["palette"]["name"]} | 共 {sum(counts.values())} 颗 | 灰色点号为空格；白色豆有色号',fill='black',font=font)
    d.text((LEFT,65),'SHA256 '+grid_hash(g),fill='black',font=ImageFont.load_default(size=10))
    for x in range(w): d.text((LEFT+x*CELL+CELL/2,TOP-18),str(x+1),fill='black',font=font,anchor='mm')
    for y,row in enumerate(g['cells']):
        d.text((LEFT-18,TOP+y*CELL+CELL/2),str(y+1),fill='black',font=font,anchor='mm')
        for x,code in enumerate(row):
            xx,yy=LEFT+x*CELL,TOP+y*CELL
            d.rectangle((xx,yy,xx+CELL,yy+CELL),fill=colors[code] if code else '#EEEEEE',outline='#AAAAAA')
            code_font=ImageFont.load_default(size=min(12, int((CELL-6)/(max(1,len(code or '.'))*.7))))
            d.text((xx+CELL/2,yy+CELL/2),code or '.',fill=ink(colors[code]) if code else '#999999',font=code_font,anchor='mm')
    for x in range(0,w+1,10): d.line((LEFT+x*CELL,TOP,LEFT+x*CELL,TOP+h*CELL),fill='#555555',width=2)
    for y in range(0,h+1,10): d.line((LEFT,TOP+y*CELL,LEFT+w*CELL,TOP+y*CELL),fill='#555555',width=2)
    d.text((LEFT,legend_y-12),'色号 / 用量（屏幕颜色为近似值，请核对实物色卡）',fill='black',font=font)
    colw=(im.width-LEFT-20)//4
    for i,(code,count) in enumerate(counts.items()):
        x=LEFT+(i%4)*colw; y=legend_y+18+(i//4)*28
        d.rectangle((x,y,x+18,y+18),fill=colors[code],outline='black')
        d.text((x+24,y+3),f'{code}: {count}',fill='black',font=font)
    im.save(path,pnginfo=meta(g,rev))

def png_check(g,path,rev,formal=False):
    with Image.open(path) as im:
        im.load(); require(im.info.get('grid_sha256')==grid_hash(g) and im.info.get('revision_id')==rev,'PNG_METADATA: mismatch')
        require(json.loads(im.info['counts'])==grid_check(g),'PNG_COUNTS: mismatch')
        if formal:
            colors=palette(g)
            require(im.width>=LEFT+g['width']*CELL and im.height>TOP+g['height']*CELL,'PNG_INCOMPLETE')
            for y,row in enumerate(g['cells']):
                for x,code in enumerate(row):
                    expected=tuple(int((colors[code] if code else '#EEEEEE')[i:i+2],16) for i in (1,3,5))
                    require(im.getpixel((LEFT+x*CELL+4,TOP+y*CELL+4))==expected,'PNG_CELL: mismatch')
        else:
            require(im.size==(g['width']*8,g['height']*8),'PREVIEW_SIZE: mismatch')

def csv_render(g,path,rev,spare=0):
    counts=grid_check(g); colors=palette(g)
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['色板','色号','颜色值','用量（颗）','建议备损（颗）','作品版本','网格校验值']);writer.writeheader()
        for code,count in counts.items(): writer.writerow({'色板':g['palette']['name'],'色号':code,'颜色值':colors[code],'用量（颗）':count,'建议备损（颗）':math.ceil(count*spare/100),'作品版本':rev,'网格校验值':grid_hash(g)})

def csv_check(g,path,rev):
    with open(path,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    if rows and '色号' in rows[0]:
        mapping={'色板':'palette_brand','色号':'code','颜色值':'hex','用量（颗）':'count','建议备损（颗）':'spare_suggested','作品版本':'revision_id','网格校验值':'grid_sha256'}
        rows=[{mapping[k]:v for k,v in row.items()} for row in rows]
    require(len(rows)==len(grid_check(g)) and {r['code']:int(r['count']) for r in rows}==grid_check(g),'CSV_COUNTS: mismatch')
    colors=palette(g)
    require(all(r['grid_sha256']==grid_hash(g) and r['revision_id']==rev and r['hex']==colors[r['code']] and r['palette_brand']==g['palette']['name'] for r in rows),'CSV_VERSION: mismatch')

def legacy_page_ranges(g,cell):
    require(14<=cell<=24,'PDF_CELL: 14..24 points')
    cols=int((A4[0]-72)//cell); rows=int((A4[1]-140)//cell)
    return [(x,y,min(x+cols,g['width']),min(y+rows,g['height'])) for y in range(0,g['height'],rows) for x in range(0,g['width'],cols)]

def legacy_pdf_render(g,path,rev,cell=18):
    pages=legacy_page_ranges(g,cell); colors=palette(g); out=canvas.Canvas(str(path),pagesize=A4,pageCompression=1)
    out.setTitle(f'{rev} {g["width"]}x{g["height"]}');out.setSubject('grid_sha256='+grid_hash(g));out.setAuthor('Yongkang Wan AI')
    for n,(x0,y0,x1,y1) in enumerate(pages):
        out.setFillColorRGB(0,0,0); out.setFont('Helvetica',10)
        out.drawString(36,A4[1]-28,f'{rev} / {g["width"]}x{g["height"]} / {g["palette"]["name"]} / {n+1} of {len(pages)}')
        out.setFont('Helvetica',7);out.drawString(36,A4[1]-42,f'Columns {x0+1}-{x1}; Rows {y0+1}-{y1}; empty = dot. NOT physical 1:1 scale.')
        out.setFont('Helvetica',6);out.drawString(36,25,'SHA256 '+grid_hash(g));out.drawString(36,37,'Match each printed code to your physical swatch. Screen/print RGB is approximate.')
        top=A4[1]-85
        for x in range(x0,x1): out.drawCentredString(36+(x-x0+.5)*cell,top+8,str(x+1))
        for y in range(y0,y1):
            out.setFillColorRGB(0,0,0);out.setFont('Helvetica',6);out.drawRightString(32,top-(y-y0+.6)*cell,str(y+1))
            for x in range(x0,x1):
                code=g['cells'][y][x];fill=colors[code] if code else '#EEEEEE';xx=36+(x-x0)*cell; yy=top-(y-y0+1)*cell
                out.setFillColor(HexColor(fill));out.setStrokeColor(HexColor('#999999'));out.setLineWidth(.25);out.rect(xx,yy,cell,cell,fill=1,stroke=1)
                out.setFillColor(HexColor(ink(fill)));out.setFont('Helvetica',min(8,cell/2.7));out.drawCentredString(xx+cell/2,yy+cell/2-2.5,code or '.')
        out.showPage()
    counts=grid_check(g)
    # A separate vector legend; one line per used color, paginated.
    for offset in range(0,len(counts),38):
        out.setFillColorRGB(0,0,0);out.setFont('Helvetica',12);out.drawString(36,A4[1]-36,f'LEGEND / {rev} / {sum(counts.values())} beads')
        for i,(code,count) in enumerate(list(counts.items())[offset:offset+38]):
            yy=A4[1]-70-i*18;out.setFillColor(HexColor(colors[code]));out.rect(36,yy-2,12,12,fill=1,stroke=1)
            out.setFillColorRGB(0,0,0);out.setFont('Helvetica',9);out.drawString(58,yy,f'{code} | {colors[code]} | {count}')
        out.showPage()
    out.save()
    return pages

def legacy_pdf_check(g,path,rev,cell=18,raster=False):
    reader=PdfReader(path);pages=legacy_page_ranges(g,cell)
    require(len(reader.pages)==len(pages)+math.ceil(len(grid_check(g))/38),'PDF_PAGES: incomplete')
    require(reader.metadata.subject=='grid_sha256='+grid_hash(g) and rev in reader.metadata.title,'PDF_VERSION: mismatch')
    counts=Counter()
    codes=set(palette(g))
    for page,(x0,y0,x1,y1) in zip(reader.pages,pages):
        text=page.extract_text();require(f'Columns {x0+1}-{x1}; Rows {y0+1}-{y1}' in text,'PDF_COORDINATES: incomplete')
        actual=Counter(line.strip() for line in text.splitlines() if line.strip() in codes or line.strip()=='.')
        expected=Counter(g['cells'][y][x] or '.' for y in range(y0,y1) for x in range(x0,x1))
        require(actual==expected,'PDF_PAGE_CELLS: missing edge, empty or bead cell')
        counts.update(line.strip() for line in text.splitlines() if line.strip() in codes)
    require(dict(counts)==grid_check(g),'PDF_CELLS: incomplete or wrong codes')
    if raster:
        import pypdfium2 as pdfium
        doc=pdfium.PdfDocument(str(path))
        try:
            for page in doc:
                bitmap=page.render(scale=0.7)
                im=bitmap.to_pil();require(im.getextrema()!=((255,255),(255,255),(255,255)),'PDF_RENDER: blank page');bitmap.close();page.close()
        finally:
            doc.close()

# v0.1 PDF functions remain only for historical-file validation and baseline comparison.
from .pdf_layout import plan as pdf_plan, render as pdf_render, check as pdf_check, page_ranges, TEMPLATE_VERSION
