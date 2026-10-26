"""Local browser panel. Run python app.py; bound only to 127.0.0.1."""
import base64
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import webbrowser
from PIL import Image, ImageOps
from core import ROOT, DATA, Studio, default_settings, load_json, ollama

TOKEN=secrets.token_urlsafe(32)
studio=None


def upload_image(encoded):
    raw=base64.b64decode(encoded,validate=True)
    if len(raw)>15*1024*1024:raise ValueError('Imagem excede 15 MB.')
    with Image.open(io.BytesIO(raw)) as im:
        if im.width*im.height>32_000_000:raise ValueError('Imagem excede 32 megapixels.')
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((1600,1600))
        path=DATA/'reference-upload.png';im.save(path)
    return str(path)


def public_state():
    state=studio.snapshot()
    def file_url(path):
        from urllib.parse import quote
        p=Path(path).resolve()
        if not p.is_relative_to(DATA.resolve()):return None
        return '/file?path='+quote(str(p.relative_to(DATA.resolve())))
    for key in ['preview','candidate']:
        if state.get(key):state[key]=file_url(state[key])
    if state.get('accepted'):state['download']=file_url(state['accepted'])
    if state.get('job'):
        state['reference_url']=file_url(Path(state['job'])/'reference.png')
    if state.get('status')=='awaiting_approval' and state.get('accepted'):
        state['approval_digest']=hashlib.sha256(Path(state['accepted']).read_bytes()).hexdigest()
    for entry in state.get('history',[]):
        entry['preview']=file_url(entry['preview']);entry['download']=file_url(entry['model'])
    return state


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,value,status=200,mime='application/json'):
        if mime=='application/json':value=json.dumps(value,ensure_ascii=False).encode()
        if isinstance(value,str):value=value.encode()
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(value)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(value)
    def host_ok(self):
        host=self.headers.get('Host','')
        return host in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
    def do_GET(self):
        if not self.host_ok():return self.send({'error':'Host inválido'},403)
        parsed=urlparse(self.path)
        try:
            if parsed.path=='/api/state':return self.send(public_state())
            if parsed.path=='/api/bootstrap':return self.send({'token':TOKEN,'settings':load_json(DATA/'settings.json',default_settings()),'assets':len(studio.catalog)})
            if parsed.path=='/file':
                p=(DATA/parse_qs(parsed.query).get('path',[''])[0]).resolve()
                if not p.is_relative_to(DATA.resolve()) or p.suffix not in {'.png','.blend','.json','.log'} or not p.is_file():return self.send({'error':'Arquivo indisponível'},404)
                return self.send(p.read_bytes(),mime=mimetypes.guess_type(str(p))[0] or 'application/octet-stream')
            static={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if parsed.path in static:
                p=ROOT/'web'/static[parsed.path]
                return self.send(p.read_bytes(),mime=mimetypes.guess_type(str(p))[0] or 'text/plain')
            self.send({'error':'Não encontrado'},404)
        except Exception as e:self.send({'error':str(e)},400)
    def do_POST(self):
        if not self.host_ok() or self.headers.get('X-Studio-Token')!=TOKEN:return self.send({'error':'Sessão inválida. Recarregue a página.'},403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<280*1024*1024:raise ValueError('Tamanho de requisição inválido.')
            data=json.loads(self.rfile.read(size))
            if self.path=='/api/models':
                response=ollama(data['url'],'/api/tags')
                return self.send({'models':[m['name'] for m in response.get('models',[])]})
            if self.path=='/api/check':
                config=data['config']
                info=ollama(config['ollama_url'],'/api/show',{'model':config['model']})
                path=Path(config['blender'])
                if not path.is_file():raise ValueError('Executável do Blender não encontrado.')
                result=subprocess.run([str(path),'--version'],capture_output=True,text=True,timeout=15)
                if result.returncode or 'Blender' not in result.stdout:raise ValueError('O caminho não retornou uma versão válida do Blender.')
                return self.send({'vision':'vision' in info.get('capabilities',[]),'blender':result.stdout.splitlines()[0],'capabilities':info.get('capabilities',[])})
            if self.path=='/api/start':
                busy=studio.thread and studio.thread.is_alive()
                if busy:raise ValueError('Pare a sessão atual antes de iniciar outra.')
                config=data['config'];resume=bool(data.get('resume'))
                reference=None;source=None
                if not resume:
                    reference=upload_image(data['image'])
                    if data.get('blend'):
                        raw=base64.b64decode(data['blend'],validate=True)
                        if len(raw)>180*1024*1024 or not raw.startswith(b'BLENDER'):raise ValueError('Envie um .blend descomprimido válido de até 180 MB. Abra e salve sem compressão no Blender, se necessário.')
                        source=DATA/'source-upload.blend';source.write_bytes(raw)
                studio.start(config,reference,data.get('prompt',''),source,resume)
                return self.send(public_state())
            if self.path=='/api/stop':studio.stop();return self.send(public_state())
            if self.path=='/api/approve':
                studio.approve(data.get('model'),data.get('sha256'))
                return self.send(public_state())
            if self.path=='/api/open':
                accepted=studio.snapshot().get('accepted')
                if not accepted or not Path(accepted).is_file():raise ValueError('Ainda não existe versão aceita.')
                config=load_json(DATA/'settings.json',default_settings())
                subprocess.Popen([config['blender'],'--disable-autoexec',accepted])
                return self.send({'ok':True})
            self.send({'error':'Não encontrado'},404)
        except Exception as e:self.send({'error':str(e)},400)


def main():
    global studio
    studio=Studio()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    address=f'http://127.0.0.1:{server.server_port}'
    print('Gemma Blender Studio:',address,flush=True)
    print('Mantenha esta janela aberta. Ctrl+C encerra o aplicativo.',flush=True)
    if '--no-browser' not in sys.argv:threading.Timer(0.7,lambda:webbrowser.open(address)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:studio.stop()
    finally:server.server_close()

if __name__=='__main__':main()
