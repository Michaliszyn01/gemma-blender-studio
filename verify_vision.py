"""Blind image description and blank control with identical text."""
from PIL import Image
import core

out=core.ROOT/'diagnostics'/'vision'
out.mkdir(exist_ok=True)
Image.new('RGB',(640,640),'white').save(out/'blank.png')
config=core.load_json(core.DATA/'settings.json')
schema={'type':'object','properties':{'description':{'type':'string'}},'required':['description']}
for label,path in [('reference',core.DATA/'jobs'/'20261020-141648-a54e44'/'reference.png'),('blank',out/'blank.png')]:
    payload={'model':config['model'],'stream':False,'think':False,'format':schema,'keep_alive':0,
             'options':{'num_ctx':config['context'],'num_predict':512,'temperature':0},
             'messages':[{'role':'user','content':'Descreva apenas o que está visível nesta imagem. Se não houver objetos, diga isso. Não suponha contexto anterior.',
                          'images':[core.image64(path)]}]}
    core.save_json(out/(label+'-request.json'),payload)
    response=core.ollama(config['ollama_url'],'/api/chat',payload,timeout=600)
    core.save_json(out/(label+'-response.json'),response)
    print(label,response.get('message',{}).get('content',''),flush=True)
