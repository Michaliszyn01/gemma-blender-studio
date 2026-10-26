"""Reproduce the original planning request without changing its session."""
import json
from pathlib import Path
import core

out = core.ROOT / 'diagnostics'
config = core.load_json(core.DATA / 'settings.json')
job = core.DATA / 'jobs' / '20261020-141648-a54e44'
meta = core.load_json(job / 'job.json')
catalog = core.load_json(core.DATA / 'catalog.json')
instruction = json.dumps({'task':meta['prompt'],'reference':'Primeira imagem é a referência. Demais imagens são a versão aceita atual.',
    'scene':{'objects':[]}, 'catalog':[{'id':k,'name':v['name']} for k,v in catalog.items()],
    'feedback':'Construa o volume principal primeiro. Não detalhe antes de acertar proporções.',
    'request':'Retorne summary, stage e actions. Não retorne código Python. Mantenha nomes existentes. Eixos: Z para cima; frente em Y negativo. Unidades de construção arbitrárias; um robô pode ter altura 6.'},ensure_ascii=False)
payload = {'model':config['model'],'stream':False,'format':core.PLAN_SCHEMA,'keep_alive':0,
    'options':{'temperature':0.2,'num_ctx':config['context'],'num_predict':4096},
    'messages':[{'role':'system','content':(core.ROOT/'modeling_guide.txt').read_text(encoding='utf-8')},
                {'role':'user','content':instruction,'images':[core.image64(job/'reference.png')]}]}
core.save_json(out/'original-request.json',payload)
for endpoint in ['version','tags']:
    core.save_json(out/(endpoint+'.json'),core.ollama(config['ollama_url'],'/api/'+endpoint))
core.save_json(out/'show.json',core.ollama(config['ollama_url'],'/api/show',{'model':config['model']}))
response=core.ollama(config['ollama_url'],'/api/chat',payload,timeout=config['timeout'])
core.save_json(out/'original-response.json',response)
print(json.dumps({k:v for k,v in response.items() if k!='message'},indent=2))
print('content:',repr(response.get('message',{}).get('content',''))[:1000])
print('thinking chars:',len(response.get('message',{}).get('thinking','')))
