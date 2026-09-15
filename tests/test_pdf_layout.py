import tempfile,unittest
from pathlib import Path
from collections import Counter
from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from pindou.pdf_layout import plan,render,check,split,ink,panel_label
from pindou.imaging import grid_hash
from pdf_benchmark import fixture

class PDFLayoutTests(unittest.TestCase):
    def test_balanced_partition_covers_every_cell_once_and_page_offsets(self):
        for dims,long in [((78,78),False),((91,47),True),((47,91),True),((1,192),False)]:
            g=fixture(*dims,long_codes=long)
            for layout in ('standard','large'):
                p=plan(g,layout=layout);seen=Counter()
                for i,t in enumerate(p['panels']):
                    self.assertEqual(t['page'],i+3)
                    self.assertEqual((t['yi'],t['xi']),divmod(i,p['nx']))
                    seen.update((x,y) for y in range(t['y0'],t['y1']) for x in range(t['x0'],t['x1']))
                self.assertEqual(len(seen),dims[0]*dims[1]);self.assertEqual(set(seen.values()),{1})
                self.assertEqual(p['total_pages'],len(p['panels'])+2)
                self.assertGreaterEqual(p['margin_pt'],28)
                for n,k in zip(dims,[p['nx'],p['ny']]):
                    sizes=[b-a for a,b in split(n,k)];self.assertLessEqual(max(sizes)-min(sizes),1)
    def test_78_candidate_six_pages_without_small_type(self):
        g=fixture();p=plan(g);self.assertEqual((p['nx'],p['ny'],p['total_pages']),(2,2,6));self.assertGreaterEqual(p['font_pt'],7)
        self.assertGreater(plan(g,layout='large')['cell_pt'],p['cell_pt'])
    def test_nonsquare_long_codes_real_render_all_pages_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            for dims in [(91,47),(47,91)]:
                g=fixture(*dims,long_codes=True);before=grid_hash(g)
                for layout in ('standard','large'):
                    p=plan(g,layout=layout);path=Path(tmp)/(str(dims)+layout+'.pdf')
                    render(g,path,'test-corners',layout=layout,pagination=p);check(g,path,'test-corners',raster=True,layout=layout,pagination=p)
                    r=PdfReader(path);self.assertIn('拼豆图案总览',r.pages[0].extract_text());self.assertIn('分页定位指南',r.pages[1].extract_text());self.assertIn('本页色号图例',r.pages[2].extract_text());self.assertNotIn('SECTION',r.pages[2].extract_text());self.assertTrue(all(not page.images for page in r.pages));self.assertEqual(len(r.pages[1]['/Annots']),len(p['panels']))
                    for tile in p['panels']:
                        self.assertIn(panel_label(tile),r.pages[1].extract_text())
                        codes=tile['codes'];bottom=p['grid_top']-(tile['y1']-tile['y0'])*p['cell_pt']
                        self.assertGreaterEqual(bottom,p['grid_bottom_limit']-1e-4)
                        for code in codes:self.assertLessEqual(stringWidth(code,'Helvetica',p['font_pt'])*p['horizontal_scale']+p['text_padding_total_pt'],p['cell_pt']+1e-5)
                    self.assertEqual(grid_hash(g),before)
        self.assertEqual(ink('#111111'),'#FFFFFF');self.assertEqual(ink('#FFFFFF'),'#111111')

if __name__=='__main__':unittest.main()
