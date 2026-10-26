"""Real Blender candidate with a controlled rejection, not an AI quality test."""
import hashlib
from pathlib import Path
import shutil
import time
from unittest.mock import patch
import core

out=core.ROOT/'diagnostics'/'rollback'
out.mkdir(exist_ok=True)
source=core.ROOT/'diagnostics'/'real-20261020-142556'/'jobs'/'20261020-142557-c9b364'/'iteration-002'
accepted=source/'model.blend'
before=hashlib.sha256(accepted.read_bytes()).hexdigest()
s=core.Studio(out)
s.state={'status':'running','iteration':0,'events':[],'history':[],'accepted':str(accepted),
         'report':core.load_json(source/'scene.json')}
s.deadline=time.monotonic()+300
config=core.load_json(core.DATA/'settings.json');config['iterations']=1
def ask(cfg,instruction,images,schema):
    if schema is core.PLAN_SCHEMA:
        assert images[1:]==[source/'front.png',source/'perspective.png']
        return {'summary':'Controlled rollback test','actions':[{'op':'transform','name':'peito','dimensions':[4,1,1]}]}
    assert images[1:3]==[out/'iteration-001'/'front.png',out/'iteration-001'/'perspective.png']
    assert images[3:]==[source/'front.png',source/'perspective.png']
    return {'accept':False,'finished':False,'score':0,'issues':['controlled test'],'reason':'forced rejection to test preservation'}
with patch.object(s,'ask',side_effect=ask),patch.object(core,'ollama',return_value={'capabilities':['vision']}):
    s.work(config,out,core.DATA/'jobs'/'20261020-141648-a54e44'/'reference.png','rollback test',None)
assert s.state['accepted']==str(accepted),s.state
assert len(s.state['history'])==1 and not s.state['history'][0]['accepted']
assert before==hashlib.sha256(accepted.read_bytes()).hexdigest()
core.save_json(out/'verification.json',{'passed':True,'review':'controlled rejection; real Blender',
    'accepted_sha256_before_and_after':before,'candidate':str(out/'iteration-001'/'model.blend')})
print('PASS: real candidate saved; rejected candidate did not replace or modify accepted blend; image order correct')
