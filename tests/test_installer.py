"""Exercise actual file placement and failure handling in isolated host fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pindou_installer', ROOT / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.source = self.home / 'source'
        self.source.mkdir()
        self.scan = self.home / '.doubao/agent_mode/workspace/.user_skills'
        self.scan.mkdir(parents=True)
        self.target = self.scan / installer.NAME
        self.files = {rel: b'synthetic release\n' for rel in installer.TOP}
        self.files['SKILL.md'] = b'---\nname: kang-doubao-pindou\ndescription: test\n---\n'
        self.files['scripts/pindou.py'] = b'# fixture CLI\n'
        self.files['assets/test.json'] = b'{}\n'
        self.write_release()
        # Fixtures model a host path; real temporary-location rejection is tested separately.
        self.addCleanup(patch.stopall)
        patch.object(installer, 'temporary_location', return_value=False).start()
        patch.object(Path, 'home', return_value=self.home).start()
        self.env = patch.object(installer, 'prepare_environment',
                                side_effect=lambda target: (str(target / '.venv/bin/python'), {'ok': True, 'reused': True})).start()

    def write_release(self):
        for rel, data in self.files.items():
            path = self.source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (self.source / 'MANIFEST.json').write_text(json.dumps(
            {rel: hashlib.sha256(data).hexdigest() for rel, data in self.files.items()}))

    def test_default_placement_real_directory_and_excludes_source_runtime(self):
        (self.source / '.venv').mkdir()
        (self.source / '.venv/private').write_text('do not copy')
        (self.source / 'runs').mkdir()
        (self.source / 'runs/user-photo').write_text('private')
        out = installer.install(self.source)
        self.assertTrue(out['ok'])
        self.assertEqual(out['skill_path'], str(self.target))
        self.assertFalse(self.target.is_symlink())
        self.assertEqual((self.target / 'SKILL.md').read_bytes(), self.files['SKILL.md'])
        self.assertFalse((self.target / '.venv/private').exists())
        self.assertFalse((self.target / 'runs').exists())
        record = json.loads((self.target / 'INSTALLATION.json').read_text())
        self.assertFalse(record['cross_session_verified'])
        self.assertEqual(record['host_registration'], 'unverified')
        self.env.assert_called_once_with(self.target)

    def test_repeat_and_installed_source_are_idempotent(self):
        installer.install(self.source)
        (self.target / '.venv').mkdir()
        (self.target / '.venv/keep').write_text('keep environment')
        second = installer.install(self.source)
        self.assertEqual(second['changed_files'], [])
        self.assertIsNone(second['backup_path'])
        self.assertEqual(installer.install(self.target)['changed_files'], [])
        self.assertEqual((self.target / '.venv/keep').read_text(), 'keep environment')

    def test_update_backs_up_code_outside_scan_preserves_project(self):
        installer.install(self.source)
        (self.target / 'runs').mkdir()
        (self.target / 'runs/state.json').write_text('real previous work')
        self.files['README.md'] = b'updated readme\n'
        self.write_release()
        result = installer.install(self.source)
        backup = Path(result['backup_path'])
        self.assertNotIn(self.scan, backup.parents)
        self.assertEqual((backup / 'README.md').read_bytes(), b'synthetic release\n')
        self.assertEqual((self.target / 'README.md').read_bytes(), b'updated readme\n')
        self.assertEqual((self.target / 'runs/state.json').read_text(), 'real previous work')

    def test_missing_scan_refused_without_mkdir(self):
        scan = self.home / 'absent/.user_skills'
        with self.assertRaises(installer.InstallError) as raised:
            installer.install(self.source, scan)
        self.assertEqual(raised.exception.code, 'SKILLS_DIR_MISSING')
        self.assertFalse(scan.exists())
        self.env.assert_not_called()

    def test_system_and_temporary_scan_refused(self):
        with self.assertRaises(installer.InstallError):
            installer.install(self.source, self.scan.parent / '.skills')
        with patch.object(installer, 'temporary_location', return_value=True):
            with self.assertRaises(installer.InstallError) as raised:
                installer.install(self.source)
            self.assertEqual(raised.exception.code, 'INVALID_SKILLS_DIR')
        self.assertFalse(self.target.exists())

    def test_symlink_target_refused_without_mutation(self):
        self.target.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(installer.InstallError) as raised:
            installer.install(self.source)
        self.assertEqual(raised.exception.code, 'SYMLINK_CONFLICT')
        self.assertTrue(self.target.is_symlink())
        self.env.assert_not_called()

    def test_symlink_file_conflict_is_found_before_any_update(self):
        installer.install(self.source)
        (self.target / 'README.md').unlink()
        (self.target / 'README.md').symlink_to(self.source / 'README.md')
        old = (self.target / 'SKILL.md').read_bytes()
        self.files['SKILL.md'] += b'changed\n'
        self.write_release()
        with self.assertRaises(installer.InstallError):
            installer.install(self.source)
        self.assertEqual((self.target / 'SKILL.md').read_bytes(), old)

    def test_environment_symlink_refused_without_overwrite(self):
        self.target.mkdir()
        (self.target / '.venv').symlink_to(self.home / 'old-env')
        with self.assertRaises(installer.InstallError) as raised:
            installer.install(self.source)
        self.assertEqual(raised.exception.code, 'VENV_LINK_CONFLICT')
        self.assertFalse((self.target / 'SKILL.md').exists())

    def test_bad_hash_and_traversal_rejected_before_copy(self):
        (self.source / 'README.md').write_text('tamper')
        with self.assertRaises(installer.InstallError) as raised:
            installer.install(self.source)
        self.assertEqual(raised.exception.code, 'HASH_MISMATCH')
        self.write_release()
        manifest = json.loads((self.source / 'MANIFEST.json').read_text())
        manifest['../escape'] = '0' * 64
        (self.source / 'MANIFEST.json').write_text(json.dumps(manifest))
        with self.assertRaises(installer.InstallError) as raised:
            installer.install(self.source)
        self.assertEqual(raised.exception.code, 'INVALID_RELEASE')
        self.assertFalse(self.target.exists())

    def test_source_directory_symlink_rejected(self):
        self.files.pop('assets/test.json')
        self.files['assets/linked/README.md'] = b'outside'
        outside = self.home / 'outside'
        outside.mkdir()
        (outside / 'README.md').write_bytes(b'outside')
        (self.source / 'assets/linked').symlink_to(outside, target_is_directory=True)
        manifest = {rel: hashlib.sha256(data).hexdigest() for rel, data in self.files.items()}
        (self.source / 'MANIFEST.json').write_text(json.dumps(manifest))
        with self.assertRaises(installer.InstallError) as raised:
            installer.install(self.source)
        self.assertEqual(raised.exception.code, 'INVALID_RELEASE')

    def test_environment_failure_does_not_report_success(self):
        self.env.side_effect = installer.InstallError('ENVIRONMENT_FAILED', 'network unavailable')
        with self.assertRaises(installer.InstallError):
            installer.install(self.source)
        self.assertFalse((self.target / 'INSTALLATION.json').exists())
        self.assertTrue((self.target / 'SKILL.md').exists())


class EnvironmentBootstrapTests(unittest.TestCase):
    def test_fresh_venv_installs_hash_locked_packages_then_doctor(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)
            env = target / '.venv'
            calls = []
            def run(command, cwd, seconds):
                calls.append(command)
                if 'venv' in command:
                    (env / 'bin').mkdir(parents=True)
                    (env / 'bin/python').write_text('fixture')
                    return ''
                if '-c' in command:
                    return json.dumps({'prefix': str(env), 'base': '/system'})
                return json.dumps({'ok': True, 'reused': True})
            with patch.object(installer, 'run', side_effect=run):
                installer.prepare_environment(target)
            pip = next(command for command in calls if 'pip' in command)
            self.assertIn('--require-hashes', pip)
            self.assertEqual(pip[0], str(env / 'bin/python'))
            self.assertEqual(calls[-1][-2:], ['doctor', '--repair'])

    def test_existing_healthy_venv_does_not_recreate_or_run_pip(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)
            env = target / '.venv'
            (env / 'bin').mkdir(parents=True)
            (env / 'bin/python').write_text('fixture')
            with patch.object(installer, 'run', side_effect=[
                    json.dumps({'prefix': str(env), 'base': '/system'}), json.dumps({'ok': True, 'reused': True})]) as run:
                installer.prepare_environment(target)
            self.assertEqual(run.call_count, 2)
            self.assertFalse(any('pip' in call.args[0] or 'venv' in call.args[0] for call in run.call_args_list))

    def test_wrong_prefix_refuses_system_install(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)
            (target / '.venv/bin').mkdir(parents=True)
            (target / '.venv/bin/python').write_text('fixture')
            with patch.object(installer, 'run', return_value=json.dumps({'prefix': '/system', 'base': '/system'})) as run:
                with self.assertRaises(installer.InstallError) as raised:
                    installer.prepare_environment(target)
                self.assertEqual(raised.exception.code, 'VENV_BROKEN')
                self.assertEqual(run.call_count, 1)
