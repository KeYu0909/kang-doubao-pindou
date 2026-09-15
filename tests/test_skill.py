"""Validate distributable skill structure and documentation references."""
from pathlib import Path
import re
import unittest
import yaml
ROOT=Path(__file__).resolve().parents[1]
class SkillStructureTests(unittest.TestCase):
    def test_standard_frontmatter_and_resolvable_references(self):
        text=(ROOT/'SKILL.md').read_text();self.assertTrue(text.startswith('---\n'))
        data=yaml.safe_load(text.split('---',2)[1])
        self.assertEqual(data['name'],ROOT.name);self.assertRegex(data['name'],r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
        self.assertLessEqual(len(data['name']),64);self.assertTrue(0<len(data['description'])<=1024)
        self.assertLessEqual(len(data.get('compatibility','')),500);self.assertLess(len(text.splitlines()),500)
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if '://' not in target:self.assertTrue((ROOT/target.split('#')[0]).is_file(),target)
if __name__=='__main__':unittest.main()
