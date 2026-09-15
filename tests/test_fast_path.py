import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import test_workflow as base
from pindou import cleanup as c, workflow as w, interaction as it
from pindou.common import WorkflowError, checked_file, current, load
from pindou.cli import parser, worker
from pindou.environment import doctor, selected_lock
from pindou.imaging import grid_hash, grid_check
from pindou.render import png_check, csv_check, pdf_check


def noise_grid():
    g={'schema_version':1,'width':20,'height':20,'max_colors':6,
       'palette':{'name':'SYNTHETIC','source':'test fixture','license':'MIT','colors':[
           {'code':code,'hex':color} for code,color in [('A','#B0B0B0'),('B','#B4B4B4'),('C','#B8B8B8'),('D','#C0C0C0'),('K','#000000'),('G','#008800')]]},
       'cells':[[None if x in (0,19) or y in (0,19) else 'A' for x in range(20)] for y in range(20)],'processing':{}}
    for x,y,code in [(4,4,'B'),(10,4,'C'),(11,4,'C'),(6,10,'D'),(7,10,'D'),(8,10,'D'),(12,12,'K'),(15,15,'G')]:g['cells'][y][x]=code
    return g


class CleanupTests(unittest.TestCase):
    def test_components_exact_four_connectivity(self):
        g=noise_grid();s=c.stats(g)
        self.assertEqual((s['components'],s['singletons'],s['doubletons'],s['small_3_5']),(6,3,1,1))
        self.assertEqual(s['nonempty_cells'],18*18)
        g['cells'][5][5]='B';self.assertEqual(c.stats(g)['components'],7) # diagonal does not join
    def test_light_only_obvious_islands(self):
        out,r=c.clean(noise_grid());self.assertEqual(r['changed_cells'],3)
        self.assertEqual(out['cells'][10][6],'D');self.assertEqual(out['cells'][4][4],'A')
    def test_explicit_cell_protects_entire_component(self):
        out,r=c.clean(noise_grid(),extra={'cells':[[11,5]]})
        self.assertEqual(out['cells'][4][10:12],['C','C']);self.assertEqual(r['changed_cells'],1)
    def test_color_and_region_protection(self):
        out,r=c.clean(noise_grid(),mode='balanced',extra={'codes':['B'],'regions':[[7,11,9,11]],'labels':['眼睛']})
        self.assertEqual(out['cells'][4][4],'B');self.assertEqual(out['cells'][10][6:9],['D']*3)
        self.assertEqual(r['changed_cells'],2)
    def test_high_contrast_and_dark_outline(self):
        out,_=c.clean(noise_grid(),mode='balanced');self.assertEqual(out['cells'][12][12],'K');self.assertEqual(out['cells'][15][15],'G')
    def test_silhouette_decoration_not_deleted(self):
        g=noise_grid();g['cells'][0][5]='B';out,_=c.clean(g,mode='balanced');self.assertEqual(out['cells'][0][5],'B')
    def test_balanced_reduces_small_regions(self):
        out,r=c.clean(noise_grid(),'balanced');self.assertEqual(r['changed_cells'],6)
        self.assertLess(r['after']['small_1_5'],r['before']['small_1_5'])
    def test_strong_reduces_colours_with_explicit_cap(self):
        out,r=c.clean(noise_grid(),'strong',3);self.assertEqual(len(grid_check(out)),3)
        self.assertLess(r['after']['used_colors'],r['before']['used_colors'])
        for point in [(12,12),(15,15)]:self.assertEqual(out['cells'][point[1]][point[0]],noise_grid()['cells'][point[1]][point[0]])
    def test_strong_does_not_silently_override_protection(self):
        with self.assertRaisesRegex(WorkflowError,'PROTECTION_COLOR_CONFLICT'):c.clean(noise_grid(),'strong',2)
        with self.assertRaisesRegex(WorkflowError,'TARGET_COLORS_REQUIRED'):c.clean(noise_grid(),'strong')
    def test_shape_empty_cells_and_input_immutable(self):
        g=noise_grid();before=deepcopy(g)
        for mode,cap in [('light',None),('balanced',None),('strong',3)]:
            out,r=c.clean(g,mode,cap);self.assertEqual(g,before)
            self.assertEqual(len(out['cells'])*len(out['cells'][0]),400)
            self.assertEqual([[v is None for v in row] for row in g['cells']],[[v is None for v in row] for row in out['cells']])
            self.assertEqual(r['changed_cells'],sum(a!=b for ra,rb in zip(g['cells'],out['cells']) for a,b in zip(ra,rb)))
    def test_analysis_estimates_match_light_actual(self):
        g=noise_grid();a=c.analyze(g);out,r=c.clean(g)
        self.assertEqual(a['estimate']['changed_cells'],r['changed_cells'])
        self.assertEqual(a['estimate']['small_1_5_after'],r['after']['small_1_5'])
        self.assertTrue(any(region['neighbours'] for region in a['small_regions']))
    def test_no_candidates_recommends_keep(self):
        g=noise_grid();g['protection']={'codes':['A','B','C','D','K','G']}
        self.assertEqual(c.analyze(g)['recommendation'],'keep')
    def test_invalid_protection_coordinates_rejected(self):
        for spec in ({'cells':[[0,1]]},{'regions':[[1,1,99,99]]},{'codes':['UNKNOWN']}):
            with self.assertRaises(WorkflowError):c.clean(noise_grid(),extra=spec)
    def test_recolor_preserves_cleaned_grid_not_original_source(self):
        g,_=c.clean(noise_grid(),'balanced');out=c.reduce_colors(g,6)
        self.assertEqual(g['cells'],out['cells']);self.assertEqual(out['cells'][4][4],'A')

    def test_recorded_feature_colours_protect_matching_shades(self):
        spec=c.feature_colors(noise_grid(),['保留绿色眼睛和黑色轮廓'])
        self.assertEqual(set(spec['codes']),{'G','K'})



