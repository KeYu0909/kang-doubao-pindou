import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import numpy as np
from PIL import Image, ImageDraw
from pypdf import PdfReader
import pypdfium2 as pdfium
from pindou import workflow as w
from pindou.common import WorkflowError, load, save, current, checked_file, canonical
from pindou.imaging import grid_build, grid_check, palette_load, crop_image
from pindou.colors import ciede2000
from pindou.cli import run_bounded
from pindou.render import png_check, pdf_check, LEFT, TOP, CELL


def fixture(path,size=(156,156)):
    im=Image.new('RGBA',size,(0,0,0,0));d=ImageDraw.Draw(im)
    d.rectangle((16,24,size[0]-17,size[1]-17),fill='white')
    d.rectangle((30,40,70,95),fill='red');d.rectangle((82,40,123,95),fill='black')
    d.rectangle((60,30,63,33),fill='#00ff00') # small identity-like accent, not a real animal
    im.save(path)

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.input=self.root/'geometry.png';fixture(self.input)
        self.project=self.root/'work'
        self.palette=self.root/'palette.json';self.palette.write_text(json.dumps({'name':'TEST-GEOMETRY','source':'self-created test fixture','license':'MIT','colors':[{'code':'W','hex':'#FFFFFF'},{'code':'R','hex':'#FF0000'},{'code':'K','hex':'#000000'},{'code':'G','hex':'#00FF00'}]}))
        w.init_project(NS(project=self.project,input=str(self.input),source='synthetic geometry; not Doubao',request='keep shapes',preserve=['small green square'],simulated=True))
    def s(self):return load(self.project)
    def r(self):return current(self.s())
    def confirm(self,stage):return w.confirm(NS(project=self.project,revision=self.r()['revision_id'],stage=stage,message=f'SIMULATED user confirms {stage} for test'))
    def pixel(self,**kw):
        args=dict(project=self.project,base=self.r()['revision_id'],width=78,height=78,max_colors=4,palette=str(self.palette),reserve=['G'],sampling='nearest',input=None,operation=None,based_on_sha=None);args.update(kw)
        return w.pixel(NS(**args))
    def to_pixel(self):self.confirm('edit');self.pixel()
    def to_png(self,confirmed=True):
        self.to_pixel();self.confirm('pixel');w.attach(NS(project=self.project,revision=self.r()['revision_id']),'pattern')
        if confirmed:self.confirm('png')
    def export(self,fmt,**kw):
        args=dict(project=self.project,revision=self.r()['revision_id'],spare_percent=0,cell_pt=18);args.update(kw);return w.attach(NS(**args),fmt)
    def grid(self):return json.loads(checked_file(self.project,self.r()['files']['grid']).read_text())
    def begin(self):return w.begin(NS(project=self.project,base=self.r()['revision_id'],kind='edit',request='smaller accessory; preserve existing shapes',preserve=[]))
    def edit(self,o,**kw):
        args=dict(project=self.project,operation=o['operation_id'],input=None,based_on_sha=None,origin=None,crop=[0,0,140,140],remove_edge=None,tolerance=12);args.update(kw);return w.edit(NS(**args))

    def test_exact_grid_dimensions_and_padding(self):
        self.confirm('edit')
        for width,height in [(78,78),(31,17),(17,41),(1,1)]:
            self.pixel(width=width,height=height)
            g=self.grid();self.assertEqual((len(g['cells'][0]),len(g['cells'])),(width,height));self.assertEqual(g['processing']['fit'],'contain')
            self.assertEqual(g['processing']['crop'],None)
    def test_white_empty_color_cap_and_small_accent(self):
        self.to_pixel();g=self.grid();flat=[c for row in g['cells'] for c in row]
        self.assertIn(None,flat);self.assertIn('W',flat);self.assertIn('G',flat);self.assertLessEqual(len(set(flat)-{None}),4)
        self.assertEqual(flat.count('G'),4) # no blanket tiny-region removal
        with Image.open(checked_file(self.project,self.r()['files']['preview'])) as im:
            self.assertNotEqual(im.getpixel((1,1)),(255,255,255))
    def test_pixel_only_has_preview_and_internal_grid(self):
        self.to_pixel();files=[p.name for p in self.project.rglob('*') if p.is_file()]
        self.assertNotIn('pattern.png',files);self.assertNotIn('bom.csv',files);self.assertFalse(any(f.endswith('.pdf') for f in files))
    def test_confirmations_required_at_every_stage(self):
        with self.assertRaisesRegex(WorkflowError,'EDIT_NOT_CONFIRMED'):self.pixel()
        self.to_pixel()
        with self.assertRaisesRegex(WorkflowError,'PIXEL_NOT_CONFIRMED'):w.attach(NS(project=self.project,revision=self.r()['revision_id']),'pattern')
        for fmt in ['csv','pdf']:
            with self.assertRaisesRegex(WorkflowError,'PNG_NOT_CONFIRMED'):self.export(fmt)
        self.confirm('pixel');w.attach(NS(project=self.project,revision=self.r()['revision_id']),'pattern')
        self.assertEqual(self.s()['stage'],'PNG_PENDING_CONFIRMATION')
        for fmt in ['csv','pdf']:
            with self.assertRaisesRegex(WorkflowError,'PNG_NOT_CONFIRMED'):self.export(fmt)
    def test_csv_counts_independent_and_no_pdf(self):
        self.to_png();g=self.grid();result=self.export('csv',spare_percent=10)
        expected={}
        for row in g['cells']:
            for code in row:
                if code is not None:expected[code]=expected.get(code,0)+1
        with open(result['file'],encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
        self.assertEqual({r['色号']:int(r['用量（颗）']) for r in rows},expected)
        self.assertTrue(all(int(r['建议备损（颗）'])>0 for r in rows));self.assertFalse(list(self.project.rglob('*.pdf')))
        with Image.open(checked_file(self.project,self.r()['files']['pattern'])) as im:self.assertEqual(json.loads(im.info['counts']),expected)
    def test_pdf_only_vectors_full_render_and_same_grid(self):
        self.to_png();result=self.export('pdf');g=self.grid();r=self.r();reader=PdfReader(result['file'])
        self.assertFalse(list(self.project.rglob('*.csv')));pdf_check(g,result['file'],r['revision_id'],18,True)
        self.assertEqual(reader.metadata.subject,'grid_sha256='+r['grid_sha256'])
        self.assertTrue(all(not p.images for p in reader.pages)) # no PNG recognition/embedding
        for kind in ['preview','pattern']:png_check(g,checked_file(self.project,r['files'][kind]),r['revision_id'],kind=='pattern')
    def test_pdf_failure_preserves_state_and_existing_products(self):
        self.to_png();result=self.export('csv');before=(self.project/'state.json').read_bytes();csv_bytes=Path(result['file']).read_bytes()
        with patch('pindou.workflow.pdf_render',side_effect=OSError('simulated disk/render failure')):
            with self.assertRaisesRegex(OSError,'simulated'):self.export('pdf')
        self.assertEqual((self.project/'state.json').read_bytes(),before);self.assertEqual(Path(result['file']).read_bytes(),csv_bytes)
        w.validate(NS(project=self.project))
    def test_reuse_and_pdf_layout_independent(self):
        self.to_png();first=self.export('pdf');stamp=Path(first['file']).stat().st_mtime_ns
        second=self.export('pdf');self.assertTrue(second['reused']);self.assertEqual(Path(second['file']).stat().st_mtime_ns,stamp)
        original_sha=self.r()['grid_sha256'];alternate=self.export('pdf',cell_pt=20)
        self.assertNotEqual(first['file'],alternate['file']);self.assertTrue(Path(first['file']).exists());self.assertEqual(self.r()['grid_sha256'],original_sha);self.assertEqual(self.s()['stage'],'PNG_CONFIRMED')
    def test_change_invalidates_and_rollback_restores_actual_files(self):
        self.to_png();old=self.r()['revision_id'];oldfile=checked_file(self.project,self.r()['files']['pattern']);data=oldfile.read_bytes()
        self.pixel(max_colors=2,reserve=[]);new=self.r()['revision_id'];self.assertNotEqual(old,new)
        with self.assertRaisesRegex(WorkflowError,'PNG_NOT_CONFIRMED'):self.export('csv')
        self.assertEqual(oldfile.read_bytes(),data)
        w.rollback(NS(project=self.project,revision=old));self.assertEqual(self.s()['stage'],'PNG_CONFIRMED');self.assertEqual(checked_file(self.project,self.r()['files']['pattern']).read_bytes(),data);self.export('csv')
    def test_stale_confirmation_rejected(self):
        self.to_pixel();old=self.r()['revision_id'];self.pixel(max_colors=2,reserve=[])
        with self.assertRaisesRegex(WorkflowError,'CONFIRMATION_STALE'):w.confirm(NS(project=self.project,revision=old,stage='pixel',message='yes'))
    def test_corrupt_and_missing_files_rejected(self):
        self.to_png();p=checked_file(self.project,self.r()['files']['pattern']);p.write_bytes(b'not a PNG')
        with self.assertRaisesRegex(WorkflowError,'CORRUPT_FILE'):self.export('pdf')
        p.unlink()
        with self.assertRaisesRegex(WorkflowError,'MISSING_FILE'):w.rollback(NS(project=self.project,revision=self.r()['revision_id']))
    def test_invalid_input_params_palette_and_crop(self):
        self.confirm('edit')
        for kw in [dict(width=0),dict(height=193),dict(max_colors=0),dict(reserve=['FAKE'])]:
            with self.assertRaises(WorkflowError):self.pixel(**kw)
        with self.assertRaisesRegex(WorkflowError,'CROP_OUT_OF_BOUNDS'):crop_image(Image.new('RGB',(1440,1920)),[0,640,1440,1440])
        self.assertEqual(crop_image(Image.new('RGB',(1440,1920)),[0,480,1440,1440]).size,(1440,1440))
        self.palette.write_text('{broken')
        with self.assertRaisesRegex(WorkflowError,'INVALID_JSON'):palette_load(self.palette)
    def test_edge_background_preserves_enclosed_white(self):
        im=Image.new('RGBA',(32,32),'white');d=ImageDraw.Draw(im);d.rectangle((5,5,26,26),fill='black');d.rectangle((9,9,22,22),fill='white');im.save(self.input)
        o=self.begin();self.edit(o,input=str(self.input),based_on_sha=o['source_sha256'],origin='manual',crop=None,remove_edge='#FFFFFF',tolerance=0)
        with Image.open(checked_file(self.project,self.r()['files']['candidate'])) as result:
            self.assertEqual(result.getpixel((0,0))[3],0);self.assertEqual(result.getpixel((12,12)),(255,255,255,255))
    def test_edit_preserves_old_candidate_and_exact_source_binding(self):
        old=self.r()['revision_id'];o=self.begin();self.edit(o);self.assertTrue((self.project/'revisions'/old/'candidate.png').exists())
        self.assertEqual(self.s()['stage'],'EDIT_PENDING_CONFIRMATION')
        o=self.begin()
        with self.assertRaisesRegex(WorkflowError,'SOURCE_MISMATCH'):self.edit(o,input=str(self.input),origin='manual',based_on_sha='wrong')
    def test_one_call_and_simulated_import(self):
        o=self.begin();args=NS(project=self.project,operation=o['operation_id'],mode='simulated');w.claim_call(args)
        with self.assertRaisesRegex(WorkflowError,'CALL_LIMIT'):w.claim_call(args)
        self.edit(o,input=str(self.input),origin='simulated',based_on_sha=o['source_sha256']);self.assertEqual(self.r()['generative_calls'],1);self.assertTrue(self.r()['input']['simulation'])
    def test_simulated_pixel_simplification_is_converted_to_real_grid(self):
        self.confirm('edit')
        o=w.begin(NS(project=self.project,base=self.r()['revision_id'],kind='pixel',request='SIMULATED simplify',preserve=[]))
        w.claim_call(NS(project=self.project,operation=o['operation_id'],mode='simulated'))
        self.pixel(input=str(self.input),operation=o['operation_id'],based_on_sha=o['source_sha256'])
        self.assertEqual(self.r()['generative_calls'],1);self.assertTrue(self.r()['input']['simulation'])
        self.assertEqual((self.grid()['width'],self.grid()['height']),(78,78))
        self.assertEqual(self.s()['stage'],'PIXEL_PENDING_CONFIRMATION')

    def test_cancelled_late_result_and_aba(self):
        o=self.begin();w.cancel(NS(project=self.project,operation=o['operation_id']))
        with self.assertRaisesRegex(WorkflowError,'OPERATION_STALE'):self.edit(o)
        o=self.begin();old=self.r()['revision_id'];w.rollback(NS(project=self.project,revision=old))
        with self.assertRaisesRegex(WorkflowError,'OPERATION_STALE'):self.edit(o)
    def test_race_result_cannot_override_new_selection(self):
        self.confirm('edit');old=self.r()['revision_id'];real=w.preview
        def changed(*args,**kw):
            real(*args,**kw);w.rollback(NS(project=self.project,revision=old))
        with patch('pindou.workflow.preview',side_effect=changed):
            with self.assertRaisesRegex(WorkflowError,'STALE_RESULT'):self.pixel()
        self.assertEqual(self.s()['current_revision'],old)
    def test_preview_fallback_is_bounded(self):
        a=NS(project=self.project,revision=self.r()['revision_id'],outcome='fail')
        one=w.preview_result(a);self.assertTrue(Path(one['fallback']).is_file());two=w.preview_result(a);self.assertTrue(two['stop']);self.assertEqual(two['visual_check'],'incomplete')
        with self.assertRaisesRegex(WorkflowError,'PREVIEW_STOP'):w.preview_result(a)
    def test_known_ciede2000_reference(self):
        actual=ciede2000(np.array([[50,2.6772,-79.7751]]),np.array([[50,0,-82.7485]]))[0,0]
        self.assertAlmostEqual(actual,2.0425,places=4)
    def test_78x78_mard_18_and_12_color_recolor_no_ai(self):
        self.confirm('edit');self.pixel(palette=None,max_colors=18,reserve=[])
        self.assertLessEqual(len(grid_check(self.grid())),18);source=checked_file(self.project,self.r()['files']['source']).read_bytes()
        self.pixel(palette=None,max_colors=12,reserve=[]);self.assertEqual(self.r()['generative_calls'],0);self.assertLessEqual(len(grid_check(self.grid())),12)
        self.assertEqual(checked_file(self.project,self.r()['files']['source']).read_bytes(),source)
    def test_delivery_distinguishes_success_slow_and_unqualified(self):
        base=dict(project=self.project,revision=self.r()['revision_id'],artifact='candidate',scope='local-observation',submitted_at=time.time()-65,delivered_at=time.time(),quality='qualified',evidence='synthetic test only')
        self.assertEqual(w.delivery(NS(**base))['result'],'slow');base['submitted_at']=time.time()-1;self.assertEqual(w.delivery(NS(**base))['result'],'pass')
        base['quality']='unqualified';self.assertEqual(w.delivery(NS(**base))['result'],'not-qualified')

class SupervisorTests(unittest.TestCase):
    def test_missing_dependencies_clear_error_no_install(self):
        p=subprocess.run([sys.executable,'-S',str(ROOT/'scripts/pindou.py'),'doctor'],capture_output=True,text=True)
        self.assertEqual(p.returncode,2);self.assertIn('missing',p.stdout)
    def test_timeout_kills_owned_child_and_grandchild(self):
        with tempfile.TemporaryDirectory() as d:
            marker=Path(d)/'late.txt'
            grandchild=f'import time;from pathlib import Path;time.sleep(0.8);Path({str(marker)!r}).write_text("late")'
            child=f'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",{grandchild!r}]);time.sleep(5)'
            start=time.monotonic();code,_,err=run_bounded([sys.executable,'-c',child],.2)
            self.assertEqual(code,124);self.assertLess(time.monotonic()-start,1);self.assertIn('terminated',err)
            time.sleep(.9);self.assertFalse(marker.exists())
    def test_cli_timeout_and_shared_submission_budget(self):
        with tempfile.TemporaryDirectory() as d:
            for opts in [ ['--budget-seconds','0.001'],['--submitted-at',str(time.time()-61)]]:
                p=subprocess.run([sys.executable,str(ROOT/'scripts/pindou.py'),*opts,'init','--project',str(Path(d)/'p'),'--input','unused.png','--source','test'],capture_output=True,text=True)
                self.assertEqual(p.returncode,124,p.stdout);self.assertFalse(json.loads(p.stdout)['ok']);self.assertFalse((Path(d)/'p/state.json').exists())
    def test_invalid_image_cli_error_and_log(self):
        with tempfile.TemporaryDirectory() as d:
            image=Path(d)/'broken.png';image.write_text('broken')
            p=subprocess.run([sys.executable,str(ROOT/'scripts/pindou.py'),'init','--project',str(Path(d)/'p'),'--input',str(image),'--source','synthetic'],capture_output=True,text=True)
            self.assertEqual(p.returncode,2);self.assertIn('INVALID_IMAGE',p.stdout)

if __name__=='__main__':unittest.main(verbosity=2)
