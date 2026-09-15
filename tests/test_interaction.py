import json,time,unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import test_workflow as base
from pindou import workflow as w, interaction as it
from pindou.common import load, current, WorkflowError

class InteractionTests(unittest.TestCase):
    setUp=base.WorkflowTests.setUp
    s=base.WorkflowTests.s;r=base.WorkflowTests.r
    confirm=base.WorkflowTests.confirm;pixel=base.WorkflowTests.pixel
    to_pixel=base.WorkflowTests.to_pixel;to_png=base.WorkflowTests.to_png
    export=base.WorkflowTests.export;grid=base.WorkflowTests.grid
    def present(self,artifact='pattern',ambiguous=False,conversation='test-session'):
        return it.present(NS(project=self.project,revision=self.r()['revision_id'],conversation=conversation,artifact=artifact,message_ref='SIMULATED visible delivery',ambiguous=ambiguous))
    def route(self,msg,**kw):
        args=dict(project=self.project,conversation='test-session',message=msg,message_ref='synthetic-user-'+msg,revision=None,layout=None);args.update(kw);return it.route(NS(**args))
    def test_export_intent_confirms_visible_png_and_pdf_only(self):
        self.to_png(False);self.present();out=self.route('导出pdf')
        self.assertEqual(out['status'],'file_ready');self.assertTrue(out['file'].endswith('.pdf'));self.assertFalse(list(self.project.rglob('*.csv')))
        c=self.r()['confirmations']['png'];self.assertEqual(c['source'],'contextual_export');self.assertEqual(c['project_id'],self.s()['project_id']);self.assertEqual(c['artifact_sha256'],self.r()['files']['pattern']['sha256']);self.assertIn('intent',out['timings'])
    def test_print_version_and_csv_natural_expression(self):
        self.to_png(False);self.present();out=self.route('这张可以，下载用量清单');self.assertTrue(out['file'].endswith('.csv'));self.assertFalse(list(self.project.rglob('*.pdf')))
        self.assertEqual(self.route('给我打印版')['status'],'file_ready')
    def test_plain_ok_confirms_png_without_guessing_export(self):
        self.to_png(False);self.present();out=self.route('可以');self.assertEqual(out['status'],'confirmed');self.assertEqual(self.r()['confirmations']['png']['source'],'explicit');self.assertFalse(list(self.project.rglob('*.pdf')))
    def test_negative_future_question_analysis_do_not_mutate(self):
        self.to_png(False);self.present();before=(self.project/'state.json').read_bytes()
        for msg in ['先不要导出PDF','不要导出','以后再导出PDF','PDF和PNG有什么区别','只分析，不生成图片','PDF有什么用','能导出PDF吗','如果导出PDF会怎么样']:
            self.assertIn(self.route(msg)['status'],('no_action','explanation'));self.assertEqual((self.project/'state.json').read_bytes(),before)
        self.assertFalse(list(self.project.rglob('*.pdf')))
    def test_unpresented_and_other_conversation_cannot_auto_confirm(self):
        self.to_png(False);out=self.route('导出pdf',revision=self.r()['revision_id']);self.assertEqual(out['status'],'needs_presentation')
        self.present();self.assertEqual(self.route('导出pdf',conversation='another',revision=self.r()['revision_id'])['status'],'needs_presentation');self.assertNotIn('png',self.r()['confirmations'])
    def test_pending_modification_blocks_following_export(self):
        self.to_png(False);self.present();self.assertEqual(self.route('眼睛改绿色后再导出')['status'],'modification_required')
        self.assertEqual(self.route('导出pdf')['status'],'modification_required');self.assertNotIn('png',self.r()['confirmations'])
        self.pixel(max_colors=2,reserve=[]);self.assertNotIn('pending_modification',self.s());self.assertFalse(self.r()['confirmations'])
        self.assertEqual(self.route('导出pdf')['status'],'needs_input')
    def test_pixel_not_confirmed_does_not_make_png_or_pdf(self):
        self.to_pixel();self.present('preview');self.assertEqual(self.route('导出pdf')['status'],'needs_input');self.assertFalse(list(self.project.rglob('pattern.png')))
    def test_pixel_confirmed_generates_only_png_then_requires_presentation(self):
        self.to_pixel();self.confirm('pixel');self.present('preview');out=self.route('导出pdf')
        self.assertEqual(out['status'],'png_needs_presentation');self.assertTrue(out['file'].endswith('.png'));self.assertFalse(list(self.project.rglob('*.pdf')))
        self.assertEqual(self.route('导出pdf')['status'],'needs_presentation')
        self.present();self.assertEqual(self.route('导出pdf')['status'],'file_ready')
    def test_ambiguous_versions_asks_one_version_question(self):
        self.to_png(False);self.present(ambiguous=True);out=self.route('导出pdf');self.assertEqual(out['status'],'needs_input');self.assertEqual(list(k for k in out if k=='question'),['question'])
    def test_previous_version_uses_real_history_without_reselecting_current(self):
        self.to_png(False);self.present();old=self.r()['revision_id'];oldsha=self.r()['grid_sha256']
        self.pixel(max_colors=2,reserve=[]);self.confirm('pixel');w.attach(NS(project=self.project,revision=self.r()['revision_id']),'pattern');self.present();new=self.r()['revision_id']
        out=self.route('就用上一版导出PDF');self.assertEqual(out['revision_id'],old);self.assertEqual(out['grid_sha256'],oldsha);self.assertEqual(self.s()['current_revision'],new)
    def menu(self,opts):
        path=self.root/'options.json';path.write_text(json.dumps(opts));return it.offer(NS(project=self.project,revision=self.r()['revision_id'],conversation='test-session',options=path))
    def test_numbers_recommendation_alias_and_stale_menu(self):
        self.to_png(False);self.present();self.menu([{'label':'标准清晰PDF','action':'export_pdf','recommended':True},{'label':'用量清单','action':'export_csv','aliases':['只要清单']}])
        self.assertEqual(self.route('第二个')['kind'],'csv');self.assertEqual(self.route('1')['status'],'needs_input')
        self.menu([{'label':'标准清晰PDF','action':'export_pdf','recommended':True}]);self.assertEqual(self.route('按推荐来')['kind'],'pdf')
        self.menu([{'label':'用量清单','action':'export_csv','aliases':['只要清单']}]);self.assertEqual(self.route('只要清单')['kind'],'csv')
    def test_ok_uses_only_current_explicit_continue_context(self):
        self.present('candidate');self.menu([{'label':'继续像素预览','action':'pixel','recommended':True,'args':{'width':31,'height':17,'max_colors':4,'palette':str(self.palette)}},{'label':'调整原图','action':'adjust'}])
        out=self.route('可以');self.assertEqual(out['parameters']['width'],31);self.assertEqual(out['parameters']['height'],17);self.assertFalse(list(self.project.rglob('pattern.png')))
        self.present('preview');self.menu([{'label':'继续生成PNG','action':'png','recommended':True},{'label':'调整像素图','action':'adjust'}]);self.assertEqual(self.route('可以')['kind'],'pattern');self.assertFalse(list(self.project.rglob('*.pdf')))
    def test_pdf_template_cache_and_layout_preferences(self):
        self.to_png(False);self.present();first=self.route('导出PDF');self.assertEqual(first['layout_plan']['layout'],'standard')
        with patch('pindou.workflow.pdf_render',side_effect=AssertionError('must reuse')):
            self.assertTrue(self.route('导出PDF')['reused'])
        bigger=self.route('PDF字号大一点，图案不改');self.assertEqual(bigger['layout_plan']['layout'],'large');self.assertTrue(self.route('导出PDF')['reused'])
        self.assertEqual(self.route('页数少一点')['layout_plan']['layout'],'standard')
        with patch('pindou.workflow.TEMPLATE_VERSION','changed-template'):
            changed=self.route('导出PDF');self.assertFalse(changed['reused']);self.assertNotEqual(changed['file'],first['file'])
    def test_legacy_state_confirmation_remains_readable(self):
        self.to_png(True);s=self.s();r=current(s);r['confirmations']['png'].pop('project_id',None);r['confirmations']['png'].pop('source',None)
        from pindou.common import save
        save(self.project,s);self.assertTrue(self.export('csv')['file'].endswith('.csv'));self.present();self.assertEqual(self.route('导出pdf')['status'],'file_ready')
    def test_inspect_counts_are_calculated(self):
        self.to_pixel();out=it.inspect(NS(project=self.project));g=self.grid();self.assertEqual(out['nonempty_cells'],sum(c is not None for row in g['cells'] for c in row));self.assertEqual(out['used_colors'],len({c for row in g['cells'] for c in row if c}))

    def test_modification_takes_priority_over_large_pdf(self):
        self.to_png(False);self.present()
        self.assertEqual(self.route('眼睛改绿色后给我大字PDF')['status'],'modification_required')
        self.assertNotIn('png',self.r()['confirmations'])

    def test_rollback_resolves_pending_modification(self):
        self.to_png(False);self.present();old=self.r()['revision_id']
        self.pixel(max_colors=2,reserve=[]);self.present('preview')
        self.route('眼睛改绿色')
        self.assertEqual(self.route('还是上一版')['status'],'restored')
        self.assertEqual(self.r()['revision_id'],old);self.assertNotIn('pending_modification',self.s())

    def test_png_label_refresh_preserves_original_and_requires_new_presentation(self):
        from pindou.common import save,checked_file
        self.to_png(True);s=self.s();r=current(s)
        old_path=checked_file(self.project,r['files']['pattern'])
        from PIL import Image,ImageDraw
        from pindou.render import meta
        from pindou.common import sha_file
        with Image.open(old_path) as im:
            ImageDraw.Draw(im).rectangle((64,16,600,38),fill='white');im.save(old_path,pnginfo=meta(self.grid(),r['revision_id']))
        old_bytes=old_path.read_bytes();r['files']['pattern']['sha256']=sha_file(old_path)
        r['confirmations']['png']['artifact_sha256']=r['files']['pattern']['sha256']
        r['files']['pattern']['params']={};save(self.project,s);self.present()
        out=w.attach(NS(project=self.project,revision=r['revision_id']),'pattern')
        self.assertFalse(out['reused']);self.assertNotEqual(out['file'],str(old_path));self.assertEqual(old_path.read_bytes(),old_bytes)
        self.assertTrue(self.r()['confirmation_history']);self.assertNotIn('png',self.r()['confirmations'])
        self.assertEqual(self.route('导出pdf')['status'],'needs_presentation')
        self.present();self.assertEqual(self.route('导出pdf')['status'],'file_ready')

if __name__=='__main__':unittest.main()
