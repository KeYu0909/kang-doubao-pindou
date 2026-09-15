#!/usr/bin/env python3
"""Reproducible synthetic PDF comparison and ALL-page visual review artifacts."""
import argparse,json,time
from pathlib import Path
from PIL import Image,ImageDraw
from pypdf import PdfReader
import pypdfium2 as pdfium
from pindou.pdf_layout import plan,render,check
from pindou.render import legacy_pdf_render,legacy_pdf_check,png_render,png_check
from pindou.imaging import grid_hash

def fixture(w=78,h=78,long_codes=False):
    values=['#FFFFFF','#111111','#F6D64A','#C82939','#235EAD','#407A52']
    codes=['WWWWW','BLACK','YELLW','RED01','BLUE1','GREEN'] if long_codes else ['A01','B02','C03','D04','E05','F06']
    cells=[]
    for y in range(h):
        row=[]
        for x in range(w):
            if (x+y)%23==0:code=None
            elif x==w//2 or y==h//2:code=codes[1]
            else:code=codes[((x*6//w)+(y*3//h))%6]
            row.append(code)
        cells.append(row)
    for x,y,i in [(0,0,2),(w-1,0,3),(0,h-1,4),(w-1,h-1,5)]:cells[y][x]=codes[i]
    return {'schema_version':1,'width':w,'height':h,'palette':{'name':'SYNTHETIC-CORNER-GRID','source':'program-generated geometry; no user image','license':'MIT','colors':[{'code':c,'hex':v} for c,v in zip(codes,values)]},'max_colors':6,'cells':cells,'processing':{'source':'pdf_benchmark.fixture'}}

def review_pages(path,out):
    out.mkdir(parents=True,exist_ok=True);doc=pdfium.PdfDocument(str(path));thumbs=[]
    try:
        for i in range(len(doc)):
            page=doc[i];bitmap=page.render(scale=1.5)
            try:
                im=bitmap.to_pil().convert('RGB');im.save(out/f'page-{i+1:02}.png')
                im.thumbnail((450,640));thumbs.append(im)
            finally:bitmap.close();page.close()
    finally:doc.close()
    for batch in range(0,len(thumbs),6):
        portion=thumbs[batch:batch+6];sheet=Image.new('RGB',(930,690*((len(portion)+1)//2)),'#D3D7DF');draw=ImageDraw.Draw(sheet)
        for j,im in enumerate(portion):
            x=10+(j%2)*465;y=28+(j//2)*690;sheet.paste(im,(x,y));draw.text((x,y-18),f'{path.stem} - page {batch+j+1}',fill='black')
        sheet.save(out/f'contact-{batch//6+1}.png')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='runs/pdf-review');ap.add_argument('--report',default='reports/pdf-comparison.json');a=ap.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);results=[]
    for name,g in [('78x78',fixture()),('91x47-long-codes',fixture(91,47,True))]:
        sha=grid_hash(g);png=out/(name+'.png');png_render(g,png,'synthetic-review');png_check(g,png,'synthetic-review',True)
        for layout in ['legacy','standard','large']:
            path=out/(name+'-'+layout+'.pdf');times={};start=time.monotonic()
            p=None if layout=='legacy' else plan(g,layout=layout);times['pagination']=time.monotonic()-start;start=time.monotonic()
            if p:render(g,path,'synthetic-review',layout=layout,pagination=p)
            else:legacy_pdf_render(g,path,'synthetic-review')
            times['drawing']=time.monotonic()-start;start=time.monotonic()
            if p:check(g,path,'synthetic-review',raster=True,layout=layout,pagination=p)
            else:legacy_pdf_check(g,path,'synthetic-review',raster=True)
            times['validation']=time.monotonic()-start;reader=PdfReader(path)
            assert grid_hash(g)==sha
            review_pages(path,out/(name+'-'+layout))
            results.append({'case':name,'layout':layout,'pages':len(reader.pages),'page_size_pt':[float(v) for v in reader.pages[0].mediabox[2:]],'bytes':path.stat().st_size,'font_pt':p['font_pt'] if p else 18/2.7,'cell_pt':p['cell_pt'] if p else 18,'partition':[p['nx'],p['ny']] if p else None,'grid_unchanged':True,'every_page_raster_checked':True,'timings_seconds':times})
    report={'scope':'local synthetic PDF/PNG only; no AI or Doubao','results':results}
    Path(a.report).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
