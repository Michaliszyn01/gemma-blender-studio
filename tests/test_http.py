import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import core

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.data_patch=patch.object(app,'DATA',self.root);self.data_patch.start()
        with patch.object(core,'ROOT',self.root):app.studio=core.Studio(self.root)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.data_patch.stop();self.temp.cleanup()
    def test_bootstrap_and_panel(self):
        with urllib.request.urlopen(self.url+'/api/bootstrap') as r:data=json.load(r)
        self.assertEqual(data['token'],app.TOKEN)
        with urllib.request.urlopen(self.url) as r:self.assertIn('Adicionar referência',r.read().decode())
    def test_rejects_cross_origin_post_and_path_escape(self):
        req=urllib.request.Request(self.url+'/api/stop',data=b'{}',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
        self.assertEqual(e.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(self.url+'/file?path=../core.py')
        self.assertEqual(e.exception.code,404)
    def test_authenticated_stop(self):
        req=urllib.request.Request(self.url+'/api/stop',data=b'{}',headers={'X-Studio-Token':app.TOKEN})
        with urllib.request.urlopen(req) as r:self.assertEqual(json.load(r)['status'],'idle')

if __name__=='__main__':unittest.main()