class FastWorkflowTests(unittest.TestCase):
    setUp=base.WorkflowTests.setUp
    s=base.WorkflowTests.s;r=base.WorkflowTests.r;grid=base.WorkflowTests.grid
    confirm=base.WorkflowTests.confirm;pixel=base.WorkflowTests.pixel;to_pixel=base.WorkflowTests.to_pixel;to_png=base.WorkflowTests.to_png
    def call(self,command,*args):
        return worker(parser().parse_args([command,'--project',str(self.project),*args]))
    def show(self,artifact):return self.call('present','--current','--conversation','test','--artifact',artifact,'--message-ref','SIMULATED shown '+artifact)
    def route(self,text):return self.call('route','--current','--conversation','test','--message',text,'--message-ref','SIMULATED user '+text)
    def clean(self):return self.call('denoise','--current','--mode','light')
    def test_current_without_revision_and_embedded_confirmation_check(self):
        with self.assertRaisesRegex(WorkflowError,'EDIT_NOT_CONFIRMED'):self.call('pixel','--current')
        self.call('confirm','--current','--stage','edit','--message','SIMULATED yes')
        out=self.call('pixel','--current','--width','78','--height','78','--max-colors','18')
        self.assertEqual((out['analysis']['width'],out['analysis']['height']),(78,78))
        self.assertTrue(Path(out['files']['analysis']).is_file())
    def test_cleanup_new_revision_invalidates_confirmations(self):
        self.to_png();old=self.r()['revision_id'];oldfile=checked_file(self.project,self.r()['files']['pattern']);data=oldfile.read_bytes()
        out=self.clean();self.assertNotEqual(old,out['revision_id']);self.assertFalse(self.r()['confirmations'])
        self.assertEqual(data,oldfile.read_bytes())
        with self.assertRaisesRegex(WorkflowError,'PIXEL_NOT_CONFIRMED'):self.call('png','--current')
    def test_final_png_csv_pdf_identical_grid_and_layout_independent(self):
        self.to_pixel();self.clean();self.show('preview');self.route('生成PNG');self.show('pattern');rev=self.r()['revision_id'];g=self.grid()
        standard=self.route('导出PDF');self.assertFalse(list(self.project.rglob('*.csv')))
        large=self.route('PDF字大一点');csv=self.route('下载清单')
        for result in (standard,large,csv):self.assertEqual(result['grid_sha256'],grid_hash(g));self.assertEqual(result['revision_id'],rev)
        png_check(g,checked_file(self.project,self.r()['files']['pattern']),rev,True)
        csv_check(g,csv['file'],rev)
        for result,layout in [(standard,'standard'),(large,'large')]:pdf_check(g,result['file'],rev,None,True,layout)
    def test_direct_denoise_no_ai_and_no_requantization(self):
        self.to_pixel();self.show('preview')
        with patch('pindou.workflow.grid_build',side_effect=AssertionError('must not quantize')),patch('pindou.workflow.claim_call',side_effect=AssertionError('must not generate')):
            out=self.route('轻度去杂色');self.assertEqual(out['status'],'file_ready');self.assertEqual(self.r()['generative_calls'],0)
    def test_recolor_fast_path_no_source_read_or_ai(self):
        self.to_pixel();self.show('preview')
        with patch('pindou.workflow.open_image',side_effect=AssertionError('must use grid')),patch('pindou.workflow.grid_build',side_effect=AssertionError('must use grid')):
            out=self.route('颜色减到4色');self.assertEqual(out['parameters']['max_colors'],4)
    def test_current_operation_claim_import_and_cancel(self):
        op=self.call('begin','--current','--kind','edit','--request','test single call')
        with self.assertRaisesRegex(WorkflowError,'MODIFICATION_PENDING'):self.call('begin','--current','--kind','edit','--request','duplicate')
        self.call('claim-call','--current','--mode','simulated')
        with self.assertRaisesRegex(WorkflowError,'CALL_LIMIT'):self.call('claim-call','--current','--mode','simulated')
        self.call('edit','--current','--input',str(self.input),'--origin','simulated','--based-on-sha',op['source_sha256'])
        self.call('begin','--current','--kind','edit','--request','cancel this')
        self.assertEqual(self.call('cancel','--current')['status'],'cancelled')
    def test_pending_operations_block_current(self):
        self.call('begin','--current','--kind','edit','--request','SIMULATED edit')
        with self.assertRaisesRegex(WorkflowError,'MODIFICATION_PENDING'):self.call('confirm','--current','--stage','edit','--message','SIMULATED yes')
    def test_previous_real_revision_restored(self):
        self.to_pixel();old=self.r()['revision_id'];g=self.grid();self.show('preview');self.route('轻度去杂色');self.show('preview')
        result=self.route('还是上一版');self.assertEqual(result['revision_id'],old);self.assertEqual(self.grid(),g)
    def test_four_option_menu_and_no_automatic_strong_target(self):
        self.to_pixel();self.show('preview');options=c.analyze(self.grid())['options'];path=self.root/'cleanup-menu.json';path.write_text(json.dumps(options))
        self.call('offer','--current','--conversation','test','--options',str(path));old=self.r()['revision_id']
        self.assertEqual(self.route('第三个')['status'],'needs_input');self.assertEqual(old,self.r()['revision_id'])
        self.call('offer','--current','--conversation','test','--options',str(path));self.assertEqual(self.route('第四个')['status'],'kept')
        self.assertNotIn('pending_cleanup',self.s()['interaction']['test'])
        self.assertEqual(self.route('12色')['status'],'needs_input')
    def test_unsafe_compound_and_questions_do_not_fast_modify(self):
        for text in ['眼睛改绿后轻度去杂色','去除杂色后加帽子']:
            self.assertEqual(it.classify(text)['action'],'adjust')
        self.assertEqual(it.classify('轻度去杂色会改变什么？')['action'],'explain')
        self.assertEqual(it.classify('去一点杂色'),{'action':'denoise','args':{'mode':'light'}})
        self.assertEqual(it.classify('18色改12色'),{'action':'recolor','args':{'max_colors':12}})
    def test_current_rejects_race_instead_of_mutating_another_revision(self):
        self.to_pixel();self.show('preview');old=self.r()['revision_id'];real=w.preview
        def change(*args,**kwargs):
            real(*args,**kwargs);w.rollback(NS(project=self.project,revision=old))
        with patch('pindou.workflow.preview',side_effect=change):
            with self.assertRaisesRegex(WorkflowError,'STALE_RESULT'):self.clean()
        self.assertEqual(self.r()['revision_id'],old)
    def test_cli_errors_are_machine_readable(self):
        p=subprocess.run([sys.executable,str(base.ROOT/'scripts/pindou.py'),'pixel','--project',str(self.project),'--current'],capture_output=True,text=True)
        out=json.loads(p.stdout);self.assertEqual(p.returncode,2);self.assertEqual(out['code'],'EDIT_NOT_CONFIRMED');self.assertIn('确认',out['message'])
    def test_csv_failure_does_not_destroy_pdf_png(self):
        self.to_png();pdf=self.call('export','--current','--format','pdf');old=Path(pdf['file']).read_bytes()
        with patch('pindou.workflow.csv_render',side_effect=OSError('test failure')):
            with self.assertRaises(OSError):self.call('export','--current','--format','csv')
        self.assertEqual(Path(pdf['file']).read_bytes(),old);self.assertTrue(checked_file(self.project,self.r()['files']['pattern']).is_file())


