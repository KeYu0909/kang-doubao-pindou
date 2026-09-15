import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import install_record
from pindou.environment import temporary_path,storage_status


class InstallationTests(unittest.TestCase):
    def test_temporary_locations_and_boundary(self):
        self.assertTrue(temporary_path('/runtime/skill'))
        self.assertTrue(temporary_path('/tmp/skill'))
        self.assertFalse(temporary_path('/runtime-backup/skill'))

    def test_symlink_target_is_checked(self):
        with tempfile.TemporaryDirectory() as d:
            link=Path(d)/'entry';link.symlink_to('/runtime/skill')
            self.assertTrue(temporary_path(link))

    def test_non_temporary_path_is_not_proof_of_persistence(self):
        status=storage_status('/opt/pindou','/opt/pindou/.venv')
        self.assertEqual(status['code'],'PERSISTENCE_UNVERIFIED')
        self.assertFalse(status['cross_session_verified'])

    def test_temporary_record_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'临时目录'):
                install_record.record(d,'test claim')
            self.assertFalse((Path(d)/install_record.NAME).exists())

    def test_record_survives_new_reader_without_claiming_registration(self):
        with tempfile.TemporaryDirectory() as d:
            project=Path(d)/'project';skill=Path(d)/'skill';env=skill/'.venv'
            # Model host-confirmed storage; temporary paths are independently tested above.
            with patch.object(install_record,'ROOT',skill),patch.object(install_record,'temporary_path',return_value=False),patch.object(install_record,'storage_status',return_value={'temporary':[]}),patch.object(sys,'prefix',str(env)),patch.object(sys,'executable',str(env/'bin/python')),patch.object(install_record,'probe',return_value={'ok':True}):
                first=install_record.record(project,'synthetic host: same project')
                again=install_record.record(project,'synthetic host: same project')
                self.assertEqual(first['record'],again['record'])
                result=install_record.check(project/install_record.NAME)
                self.assertEqual(result['code'],'REACHABLE_NOW')
                self.assertFalse(result['installation']['cross_session_verified'])
                self.assertEqual(result['installation']['host_registration'],'unverified')
                with patch.object(sys,'executable',str(env/'bin/python-other')):
                    with self.assertRaisesRegex(ValueError,'其他安装记录'):
                        install_record.record(project,'new claim')
                self.assertEqual(json.loads((project/install_record.NAME).read_text())['python_path'],first['python_path'])

    def test_missing_install_reports_restore_without_recreating_work(self):
        with tempfile.TemporaryDirectory() as d:
            project=Path(d);path=project/install_record.NAME
            path.write_text(json.dumps({'schema':1,'project_path':d,'skill_path':str(project/'missing'),'python_path':str(project/'missing/python')}))
            with self.assertRaisesRegex(ValueError,'技能文件已不可用'):
                install_record.check(path)
            self.assertFalse((project/'missing').exists())

    def test_relative_record_path_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/install_record.NAME
            path.write_text(json.dumps({'schema':1,'skill_path':'relative'}))
            with self.assertRaisesRegex(ValueError,'绝对路径'):
                install_record.check(path)
