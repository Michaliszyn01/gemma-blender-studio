import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
import core

class ValidationTests(unittest.TestCase):
    def test_tapered_box_contract(self):
        good={'op':'tapered_box','name':'abdomen','top_scale':[1.3,1],'dimensions':[2,1,0.5]}
        self.assertEqual(core.validate_actions([good],[],{}),[good])
        for scale in [None,[1],[0,1],[5,1],[True,1]]:
            with self.assertRaises(ValueError):
                core.validate_actions([dict(good,top_scale=scale)],[],{})
    def test_no_unknown_actions_or_arbitrary_paths(self):
        for action in [{'op':'python','name':'x'}, {'op':'import_asset','name':'x','asset_id':'unknown','asset_path':'/etc/passwd'}, {'op':'box','name':'SYS_Camera'}]:
            with self.assertRaises(ValueError):core.validate_actions([action],[],{})
    def test_sequential_edit_delete_and_duplicate(self):
        actions=[{'op':'box','name':'body'},{'op':'transform','name':'body','dimensions':[2,1,3]},{'op':'delete','name':'body'}]
        self.assertEqual(len(core.validate_actions(actions,[],{})),3)
        with self.assertRaises(ValueError):core.validate_actions([{'op':'box','name':'body'}],['body'],{})
    def test_nan_mesh_indices_and_limits(self):
        for action in [{'op':'box','name':'x','location':[float('nan'),0,0]}, {'op':'box','name':'x','dimensions':[0,1,1]}, {'op':'mesh','name':'x','vertices':[[0,0,0],[1,0,0],[0,1,0]],'faces':[[0,1,3]]}]:
            with self.assertRaises(ValueError):core.validate_actions([action],[],{})
    def test_local_only_ollama(self):
        for url in ['https://example.com','http://127.0.0.1.evil.com','http://localhost:11434/api','http://user:pw@localhost']:
            with self.assertRaises(ValueError):core.local_url(url)
        self.assertEqual(core.local_url('http://localhost:11434/'),'http://localhost:11434')
    def test_zip_traversal_and_format_preference(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('../evil.obj','evil')
            with self.assertRaises(ValueError):core.extract_catalog(path,Path(d)/'out')
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('Models/GLB/gear.glb','data');z.writestr('Models/FBX/gear.fbx','data');z.writestr('evil.py','print(1)')
            catalog=core.extract_catalog(path,Path(d)/'good')
            self.assertEqual(len(catalog),1);self.assertTrue(next(iter(catalog.values()))['path'].endswith('.glb'))
            self.assertFalse((Path(d)/'good'/'evil.py').exists())
    def test_image_encoding(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.png';Image.new('RGB',(2000,1000)).save(p)
            out=Image.open(io.BytesIO(base64.b64decode(core.image64(p))))
            self.assertEqual(out.size,(960,480))

class LoopTests(unittest.TestCase):
    def setup_studio(self,d):
        with patch.object(core,'ROOT',Path(d)):
            s=core.Studio(Path(d)/'data')
        s.deadline=time.monotonic()+100
        s.state={'status':'running','iteration':0,'events':[],'history':[],'accepted':None,'report':None}
        s.persist()
        return s
    def run_job(self,s,d,reviews,check_status='unmet'):
        job=Path(d)/'job';job.mkdir()
        reference=job/'reference.png';Image.new('RGB',(32,32)).save(reference)
        config={'iterations':len(reviews),'model':'fake','ollama_url':'http://localhost:11434'}
        proposal={'summary':'volume','stage':'blockout','actions':[{'op':'box','name':'body'}]}
        calls=iter(reviews)
        def ask(cfg,instruction,images,schema):
            if schema is not core.PLAN_SCHEMA and schema is not core.REVIEW_SCHEMA:
                self.assertEqual(images,[reference]+[job/f"iteration-{s.state['iteration']:03d}"/v for v in ['front.png','side.png','perspective.png']])
                return {'checks':[{'id':r['id'],'status':check_status,'evidence':'Specific evidence',
                    'correction':'Adjust shape' if check_status!='met' else ''} for r in json.loads(instruction)['requirements']]}
            if schema is core.PLAN_SCHEMA:
                self.assertEqual(images[0],reference)
                if s.state.get('accepted'):
                    self.assertEqual(images[1:], [Path(s.state['accepted']).parent/v for v in ['front.png','perspective.png']])
                return dict(proposal,actions=[{'op':'transform','name':'body','dimensions':[1,1,2]}] if s.state.get('accepted') else proposal['actions'])
            self.assertEqual(images[0],reference)
            self.assertEqual(images[1:3],[job/f"iteration-{s.state['iteration']:03d}"/v for v in ['front.png','perspective.png']])
            if s.state.get('accepted'):
                self.assertEqual(images[3:],[Path(s.state['accepted']).parent/v for v in ['front.png','perspective.png']])
            return next(calls)
        def blender(cfg,req,folder):
            (folder/'model.blend').write_bytes(b'BLENDER')
            for view in ['front','side','perspective']:Image.new('RGB',(32,32)).save(folder/(view+'.png'))
            return {'objects':[{'name':'body'}],'triangles':12}
        with patch.object(core,'ollama',return_value={'capabilities':['vision']}),patch.object(s,'ask',side_effect=ask),patch.object(s,'run_blender',side_effect=blender):
            s.work(config,job,reference,'robô',None)
        return job
    def test_rejection_keeps_prior_scene_and_stops_stagnation(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.setup_studio(d)
            review=lambda accept:{'accept':accept,'score':50,'finished':False,'issues':[],'reason':'review'}
            job=self.run_job(s,d,[review(True)]+[review(False)]*4)
            self.assertEqual(s.state['status'],'pending')
            self.assertEqual(s.state['iteration'],5)
            self.assertEqual(s.state['accepted'],str(job/'iteration-001'/'model.blend'))
            self.assertEqual(len(s.state['history']),5)
    def test_three_failures_preserve_and_exit(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.setup_studio(d)
            with patch.object(core,'ollama',return_value={'capabilities':['vision']}),patch.object(s,'ask',side_effect=RuntimeError('bad response')):
                s.work({'iterations':8,'ollama_url':'http://localhost:11434','model':'fake'},Path(d),Path(d)/'ref.png','robot',None)
            self.assertEqual(s.state['status'],'error');self.assertEqual(s.state['iteration'],3)
    def test_all_rejected_does_not_claim_accepted_model(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.setup_studio(d)
            self.run_job(s,d,[{'accept':False,'score':20,'finished':False,'issues':[],'reason':'poor'}]*4)
            self.assertIsNone(s.state['accepted'])
            self.assertEqual(s.state['status'],'pending')
            self.assertIn('sem versão aceita',s.state['message'])
    def test_finished_high_score_does_not_end_with_pending_requirements(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.setup_studio(d)
            review={'accept':True,'score':100,'finished':True,'issues':[],'reason':'useful'}
            self.run_job(s,d,[review]*3)
            self.assertEqual(s.state['iteration'],3)
            self.assertEqual(s.state['status'],'pending')
            self.assertFalse(s.state['assessment']['requirements_met'])
            self.assertIsNone(s.state.get('human_approval'))
    def test_all_requirements_met_only_waits_for_human(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.setup_studio(d)
            self.run_job(s,d,[{'accept':True,'score':40,'finished':False,'issues':[],'reason':'useful'}]*3,'met')
            self.assertEqual(s.state['iteration'],1)
            self.assertEqual(s.state['status'],'awaiting_approval')
            self.assertIsNone(s.state.get('human_approval'))
    def test_review_issues_override_all_met_checklist(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.setup_studio(d)
            self.run_job(s,d,[{'accept':True,'score':100,'finished':True,'issues':['missing bevels'],'reason':'useful'}]*2,'met')
            self.assertEqual(s.state['iteration'],2)
            self.assertEqual(s.state['status'],'pending')
    def test_expired_budget_preserves_model_and_reports_pending(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.setup_studio(d)
            accepted=Path(d)/'accepted.blend';accepted.write_bytes(b'untouched')
            s.state['accepted']=str(accepted);s.deadline=time.monotonic()-1
            with patch.object(core,'ollama',return_value={'capabilities':['vision']}):
                s.work({'iterations':3,'model':'fake','ollama_url':'http://localhost:11434'},Path(d),Path(d)/'ref.png','robot',None)
            self.assertEqual(s.state['status'],'pending')
            self.assertEqual(accepted.read_bytes(),b'untouched')
    def test_cancel_before_mutating(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.setup_studio(d);s.stop_event.set()
            with patch.object(core,'ollama',return_value={'capabilities':['vision']}),patch.object(s,'ask') as ask:
                s.work({'iterations':8,'ollama_url':'http://localhost:11434','model':'fake'},Path(d),Path(d)/'ref.png','robot',None)
                ask.assert_not_called()
            self.assertEqual(s.state['status'],'stopped')
    def test_missing_vision_fails_early(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.setup_studio(d)
            with patch.object(core,'ollama',return_value={'capabilities':['completion']}):s.work({'ollama_url':'http://localhost:11434','model':'fake'},Path(d),Path(d)/'ref.png','robot',None)
            self.assertEqual(s.state['status'],'error');self.assertIn('visão',s.state['message'])
    def test_restart_marks_interrupted_session(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.setup_studio(d)
            with patch.object(core,'ROOT',Path(d)):
                restarted=core.Studio(Path(d)/'data')
            self.assertEqual(restarted.state['status'],'interrupted')

class ResponseTests(unittest.TestCase):
    def test_structured_response_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(core,'ROOT',Path(d)):
                s=core.Studio(Path(d)/'data')
            s.deadline=time.monotonic()+100
            s.disable_thinking=True
            s.call_folder=Path(d)
            ref=Path(d)/'reference.png';Image.new('RGB',(32,32),'red').save(ref)
            config={'model':'test','context':8192,'timeout':30,'ollama_url':'http://localhost:11434'}
            response={'done':True,'done_reason':'length','eval_count':4096,
                      'message':{'content':'','thinking':'unfinished reasoning'}}
            with patch.object(core,'ollama',return_value=response) as call:
                with self.assertRaisesRegex(ValueError,'truncada'):
                    s.ask(config,'inspect',[ref],core.PLAN_SCHEMA)
                payload=call.call_args.args[2]
                self.assertIs(payload['think'],False)
                self.assertEqual(payload['messages'][-1]['images'],[core.image64(ref)])
            self.assertEqual(core.load_json(Path(d)/'planning-response.json'),response)
            manifest=core.load_json(Path(d)/'planning-request.json')
            self.assertEqual(manifest['messages'][-1]['images'][0]['path'],str(ref))
            for message,pattern in [({'content':''},'vazia'),({'content':'[]'},'objeto JSON'),({'content':'broken'},'JSON válido')]:
                with patch.object(core,'ollama',return_value={'done':True,'done_reason':'stop','message':message}):
                    with self.assertRaisesRegex(ValueError,pattern):
                        s.ask(config,'inspect',[ref],core.PLAN_SCHEMA)

if __name__=='__main__':unittest.main()
