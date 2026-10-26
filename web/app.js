const $=id=>document.getElementById(id);let token='',state={},selected=false,lastEvents='',lastHistory='',imageURL='';
const fields=['ollama_url','model','blender','iterations','hours','context','timeout'];
const labels={idle:'Pronto',running:'Trabalhando',stopping:'Parando',stopped:'Parado',interrupted:'Interrompido',completed:'Sessão antiga — não aprovada',pending:'Encerrada com pendências',awaiting_approval:'Aguardando sua aprovação',approved:'Aprovado por você',error:'Precisa de atenção'};
const phases={planning:'Planejando ajustes',building:'Construindo e renderizando',reviewing:'Inspecionando candidato',checking:'Verificando requisitos',done:'Sessão encerrada'};
function config(){return Object.fromEntries(fields.map(k=>[k,$(k).value]));}
function notice(msg){$('notice').textContent=msg;$('notice').hidden=!msg;}
async function api(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json','X-Studio-Token':token}:{},body:data?JSON.stringify(data):undefined});const v=await r.json();if(!r.ok)throw new Error(v.error||'Falha na conexão.');return v;}
async function models(){const old=$('model').value;const result=await api('/api/models',{url:$('ollama_url').value});$('model').replaceChildren();for(const name of result.models){const o=document.createElement('option');o.value=name;o.textContent=name;$('model').append(o);}if(result.models.includes(old))$('model').value=old;if(!result.models.length)throw new Error('Nenhum modelo instalado no Ollama. Instale uma variante com visão.');}
function readFile(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=()=>reject(new Error('Não foi possível ler o arquivo.'));r.readAsDataURL(file);});}
function showRender(url,label){if(!url)return;$('empty').hidden=true;$('render').hidden=false;$('render').src=url;$('renderLabel').hidden=false;$('renderLabel').textContent=label;}
function render(s){state=s;const busy=['running','stopping'].includes(s.status);$('status').textContent=labels[s.status]||s.status;$('phase').textContent=s.phase==='done'?s.message:(phases[s.phase]||s.message);renderRequirements(s);$('iteration').textContent=s.iteration?'Rodada '+s.iteration:'Nenhuma rodada iniciada';$('start').disabled=busy;$('resume').disabled=busy||!s.job;$('stop').disabled=!busy||s.status==='stopping';$('open').disabled=!s.accepted;$('download').hidden=!s.download;if(s.download)$('download').href=s.download;if(s.preview&&!selected)showRender(s.preview,'ÚLTIMA VERSÃO INTERMEDIÁRIA');const es=JSON.stringify(s.events);if(es!==lastEvents){lastEvents=es;$('events').replaceChildren();for(const e of s.events||[]){const row=document.createElement('div');row.className='event';const time=document.createElement('time');time.textContent=e.time;const text=document.createElement('span');text.textContent=e.message;row.append(time,text);$('events').append(row);}$('events').scrollTop=$('events').scrollHeight;}
const hs=JSON.stringify(s.history);if(hs!==lastHistory){lastHistory=hs;$('history').replaceChildren();for(const h of [...(s.history||[])].reverse()){const b=document.createElement('button');b.className='version '+(h.accepted?'accepted':'rejected');const title=document.createElement('strong');title.textContent='Rodada '+h.iteration+' · '+(h.accepted?'Intermediária aceita':'Rejeitada');const detail=document.createElement('small');detail.textContent='Opinião do modelo: '+h.score+'/100 · '+h.reason;b.append(title,detail);b.onclick=()=>{selected=true;$('approveFinal').disabled=true;showRender(h.preview,'CANDIDATO DA RODADA '+h.iteration+(h.accepted?' · ACEITO':' · REJEITADO'));};$('history').append(b);}}
if(['error','pending','awaiting_approval'].includes(s.status))notice(s.message);}
async function launch(resume){notice('');$('start').disabled=true;try{let data={config:config(),resume,prompt:$('prompt').value};if(!resume){const image=$('reference').files[0];if(!image)throw new Error('Escolha a imagem de referência.');if(image.size>15*1024*1024)throw new Error('Imagem excede 15 MB.');if(!data.prompt.trim())throw new Error('Descreva o modelo desejado.');data.image=await readFile(image);const blend=$('blend').files[0];if(blend){if(blend.size>180*1024*1024)throw new Error('.blend excede 180 MB.');data.blend=await readFile(blend);}}selected=false;render(await api('/api/start',data));}catch(e){notice(e.message);$('start').disabled=false;}}
$('reference').onchange=()=>{const f=$('reference').files[0];if(!f)return;if(imageURL)URL.revokeObjectURL(imageURL);imageURL=URL.createObjectURL(f);$('referencePreview').src=imageURL;$('referencePreview').hidden=false;$('uploadHint').hidden=true;};
$('settingsToggle').onclick=()=>$('settings').showModal();$('start').onclick=()=>launch(false);$('resume').onclick=()=>launch(true);$('stop').onclick=async()=>{try{render(await api('/api/stop',{}));}catch(e){notice(e.message);}};$('latest').onclick=()=>{selected=false;renderRequirements(state);if(state.preview)showRender(state.preview,'ÚLTIMA VERSÃO INTERMEDIÁRIA');};$('models').onclick=async()=>{try{await models();$('connectionResult').textContent='Lista atualizada.';}catch(e){$('connectionResult').textContent=e.message;}};$('check').onclick=async()=>{$('connectionResult').textContent='Testando…';try{const r=await api('/api/check',{config:config()});$('connectionResult').textContent=r.blender+'\n'+(r.vision?'Modelo com visão disponível. Pronto para iniciar.':'Este modelo não anuncia visão. Escolha uma variante multimodal.');}catch(e){$('connectionResult').textContent=e.message;}};$('open').onclick=async()=>{try{await api('/api/open',{});}catch(e){notice(e.message);}};
async function init(){try{const b=await api('/api/bootstrap');token=b.token;for(const k of fields){if(k==='model'){const o=document.createElement('option');o.value=b.settings[k]||'';o.textContent=b.settings[k]||'Selecione um modelo';$('model').replaceChildren(o);}else if(b.settings[k]!==undefined)$(k).value=b.settings[k];}$('assetCount').textContent='Factory Kit · '+b.assets+' modelos';try{await models();}catch(e){notice(e.message);}render(await api('/api/state'));if(!b.settings.model||!b.settings.blender)$('settings').showModal();}catch(e){notice(e.message);}}

