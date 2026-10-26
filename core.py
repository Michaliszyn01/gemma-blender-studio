"""Local modelling controller. No model-generated Python is executed."""
import base64
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import urllib.error
import uuid
import zipfile
from PIL import Image, ImageOps
from requirements_check import build_requirements, check_schema, geometry_checks, assess, torso_contract

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,63}$')
OPS = {'box', 'tapered_box', 'cylinder', 'sphere', 'cone', 'torus', 'mesh', 'transform', 'material', 'delete', 'import_asset'}


def save_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def vector(v, n, low, high):
    if not isinstance(v, list) or len(v) != n:
        raise ValueError(f'Esperado vetor com {n} valores.')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not low <= x <= high for x in v):
        raise ValueError('Vetor fora dos limites.')
    return v


def validate_actions(actions, known_names, catalog):
    if not isinstance(actions, list) or not 1 <= len(actions) <= 24:
        raise ValueError('O lote precisa ter de 1 a 24 operações.')
    known = set(known_names)
    result = []
    for raw in actions:
        a = dict(raw)
        op, name = a.get('op'), a.get('name')
        if op not in OPS or not isinstance(name, str) or not NAME.fullmatch(name) or name.startswith('SYS_'):
            raise ValueError('Operação ou nome inválido. Use nomes ASCII e não use SYS_.')
        if op in {'transform', 'material', 'delete'}:
            if name not in known:
                raise ValueError(f'Objeto desconhecido: {name}')
        else:
            if name in known:
                raise ValueError(f'Nome já existe: {name}. Use transform para editar.')
            if len(known) >= 200:
                raise ValueError('Limite de 200 objetos/grupos atingido.')
            known.add(name)
        if op == 'delete':
            known.remove(name)
        for field, count, lo, hi in [('location',3,-100,100), ('rotation',3,-360,360), ('dimensions',3,0.005,100), ('color',4,0,1)]:
            if field in a:
                vector(a[field], count, lo, hi)
        if op == 'tapered_box' or 'top_scale' in a:
            vector(a.get('top_scale'),2,0.05,4)
            if op not in {'tapered_box','transform'}:
                raise ValueError('top_scale só se aplica a tapered_box ou transform.')
        for field in ('bevel', 'metallic', 'roughness'):
            if field in a:
                v = a[field]
                if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0 <= v <= 1:
                    raise ValueError(f'{field} precisa estar entre 0 e 1.')
        if op == 'import_asset':
            if a.get('asset_id') not in catalog:
                raise ValueError('Asset não encontrado no catálogo.')
            a['asset_path'] = catalog[a['asset_id']]['path']
        if op == 'mesh':
            verts, faces = a.get('vertices'), a.get('faces')
            if not isinstance(verts,list) or not 3 <= len(verts) <= 512 or not isinstance(faces,list) or not 1 <= len(faces) <= 1024:
                raise ValueError('Malha fora dos limites: 3–512 vértices, 1–1024 faces.')
            for v in verts:
                vector(v,3,-100,100)
            for f in faces:
                if not isinstance(f,list) or not 3 <= len(f) <= 32 or any(type(i) is not int or i < 0 or i >= len(verts) for i in f):
                    raise ValueError('Face inválida.')
        result.append(a)
    return result


def local_url(url):
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'} or parsed.username or parsed.password or parsed.path not in {'','/'}:
        raise ValueError('Use o endereço HTTP local do Ollama, por exemplo http://127.0.0.1:11434.')
    return url.rstrip('/')


def ollama(url, endpoint, payload=None, timeout=30):
    url = local_url(url)
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url + endpoint, data=body, headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.load(res)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Ollama HTTP {e.code}: {e.read(1500).decode(errors="replace")}') from e
    except urllib.error.URLError as e:
        raise RuntimeError(f'Ollama indisponível: {e.reason}. Verifique se está aberto.') from e


def image64(path):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((960,960))
        out = io.BytesIO()
        im.save(out,'JPEG',quality=88)
        return base64.b64encode(out.getvalue()).decode()


