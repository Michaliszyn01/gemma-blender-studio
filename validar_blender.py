"""Real render smoke test on the user's machine. No Ollama needed."""
import json
from pathlib import Path
import subprocess
import sys
from core import ROOT, DATA, detect_blender, load_json, save_json


def main():
    settings=load_json(DATA/'settings.json',{})
    executable=sys.argv[1] if len(sys.argv)>1 else settings.get('blender') or detect_blender()
    if not executable:
        executable=input('Cole o caminho do blender.exe (sem aspas): ').strip().strip('"')
    output=DATA/'blender-smoke-test';output.mkdir(parents=True,exist_ok=True)
    save_json(output/'request.json',{'base':None,'output':str(output),'actions':[
        {'op':'box','name':'body','dimensions':[2,1,2],'location':[0,0,2],'color':[0.3,0.4,0.5,1],'bevel':0.08},
        {'op':'mesh','name':'custom_panel','vertices':[[-1,0,0],[1,0,0],[0.8,0,1],[-0.8,0,1]],'faces':[[0,1,2,3]],'location':[0,-0.6,2]},
        {'op':'transform','name':'body','dimensions':[2.2,1,2]},
        {'op':'material','name':'body','metallic':0.3,'roughness':0.6}]})
    cmd=[executable,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(ROOT/'blender_worker.py'),'--',str(output/'request.json')]
    result=subprocess.run(cmd,timeout=300)
    needed=['model.blend','scene.json','front.png','side.png','perspective.png']
    if result.returncode or not all((output/x).exists() for x in needed):raise SystemExit('FALHOU. Confira as mensagens do Blender acima.')
    # Reopen generated blend and update it to verify the incremental path too.
    save_json(output/'request.json',{'base':str(output/'model.blend'),'output':str(output),'actions':[{'op':'transform','name':'body','dimensions':[2,1,2.5]}]})
    result=subprocess.run(cmd,timeout=300)
    if result.returncode:raise SystemExit('FALHOU ao reabrir e editar o .blend.')
    print('OK: criação, malha customizada, material, transformação, salvamento, reabertura e três vistas. Arquivos em:',output)

if __name__=='__main__':main()
