"""Evidence-based completion gate. No score or reviewer 'finished' can approve a job."""
import math
import re
import unicodedata


def normalized(text):
    return unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().lower()


def build_requirements(prompt):
    # Keep verbatim substantive lines; do not let the reviewing model omit requirements.
    lines=[s.strip() for s in prompt.splitlines() if s.strip()]
    lines=[s for s in lines if not (s.isupper() and len(s)<60)]
    if not lines:
        lines=[prompt]
    return [{'id':f'r{i:02d}','requirement':line} for i,line in enumerate(lines,1)]


def check_schema(requirements):
    return {'type':'object','properties':{'checks':{'type':'array','minItems':len(requirements),
        'maxItems':len(requirements),'items':{'type':'object','properties':{
        'id':{'type':'string','enum':[r['id'] for r in requirements]},
        'status':{'type':'string','enum':['met','unmet','uncertain']},
        'evidence':{'type':'string'},'correction':{'type':'string'}},
        'required':['id','status','evidence','correction']}}},'required':['checks']}


TORSO_NAMES=('peito','abdomen','cintura','encaixe_pescoco','encaixe_ombro_esquerdo','encaixe_ombro_direito')


def torso_contract(prompt):
    # Only activate this explicit contract when the user requested these exact components.
    return all(name in prompt for name in TORSO_NAMES)


def geometry_checks(prompt,report):
    if not torso_contract(prompt):
        return []
    objects={o['name']:o for o in report.get('objects',[])}
    checks=[]
    def add(key,title,status,evidence,correction=''):
        checks.append({'id':'geometry.'+key,'requirement':title,'status':status,
                       'evidence':evidence,'correction':correction,'source':'geometry'})
    missing=[n for n in TORSO_NAMES if n not in objects]
    add('components','Seis componentes solicitados presentes','unmet' if missing else 'met',
        'Ausentes: '+', '.join(missing) if missing else ', '.join(TORSO_NAMES),
        'Crie os componentes ausentes.' if missing else '')
    if missing:
        return checks
    p,a,w,neck,left,right=[objects[n] for n in TORSO_NAMES]
    for key,obj,axis in [('left_axis',left,0),('right_axis',right,0),('neck_axis',neck,2)]:
        vec=obj.get('world_axis_z')
        ok=vec is not None and abs(vec[axis])>=0.98
        add(key,'Eixo do cilindro '+obj['name'],'met' if ok else 'unmet' if vec else 'uncertain',
            f"Eixo local Z no mundo: {vec}; eixo exigido: {'X' if axis==0 else 'Z'}.",
            '' if ok else ('Use rotation [0,90,0] para apontar o cilindro lateral ao longo de X.' if axis==0 else 'Use rotation [0,0,0] para o pescoço.'))
    bounds=all('world_bounds_min' in o and 'world_bounds_max' in o for o in [p,a,w,neck,left,right])
    if not bounds:
        add('bounds','Contato e proporções verificáveis','uncertain','Relatório sem limites globais.','Renderize novamente para obter medidas.')
        return checks
    def size(o,i):return o['world_bounds_max'][i]-o['world_bounds_min'][i]
    def center(o,i):return (o['world_bounds_max'][i]+o['world_bounds_min'][i])/2
    tolerance=max(size(p,0),0.01)*1e-4
    for first,second in [(p,a),(a,w),(p,neck),(p,left),(p,right)]:
        gaps=[max(0,first['world_bounds_min'][i]-second['world_bounds_max'][i],
                  second['world_bounds_min'][i]-first['world_bounds_max'][i]) for i in range(3)]
        ok=max(gaps)<=tolerance
        add('contact_'+first['name']+'_'+second['name'],'Sem espaço entre '+first['name']+' e '+second['name'],
            'met' if ok else 'unmet',f'Separação entre caixas envolventes XYZ: {[round(v,4) for v in gaps]}. Sobreposição de caixas é condição necessária, não prova de contato da superfície.',
            '' if ok else 'Ajuste location/dimensions para pequena sobreposição dos volumes; confira também a vista frontal.')
    symmetry=max(abs(center(left,0)+center(right,0)-2*center(p,0)),
                 abs(center(left,1)-center(right,1)),abs(center(left,2)-center(right,2)),
                 *(abs(size(left,i)-size(right,i)) for i in range(3)))
    add('symmetry','Ombros simétricos','met' if symmetry<=tolerance*10 else 'unmet',
        f'Desvio máximo de centros/dimensões espelhados: {symmetry:.4f}.',
        '' if symmetry<=tolerance*10 else 'Espelhe X em torno do peito; mantenha Y, Z e dimensões iguais.')
    for key,ok,evidence in [
        ('chest_wide',size(p,0)>size(p,2),'Peito largura/altura: '+str(round(size(p,0)/max(size(p,2),1e-9),3))),
        ('abdomen_short',size(a,2)<size(p,2) and size(a,0)<size(p,0),'Abdômen deve ser mais curto e estreito que o peito.'),
        ('vertical_order',center(w,2)<center(a,2)<center(p,2),'Centros Z cintura/abdômen/peito: '+str([center(o,2) for o in [w,a,p]]))]:
        add(key,key,'met' if ok else 'unmet',evidence,'' if ok else 'Corrija proporções e posições, sem adicionar detalhes.')
    return checks


def assess(requirements,raw,geometry,review_issues=()):
    incoming=raw.get('checks',[]) if isinstance(raw,dict) else []
    if not isinstance(incoming,list):
        incoming=[]
    checks=[]
    for r in requirements:
        matches=[x for x in incoming if isinstance(x,dict) and x.get('id')==r['id']]
        item=matches[0] if len(matches)==1 else {}
        valid=item.get('status') in {'met','unmet','uncertain'} and isinstance(item.get('evidence'),str) and bool(item['evidence'].strip()) and isinstance(item.get('correction'),str)
        checks.append({**r,'status':item['status'] if valid else 'uncertain',
            'evidence':item['evidence'] if valid else 'Verificação ausente, duplicada ou sem evidência.',
            'correction':item.get('correction','Verificar este requisito.') if valid else 'Verificar este requisito.',
            'source':'visual_check'})
    checks.extend(geometry)
    # A visual reviewer acknowledging unfinished work cannot silently contradict the checklist.
    for i,issue in enumerate(review_issues):
        if isinstance(issue,str) and issue.strip():
            checks.append({'id':f'review_issue_{i}','requirement':'Pendência apontada na revisão',
                'status':'unmet','evidence':issue,'correction':issue,'source':'review'})
    pending=[c for c in checks if c['status']!='met']
    return {'checks':checks,'pending':pending,'requirements_met':bool(checks) and not pending,
            'human_approved':False}
