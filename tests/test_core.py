import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from bbcore.store import Archive, Conflict
from bbcore.server import serve

READ = "r" * 48
WRITE = "w" * 48

def capsule():
    return {
      "request_id": str(uuid.uuid4()),
      "title": "Memória não é sinônimo de conclusão",
      "claim": "Um insight exige preservar as condições de sua compreensão",
      "why_matters": "Permite reconstrução crítica em investigações futuras",
      "genesis": {"trigger":"Debate sobre memória", "prior_assumption":None,
                  "turning_point":"Exigência de contexto verificável"},
      "context": {"coverage":"PARTIAL_DIALOGUE", "missing":["Transcrição integral"]},
      "limitations": "A fala original completa não foi fornecida e autoria não autenticada",
      "sharing":"PRIVATE",
      "sources":[{"text":"O insight deve preservar o contexto que o tornou compreensível.",
                  "quote":"preservar o contexto", "origin":"dialogo-fornecido",
                  "coverage":"LITERAL_EXCERPT", "role":"trigger", "author":"user"}]
    }

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Archive(Path(self.tmp.name)/"bb.sqlite")

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_capture_recover_verify_and_idempotency(self):
        c=capsule()
        out=self.store.capture(c)
        self.assertEqual(out,self.store.capture(c))
        ctx=self.store.context(out["id"])
        self.assertEqual(ctx["integrity"],"VERIFIED_LOCAL_BYTES")
        self.assertEqual(ctx["sources"][0]["body"],c["sources"][0]["text"])
        self.assertEqual(ctx["sources"][0]["quote"],"preservar o contexto")
        self.assertEqual(self.store.verify()["integrity"],"VERIFIED")
        self.assertEqual(len(self.store.list()),1)

    def test_conflicting_retry_is_rejected(self):
        c=capsule();self.store.capture(c)
        c["claim"]="Outro conteúdo"
        with self.assertRaises(Conflict):self.store.capture(c)

    def test_missing_literal_quote_is_rejected(self):
        c=capsule();c["sources"][0]["quote"]="texto inventado"
        with self.assertRaises(ValueError):self.store.capture(c)
        self.assertEqual(self.store.list(),[])

    def test_relate_is_candidate_not_causal(self):
        a=self.store.capture(capsule())["id"]
        b=self.store.capture(capsule())["id"]
        self.assertNotEqual(a,b)
        inp={"request_id":str(uuid.uuid4()),"left_id":a,"right_id":b,
             "rationale":"Ambos discutem proveniência", "counterpoint":"Mesmo conceito não comprova influência"}
        out=self.store.relate(inp)
        self.assertEqual(out,self.store.relate(inp))
        self.assertEqual(out["status"],"INFERRED_CANDIDATE")
        self.assertEqual(len(self.store.get(a)["relations"]),1)

    def test_search(self):
        self.store.capture(capsule())
        self.assertEqual(len(self.store.search("contexto")),0)
        self.assertEqual(len(self.store.search("memória")),1)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=serve("127.0.0.1",0,Path(self.tmp.name)/"bb.sqlite",READ,WRITE)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_port}"
        # Evita proxies institucionais nos testes HTTP de loopback.
        from urllib.request import build_opener, ProxyHandler
        self.direct_http=build_opener(ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        self.server.archive.db.close();self.tmp.cleanup()

    def post(self,path,body,token=WRITE):
        r=Request(self.base+path,data=json.dumps(body).encode(),headers={
          "Authorization":"Bearer "+token,"Content-Type":"application/json",
          "Accept":"application/json, text/event-stream"},method="POST")
        with self.direct_http.open(r,timeout=4) as f:return f.status,json.load(f)

    def get(self,path,token=READ):
        r=Request(self.base+path,headers={"Authorization":"Bearer "+token})
        with self.direct_http.open(r,timeout=4) as f:return json.load(f)

    def test_mcp_initialize_discover_capture_search_recover(self):
        status,init=self.post("/mcp",{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
        self.assertEqual(status,200)
        self.assertEqual(init["result"]["serverInfo"]["name"],"bb-core")
        _,listed=self.post("/mcp",{"jsonrpc":"2.0","id":2,"method":"tools/list"})
        self.assertEqual(len(listed["result"]["tools"]),5)
        _,read_only=self.post("/mcp",{"jsonrpc":"2.0","id":2,"method":"tools/list"},READ)
        self.assertEqual(len(read_only["result"]["tools"]),3)
        payload=capsule()
        _,captured=self.post("/mcp",{"jsonrpc":"2.0","id":3,"method":"tools/call",
                                      "params":{"name":"capture_insight","arguments":payload}})
        self.assertFalse(captured["result"]["isError"])
        iid=json.loads(captured["result"]["content"][0]["text"])["id"]
        _,recovered=self.post("/mcp",{"jsonrpc":"2.0","id":4,"method":"tools/call",
                                       "params":{"name":"get_context","arguments":{"id":iid}}},READ)
        data=json.loads(recovered["result"]["content"][0]["text"])
        self.assertEqual(data["integrity"],"VERIFIED_LOCAL_BYTES")
        self.assertEqual(data["context"]["missing"],["Transcrição integral"])
        self.assertEqual(len(self.get("/api/insights" )["items"]),1)

    def test_write_requires_write_token(self):
        with self.assertRaises(HTTPError) as err:
            self.post("/api/insights",capsule(),READ)
        self.assertEqual(err.exception.code,403)
        _,denied=self.post("/mcp",{"jsonrpc":"2.0","id":1,"method":"tools/call",
                                   "params":{"name":"capture_insight","arguments":capsule()}},READ)
        self.assertTrue(denied["result"]["isError"])

    def test_cross_origin_rejected(self):
        r=Request(self.base+"/api/insights",headers={"Authorization":"Bearer "+READ,
                                                     "Origin":"https://evil.example"})
        with self.assertRaises(HTTPError) as err:self.direct_http.open(r,timeout=4)
        self.assertEqual(err.exception.code,403)

if __name__=="__main__":unittest.main()
