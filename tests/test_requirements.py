import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
from requirements_check import assess,build_requirements,geometry_checks


class RequirementsTests(unittest.TestCase):
    def test_missing_duplicate_or_evidenceless_items_are_pending(self):
        requirements=build_requirements('Wide chest\nShort abdomen')
        a={'id':'r01','status':'met','evidence':'front image','correction':''}
        for rows in [[],[a],[a,a], [a,{'id':'r02','status':'met','evidence':'','correction':''}]]:
            self.assertFalse(assess(requirements,{'checks':rows},[])['requirements_met'])
    def test_geometry_failure_cannot_be_overridden_by_visual_model(self):
        requirements=build_requirements('robot')
        visual={'checks':[{'id':'r01','status':'met','evidence':'looks good','correction':''}]}
        self.assertFalse(assess(requirements,visual,[{'id':'axis','status':'unmet','evidence':'vertical'}])['requirements_met'])
    def test_human_approval_is_explicit_and_bound_to_file(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(core,'ROOT',Path(d)):s=core.Studio(Path(d)/'data')
            model=Path(d)/'model.blend';model.write_bytes(b'original')
            s.state.update(job=d,accepted=str(model),status='awaiting_approval',assessment={'requirements_met':True})
            with self.assertRaises(ValueError):s.approve(str(model),'stale')
            self.assertNotIn('human_approval',s.state)
            s.approve(str(model),hashlib.sha256(model.read_bytes()).hexdigest())
            self.assertEqual(s.state['status'],'approved')
            self.assertEqual(json.loads((Path(d)/'human-approval.json').read_text())['by'],'user')
    def test_cannot_approve_pending(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(core,'ROOT',Path(d)):s=core.Studio(Path(d)/'data')
            s.state.update(status='pending',assessment={'requirements_met':False})
            with self.assertRaises(ValueError):s.approve(None,None)

if __name__=='__main__':unittest.main()