def detect_blender():
    found = shutil.which('blender')
    if found:
        return found
    for base in [Path('C:/Program Files/Blender Foundation'), Path('/Applications/Blender.app/Contents/MacOS')]:
        if base.exists():
            candidates = sorted(base.glob('**/blender.exe')) + sorted(base.glob('blender'))
            if candidates:
                return str(candidates[-1])
    return ''


def default_settings():
    return {'ollama_url':'http://127.0.0.1:11434','model':'','blender':detect_blender(), 'iterations':3,'hours':0.25,'context':8192, 'timeout':600}


def extract_catalog(archive, destination):
    """Only selected game asset formats are extracted; no scripts or traversal."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > 5000 or sum(i.file_size for i in infos) > 500*1024*1024:
            raise ValueError('Pacote excede os limites de extração.')
        for info in infos:
            name = info.filename.replace('\\','/')
            target = (destination/name).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('Caminho inválido no ZIP.')
            if info.is_dir() or target.suffix.lower() not in {'.glb','.fbx','.obj','.mtl','.png','.jpg','.jpeg','.txt'}:
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as src, target.open('wb') as dst:
                shutil.copyfileobj(src,dst)
            extracted.append(target)
    # Prefer GLB to keep materials and avoid duplicate formats.
    models = [p for p in extracted if p.suffix.lower()=='.glb']
    if not models:
        models = [p for p in extracted if p.suffix.lower() in {'.fbx','.obj'}]
    return {f'asset_{i:03d}':{'name':p.stem,'path':str(p)} for i,p in enumerate(sorted(models))}


class Cancelled(Exception):
    pass


class BudgetExpired(Cancelled):
    pass


class Studio:
    def __init__(self, data=DATA):
        self.data = Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.state = load_json(self.data/'state.json', {'status':'idle','message':'Pronto para começar.','events':[],'history':[]})
        if self.state.get('status') in {'running','stopping'}:
            self.state.update(status='interrupted',message='Sessão interrompida. Você pode retomar a última versão aceita.')
            self.persist()
        self.catalog = {}
        bundle = ROOT/'assets'/'factory.zip'
        if bundle.exists():
            cached = load_json(self.data/'catalog.json')
            if cached and all(Path(x['path']).exists() for x in cached.values()):
                self.catalog = cached
            else:
                self.catalog = extract_catalog(bundle,self.data/'factory')
                save_json(self.data/'catalog.json',self.catalog)

    def persist(self):
        save_json(self.data/'state.json', self.state)
        if self.state.get('job'):
            save_json(Path(self.state['job'])/'state.json', self.state)

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def update(self, **values):
        with self.lock:
            self.state.update(values)
            self.persist()

    def log(self, message):
        with self.lock:
            self.state.setdefault('events',[]).append({'time':time.strftime('%H:%M:%S'),'message':str(message)[:3000]})
            self.state['events'] = self.state['events'][-150:]
            self.state['message'] = str(message)[:3000]
            self.persist()

    def check(self):
        if self.stop_event.is_set():
            raise Cancelled()
        if time.monotonic() > self.deadline:
            raise BudgetExpired('Limite de tempo atingido.')

    def run_blender(self, config, request_file, folder):
        command = [config['blender'],'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(ROOT/'blender_worker.py'),'--',str(request_file)]
        with (folder/'blender.log').open('w',encoding='utf-8') as output:
            process = subprocess.Popen(command, stdout=output,stderr=subprocess.STDOUT)
            try:
                until = time.monotonic()+300
                while process.poll() is None:
                    self.check()
                    if time.monotonic()>until:
                        raise RuntimeError('Blender excedeu 5 minutos nesta etapa.')
                    self.stop_event.wait(0.25)
                if process.returncode:
                    detail = (folder/'blender.log').read_text(encoding='utf-8',errors='replace')[-2500:]
                    raise RuntimeError('Falha no Blender: '+detail)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        report = load_json(folder/'scene.json')
        if not report or not (folder/'model.blend').exists() or not all((folder/(v+'.png')).exists() for v in ['front','side','perspective']):
            raise RuntimeError('Blender não produziu todos os arquivos esperados.')
        return report

    def ask(self, config, instruction, images, schema):
        self.check()
        payload = {'model':config['model'], 'stream':False,'format':schema,'keep_alive':0,
                   'options':{'temperature':0.2,'num_ctx':config['context'],'num_predict':4096},
                   'messages':[{'role':'system','content':(ROOT/'modeling_guide.txt').read_text(encoding='utf-8')},
                               {'role':'user','content':instruction,'images':[image64(p) for p in images]}]}
        # Discover support instead of forcing an option on every installed model.
        if getattr(self, 'disable_thinking', False):
            payload['think'] = False
        audit = getattr(self, 'call_folder', None)
        kind = 'planning' if schema is PLAN_SCHEMA else 'review' if schema is REVIEW_SCHEMA else 'requirements'
        if audit:
            manifest = copy.deepcopy(payload)
            manifest['messages'][-1]['images'] = [
                {'path':str(p), 'file_sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                 'sent_sha256':hashlib.sha256(base64.b64decode(encoded)).hexdigest()}
                for p,encoded in zip(images,payload['messages'][-1]['images'])]
            save_json(audit/(kind+'-request.json'),manifest)
        response = ollama(config['ollama_url'],'/api/chat',payload,timeout=config['timeout'])
        if audit:
            save_json(audit/(kind+'-response.json'),response)
        self.check()
        if response.get('done_reason') == 'length':
            raise ValueError('Resposta truncada pelo limite de geração (done_reason=length). Consulte o registro da chamada; nenhuma ação foi executada.')
        content = response.get('message',{}).get('content','').strip()
        if not content:
            raise ValueError('Resposta final vazia do Ollama. Consulte done_reason e thinking no registro da chamada.')
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            raise ValueError('O modelo não retornou JSON válido. Resposta original preservada no registro da chamada.')
        if not isinstance(value,dict):
            raise ValueError('A resposta estruturada precisa ser um objeto JSON.')
        return value

    def start(self, config, reference, prompt, source=None, resume=False):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Já há uma sessão em execução.')
            config = dict(config)
            config['ollama_url'] = local_url(config['ollama_url'])
            if not Path(config['blender']).is_file():
                raise ValueError('Selecione o executável do Blender nas configurações.')
            if not config.get('model'):
                raise ValueError('Selecione um modelo instalado no Ollama.')
            for k,lo,hi in [('iterations',1,300),('hours',0.05,24),('context',4096,32768),('timeout',30,1800)]:
                config[k] = float(config[k]) if k=='hours' else int(config[k])
                if not lo <= config[k] <= hi:
                    raise ValueError(f'Valor fora dos limites: {k}')
            if resume:
                if not self.state.get('job'):
                    raise ValueError('Nenhuma sessão para retomar.')
                job = Path(self.state['job'])
                meta = load_json(job/'job.json')
                if not meta:
                    raise ValueError('Dados da sessão não encontrados.')
                reference, prompt, source = job/'reference.png', meta['prompt'], meta.get('source')
                self.state['status']='running'
                self.state['human_approval']=None
            else:
                if not reference or not Path(reference).exists() or not prompt.strip():
                    raise ValueError('Adicione a referência e descreva o modelo.')
                job = self.data/'jobs'/time.strftime('%Y%m%d-%H%M%S')
                job = job.with_name(job.name+'-'+uuid.uuid4().hex[:6])
                job.mkdir(parents=True)
                shutil.copy2(reference,job/'reference.png')
                if source:
                    shutil.copy2(source,job/'source.blend')
                    source = str(job/'source.blend')
                reference = job/'reference.png'
                save_json(job/'job.json',{'prompt':prompt,'source':source,'config':config})
                self.state = {'status':'running','job':str(job),'message':'Verificando modelo…','events':[], 'history':[],'iteration':0,'accepted':None,'report':None}
            self.persist()
            save_json(self.data/'settings.json',config)
            save_json(job/('config-resume-'+time.strftime('%Y%m%d-%H%M%S')+'.json' if resume else 'config.json'),config)
            self.stop_event.clear()
            self.deadline=time.monotonic()+config['hours']*3600
            self.thread=threading.Thread(target=self.work,args=(config,job,Path(reference),prompt,source),daemon=True)
            self.thread.start()
            return self.snapshot()

    def finish_session(self, reason):
        state=self.snapshot()
        ready=bool(state.get('accepted')) and state.get('assessment',{}).get('requirements_met',False)
        self.update(status='awaiting_approval' if ready else 'pending',phase='done',end_reason=reason)
        self.log(('Verificação sem pendências; aguardando aprovação final do usuário. ' if ready else
                  'Sessão encerrada com pendências. '+('Última versão intermediária preservada. ' if state.get('accepted') else 'Ainda sem versão aceita. '))+reason)

    def approve(self, model, digest):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Aguarde a sessão encerrar antes de aprovar.')
            if self.state.get('status')!='awaiting_approval' or not self.state.get('assessment',{}).get('requirements_met'):
                raise ValueError('Existem requisitos pendentes; revise-os antes da aprovação final.')
            accepted=self.state.get('accepted')
            if model!=accepted or not accepted or hashlib.sha256(Path(accepted).read_bytes()).hexdigest()!=digest:
                raise ValueError('A versão mudou. Recarregue e confira o modelo antes de aprovar.')
            approval={'model':accepted,'sha256':digest,'time':time.strftime('%Y-%m-%dT%H:%M:%S'),'by':'user'}
            save_json(Path(self.state['job'])/'human-approval.json',approval)
            self.update(human_approval=approval,status='approved',message='Resultado aprovado pelo usuário.')

    def verify_requirements(self,config,prompt,reference,folder,report,requirements,review):
        measured=geometry_checks(prompt,report)
        self.update(phase='checking')
        try:
            raw=self.ask(config,json.dumps({
                'task':prompt,'requirements':requirements,'geometry_checks':measured,'scene':report,
                'instruction':'Verificação de requisitos, NÃO avaliação de utilidade intermediária. Imagem 1 referência; 2 frontal, 3 lateral, 4 perspectiva do candidato. Retorne uma entrada por id com status met/unmet/uncertain, evidência específica e correção concreta. Compare silhueta, contorno, largura/altura, cintura, afunilamento, orientação dos cilindros, contatos e chanfros. Estar pronto para refinar não atende ao requisito de forma. Dúvidas são uncertain, nunca met. Não contradiga falhas geométricas medidas. Seja conciso.'},ensure_ascii=False),
                [reference,folder/'front.png',folder/'side.png',folder/'perspective.png'],check_schema(requirements))
        except Cancelled:
            raise
        except Exception as e:
            raw={'checks':[],'error':str(e)}
        save_json(folder/'requirements-raw.json',raw)
        result=assess(requirements,raw,measured,review.get('issues',[]))
        result['model']=str(folder/'model.blend')
        save_json(folder/'requirements-check.json',result)
        return result

    def work(self,config,job,reference,prompt,source):
        try:
            info = ollama(config['ollama_url'],'/api/show',{'model':config['model']})
            save_json(job/'model-info.json',info)
            self.disable_thinking = False in info.get('thinking',{}).get('values',[])
            if 'vision' not in info.get('capabilities',[]):
                raise RuntimeError('Este modelo/versão do Ollama não anuncia visão. Escolha uma variante multimodal e atualize o Ollama.')
            self.log('Visão disponível. Preparando geometria e referências.')
            state=self.snapshot()
            requirements=build_requirements(prompt)
            save_json(job/'requirements.json',{'prompt':prompt,'items':requirements,
                'geometry_contract':'named_six_part_torso' if torso_contract(prompt) else None})
            self.update(requirements=requirements,human_approval=None)
            accepted=state.get('accepted')
            report=state.get('report')
            if source and not accepted:
                folder=job/'baseline';folder.mkdir(exist_ok=True)
                save_json(folder/'request.json',{'base':source,'actions':[], 'output':str(folder)})
                report=self.run_blender(config,folder/'request.json',folder)
                accepted=str(folder/'model.blend')
                self.update(accepted=accepted,report=report,preview=str(folder/'perspective.png'))
            failures=0;stagnant=0
            feedback=state.get('assessment') or 'Construa o volume principal primeiro. Não detalhe antes de acertar proporções.'
            current_images=[]
            if accepted:
                current_images=[Path(accepted).parent/'front.png',Path(accepted).parent/'perspective.png']
            first=int(self.snapshot().get('iteration',0))+1
            for iteration in range(first,first+config['iterations']):
                self.check()
                self.update(iteration=iteration,phase='planning')
                folder=job/f'iteration-{iteration:03d}';folder.mkdir(exist_ok=True)
                self.call_folder=folder
                self.log(f'Etapa {iteration}: planejando alterações pequenas.')
                try:
                    instruction=json.dumps({'task':prompt,'reference':'Primeira imagem é a referência. Demais imagens são a versão aceita atual.',
                        'scene':report or {'objects':[]},
                        'requirements':requirements,'pending_requirements':self.snapshot().get('assessment',{}).get('pending',[]),
                        'geometry_contract':('Os seis componentes devem conectar-se com pequena sobreposição. Cilindros de ombro têm eixo local Z apontando para X: rotation [0,90,0]. Pescoço aponta para Z. top_scale maior que 1 alarga o TOPO do abdômen, preservando dimensões máximas. Meça limites globais para evitar lacunas.' if torso_contract(prompt) else None),
                        'base_state':{'has_accepted_model':bool(accepted),'editable_names':[o['name'] for o in (report or {}).get('objects',[])],
                                      'rule':'Somente scene existe na base. Candidatos rejeitados NÃO existem nela. Sem versão aceita, crie do zero; não transforme nem exclua peças rejeitadas.'},
                        'catalog':[{'id':k,'name':v['name']} for k,v in self.catalog.items()],
                        'feedback':feedback,'request':'Retorne summary, stage e actions. Não retorne código Python. Mantenha nomes existentes. Eixos: Z para cima; frente em Y negativo. Unidades de construção arbitrárias; um robô pode ter altura 6.'},ensure_ascii=False)
                    proposal=self.ask(config,instruction,[reference]+current_images,PLAN_SCHEMA)
                    save_json(folder/'proposal.json',proposal)
                    actions=validate_actions(proposal.get('actions'),[o['name'] for o in (report or {}).get('objects',[])],self.catalog)
                    self.update(phase='building')
                    self.log(proposal.get('summary','Construindo candidato…'))
                    save_json(folder/'request.json',{'base':accepted,'actions':actions,'output':str(folder)})
                    candidate_report=self.run_blender(config,folder/'request.json',folder)
                    self.update(phase='reviewing',candidate=str(folder/'perspective.png'))
                    self.log('Comparando referência, candidato e versão anterior.')
                    review_images=[reference]+[folder/'front.png',folder/'perspective.png']+current_images
                    review=self.ask(config,json.dumps({'task':prompt,'instruction':'Decida somente se o candidato é uma versão intermediária útil para continuar. Imagem 1: referência. 2 e 3: candidato frontal e perspectiva. 4 e 5, se presentes: versão aceita anterior. Aceite melhorias reais e volumes básicos úteis; não aceite regressão. score é opinião, não conclusão. Liste todas as pendências em issues. Retorne accept, score, issues e reason. A aprovação final pertence ao usuário.', 'candidate':candidate_report,'changes':proposal.get('summary')},ensure_ascii=False),review_images,REVIEW_SCHEMA)
                    if type(review.get('accept')) is not bool or type(review.get('score')) not in (int,float) or not 0<=review['score']<=100 or not isinstance(review.get('issues'),list):
                        raise ValueError('Revisão visual inválida.')
                    save_json(folder/'review.json',review)
                    keep=review['accept']
                    with self.lock:
                        self.state['history'].append({'iteration':iteration,'accepted':keep,'score':review['score'],'reason':str(review.get('reason','')),'preview':str(folder/'perspective.png'),'model':str(folder/'model.blend')})
                    if keep:
                        accepted=str(folder/'model.blend');report=candidate_report
                        current_images=[folder/'front.png',folder/'perspective.png']
                        self.update(accepted=accepted,report=report,preview=str(folder/'perspective.png'))
                        self.update(assessment=assess(requirements,{},geometry_checks(prompt,report)),
                                    human_approval=None)
                        stagnant=0
                    else:
                        stagnant+=1
                    assessment=self.verify_requirements(config,prompt,reference,folder,candidate_report,requirements,review)
                    if keep:
                        self.update(assessment=assessment)
                    feedback=json.dumps({'review':review,'candidate_check':assessment,
                        'base':'Apenas a última versão aceita existe; candidato rejeitado não é a base.'},ensure_ascii=False)
                    self.log(('Versão intermediária aceita. ' if keep else 'Candidato rejeitado; versão anterior preservada. ')+str(review.get('reason','')))
                    failures=0
                    if keep and assessment['requirements_met']:
                        self.finish_session('Todos os itens têm evidências; a aprovação continua sendo humana.')
                        return
                except Cancelled:
                    raise
                except Exception as e:
                    failures+=1
                    feedback=f'A tentativa anterior falhou: {str(e)[:1800]}. Corrija a causa e proponha outro lote válido.'
                    self.log(feedback)
                    save_json(folder/'error.json',{'error':str(e)})
                    if failures>=3:
                        raise RuntimeError('Três falhas consecutivas. Última versão aceita preservada. '+str(e)) from e
            self.finish_session('Limite de rodadas atingido.')
        except BudgetExpired as e:
            self.finish_session(str(e))
        except Cancelled as e:
            self.update(status='stopped',phase='done')
            self.log(str(e) or 'Sessão parada. Versões preservadas.')
        except Exception as e:
            self.update(status='error',phase='done')
            self.log(str(e))

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.update(status='stopping',message='Parando. Se o Ollama estiver gerando, aguarde a resposta ou o timeout configurado.')


PLAN_SCHEMA={'type':'object','properties':{'summary':{'type':'string'},'stage':{'type':'string'},'actions':{'type':'array','minItems':1,'maxItems':24,'items':{'type':'object','properties':{'op':{'type':'string','enum':sorted(OPS)},'name':{'type':'string'},'location':{'type':'array','items':{'type':'number'}},'rotation':{'type':'array','items':{'type':'number'}},'dimensions':{'type':'array','items':{'type':'number'}},'color':{'type':'array','items':{'type':'number'}},'bevel':{'type':'number'},'metallic':{'type':'number'},'roughness':{'type':'number'},'asset_id':{'type':'string'},'vertices':{'type':'array','items':{'type':'array','items':{'type':'number'}}},'faces':{'type':'array','items':{'type':'array','items':{'type':'integer'}}}},'required':['op','name']}}},'required':['summary','stage','actions']}
REVIEW_SCHEMA={'type':'object','properties':{'accept':{'type':'boolean'},'score':{'type':'number'},'finished':{'type':'boolean'},'issues':{'type':'array','items':{'type':'string'}},'reason':{'type':'string'}},'required':['accept','score','finished','issues','reason']}
REVIEW_SCHEMA['properties'].pop('finished')
REVIEW_SCHEMA['required'].remove('finished')

# Mirror the worker contract in constrained generation, not only after generation.
_properties=PLAN_SCHEMA['properties']['actions']['items']['properties']
for _field,_count in [('location',3),('rotation',3),('dimensions',3),('color',4)]:
    _properties[_field].update(minItems=_count,maxItems=_count)
_properties['top_scale']={'type':'array','items':{'type':'number','minimum':0.05,'maximum':4},'minItems':2,'maxItems':2}
_properties['vertices'].update(minItems=3,maxItems=512)
_properties['vertices']['items'].update(minItems=3,maxItems=3)
_properties['faces'].update(minItems=1,maxItems=1024)
_properties['faces']['items'].update(minItems=3,maxItems=32)
