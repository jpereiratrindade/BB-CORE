import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
from bbcore.server import serve

class StubOAuth:
    def scopes(self, token):
        return {'oauth-read': {'bb.read'}, 'oauth-write': {'bb.write'}}.get(token, set())

class OAuthAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=serve('127.0.0.1',0,Path(self.tmp.name)/'db.sqlite','r'*40,'w'*40,oauth=StubOAuth())
        self.server.oauth_resource='https://bb.example.org'
        self.server.oauth_issuer='https://id.example.org'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        self.opener=build_opener(ProxyHandler({}))
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        self.server.archive.db.close();self.tmp.cleanup()
    def call(self,token):
        req=Request(self.url+'/mcp',data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',headers={
            'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
        with self.opener.open(req,timeout=3) as r:return json.load(r)
    def test_read_scope_lists_only_reads(self):
        self.assertEqual(len(self.call('oauth-read')['result']['tools']),3)
        self.assertEqual(len(self.call('oauth-write')['result']['tools']),5)
    def test_invalid_token_rejected(self):
        with self.assertRaises(HTTPError) as e:self.call('invalid')
        self.assertEqual(e.exception.code,401)
        e.exception.close()
    def test_resource_metadata(self):
        with self.opener.open(self.url+'/.well-known/oauth-protected-resource',timeout=3) as r:
            data=json.load(r)
        self.assertEqual(data['resource'],'https://bb.example.org')
        self.assertEqual(data['authorization_servers'],['https://id.example.org'])