class RepairTests(unittest.TestCase):
    def test_healthy_repair_never_installs(self):
        with patch('pindou.cli.run_bounded',side_effect=AssertionError('must not install')):
            result=doctor(repair=True);self.assertTrue(result['ok']);self.assertTrue(result['reused']);self.assertEqual(result['actions'],[])
    def test_rebuild_missing_link_reuses_environment_and_refuses_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            link=Path(d)/'runtime/skill';out=doctor(repair=True,link=str(link));self.assertTrue(out['ok']);self.assertTrue(link.is_symlink())
            self.assertEqual(doctor(repair=True,link=str(link))['actions'][0]['action'],'reuse_link')
            conflict=Path(d)/'keep';conflict.write_text('keep')
            self.assertEqual(doctor(repair=True,link=str(conflict))['code'],'LINK_CONFLICT');self.assertEqual(conflict.read_text(),'keep')
    def test_missing_dependency_clear_without_automatic_install(self):
        p=subprocess.run([sys.executable,'-S',str(base.ROOT/'scripts/pindou.py'),'doctor'],capture_output=True,text=True)
        result=json.loads(p.stdout);self.assertEqual(result['code'],'DEPENDENCY_ERROR');self.assertTrue(result['needed']);self.assertEqual(result['actions'],[])
    def test_repair_selects_only_missing_locked_package(self):
        text=selected_lock(base.ROOT,['PyYAML']);self.assertIn('PyYAML==6.0.2',text);self.assertIn('--hash=sha256:',text);self.assertNotIn('numpy==',text)
        good={'ok':True,'needed':[]};bad={'ok':False,'needed':['PyYAML']}
        captured=[]
        def run(cmd,budget):
            captured.append(Path(cmd[-1]).read_text());self.assertIn('--no-deps',cmd);return 0,'',''
        with patch('pindou.environment.check',side_effect=[bad,good]),patch('pindou.cli.run_bounded',side_effect=run):
            result=doctor(repair=True);self.assertTrue(result['ok']);self.assertFalse(result['reused']);self.assertEqual(len(captured),1)

if __name__=='__main__':unittest.main()