// The stored session reference is shown beside the selected render.
const comparison=document.createElement('div');comparison.className='comparison';
const canvas=document.querySelector('.canvas');canvas.before(comparison);
const referenceFigure=document.createElement('figure');referenceFigure.className='referenceFigure';
const caption=document.createElement('figcaption');caption.textContent='REFERÊNCIA DA SESSÃO';
const comparisonImage=document.createElement('img');comparisonImage.id='comparisonReference';comparisonImage.alt='Referência original da sessão';
referenceFigure.append(caption,comparisonImage);comparison.append(referenceFigure,canvas);
const requirementsPanel=document.createElement('section');requirementsPanel.className='requirementsPanel';
const requirementsTitle=document.createElement('h3');requirementsTitle.textContent='Requisitos e aprovação final';
const requirementsSummary=document.createElement('p');requirementsSummary.id='requirementsSummary';
const requirementsList=document.createElement('div');requirementsList.id='requirementsList';
const approveButton=document.createElement('button');approveButton.id='approveFinal';approveButton.className='primary';approveButton.textContent='Aprovar resultado final';approveButton.disabled=true;
requirementsPanel.append(requirementsTitle,requirementsSummary,requirementsList,approveButton);
document.querySelector('.toolbar').after(requirementsPanel);
let lastRequirements='';
function renderRequirements(s){
 if(s.reference_url&&comparisonImage.getAttribute('src')!==s.reference_url)comparisonImage.src=s.reference_url;
 approveButton.disabled=s.status!=='awaiting_approval'||selected;
 requirementsSummary.textContent=s.status==='approved'?'Aprovação final registrada por você.':s.status==='awaiting_approval'?'Verificação sem pendências. Compare as imagens e decida se aprova.':'Aceitar uma versão intermediária não conclui o pedido. Pendências orientam as próximas rodadas.';
 const rows=s.assessment?.checks||[];const signature=JSON.stringify(rows);
 if(signature!==lastRequirements){lastRequirements=signature;requirementsList.replaceChildren();
 for(const c of rows){const item=document.createElement('details');const title=document.createElement('summary');
 title.textContent=({met:'Verificado',unmet:'Pendente',uncertain:'Não comprovado'}[c.status]||c.status)+' · '+c.requirement;
 const evidence=document.createElement('p');evidence.textContent=c.evidence+(c.correction?' Correção: '+c.correction:'');
 item.append(title,evidence);requirementsList.append(item);}}
}
approveButton.onclick=async()=>{try{render(await api('/api/approve',{model:state.accepted,sha256:state.approval_digest}));notice('Resultado aprovado por você.');}catch(e){notice(e.message);}};
document.querySelector('.footnote').textContent='A nota do modelo não encerra a tarefa. Requisitos e pendências são verificados separadamente. A aprovação final é sua.';

init();setInterval(async()=>{try{render(await api('/api/state'));}catch(e){notice('Aplicativo desconectado. Verifique a janela do servidor e recarregue a página.');}},2500);
