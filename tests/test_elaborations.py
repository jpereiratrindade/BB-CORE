"""Testes da Mesa de Elaboração: persistência independente, HTTP e percurso real."""
import base64
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from bbcore.server import serve
from bbcore.store import Archive, NotFound

READ_TOKEN = 'r' * 40
WRITE_TOKEN = 'w' * 40


class ElaborationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.archive = Archive(Path(self.tmp.name) / 'bb.sqlite')

    def tearDown(self):
        self.archive.db.close()
        self.tmp.cleanup()

    def test_free_elaboration_is_independent_of_canonical_archive(self):
        # Permite rascunho livre sem título, sem tipo e sem confirmação.
        created, is_new = self.archive.elaborations.save({
            'notes': 'Ideia em aberto ainda sem categoria definida.',
            'excerpts': [{
                'receipt_id': 'rec-1',
                'version_id': 'ver-1',
                'label': 'EVAL-01',
                'declared_version': '0.1.0',
                'quote': 'trecho literal',
                'start_byte': 0,
                'end_byte': 14,
            }],
        })
        self.assertTrue(is_new)
        self.assertEqual(created['title'], '')
        self.assertEqual(len(created['excerpts']), 1)

        # Acervo canônico e diário permanecem intocados.
        self.assertEqual(self.archive.list(), [])
        self.assertEqual(self.archive.events.export()['events'], [])
        self.assertEqual(self.archive.verify()['integrity'], 'VERIFIED')

        # Retomada e edição preservam ID.
        updated, is_new_2 = self.archive.elaborations.save({
            'id': created['id'],
            'title': 'Título provisório',
            'notes': created['notes'] + '\nMais reflexão.',
            'excerpts': created['excerpts'],
            'references': [{'insight_id': 'ins-x', 'title': 'Outro registro'}],
        })
        self.assertFalse(is_new_2)
        self.assertEqual(updated['id'], created['id'])
        self.assertEqual(len(self.archive.elaborations.list()), 1)

        # Descarte remove apenas da tabela independente.
        deleted = self.archive.elaborations.delete(created['id'])
        self.assertTrue(deleted['deleted'])
        with self.assertRaises(NotFound):
            self.archive.elaborations.get(created['id'])


class ElaborationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = serve('127.0.0.1', 0, Path(self.tmp.name) / 'bb.sqlite', READ_TOKEN, WRITE_TOKEN)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor())

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, method, path, data=None, token=None, local=True):
        headers = {}
        if local and method != 'GET':
            headers['Origin'] = f'http://127.0.0.1:{self.port}'
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = Request(
            f'http://127.0.0.1:{self.port}{path}',
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
            method=method,
        )
        with self.opener.open(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())

    def test_http_crud_permissions_and_real_investigation_journey(self):
        # 1. Asset /mesa.js servido com CSP compatível e MCP intacto.
        with self.opener.open(f'http://127.0.0.1:{self.port}/mesa.js', timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn('bb-mesa-add-excerpt', resp.read().decode())

        status, mcp_tools = self.call(
            'POST', '/mcp',
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}},
            token=WRITE_TOKEN, local=False,
        )
        self.assertEqual(status, 200)
        tool_names = [t['name'] for t in mcp_tools['result']['tools']]
        self.assertEqual(tool_names, ['capture_insight', 'search_insights', 'get_insight', 'get_context', 'propose_relation'])

        # 2. Sem sessão ou token, POST/DELETE são rejeitados.
        with self.assertRaises(HTTPError) as err:
            self.call('POST', '/api/elaborations', {'notes': 'sem auth'}, local=False)
        self.assertEqual(err.exception.code, 401)
        with self.assertRaises(HTTPError) as err_ro:
            self.call('POST', '/api/elaborations', {'notes': 'só leitura'}, token=READ_TOKEN, local=False)
        self.assertEqual(err_ro.exception.code, 403)

        # 3. Inicia sessão local (como navegador).
        status, _ = self.call('POST', '/api/local-session', {})
        self.assertEqual(status, 200)

        # 4. Percurso real: ingere documento de avaliação do próprio BB-CORE.
        doc_text = (
            'Avaliação BB-CORE\n\n'
            'O diário BB-EVENT-1 detecta adulteração e truncamento, mas sem checkpoint externo '
            'não impede reescrita integral por administrador.\n\n'
            'A ausência de interface de elaboração cria ruptura entre o modelo e o uso cotidiano.\n'
        )
        doc_bytes = doc_text.encode('utf-8')
        _, doc_res = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'avaliacao-bbcore.md',
            'content_base64': base64.b64encode(doc_bytes).decode(),
            'external_id': 'BB-EVAL-01',
            'declared_version': '0.1.0',
            'provenance': 'Avaliação técnica do BB-CORE usada como caso de investigação',
            'received_by': 'Pesquisador local',
            'confirmed': True,
        })

        quote_1 = 'O diário BB-EVENT-1 detecta adulteração e truncamento, mas sem checkpoint externo não impede reescrita integral por administrador.'
        start_1 = doc_bytes.index(quote_1.encode('utf-8'))
        quote_2 = 'A ausência de interface de elaboração cria ruptura entre o modelo e o uso cotidiano.'
        start_2 = doc_bytes.index(quote_2.encode('utf-8'))

        # 5. Salva elaboração livre na Mesa reunindo os dois trechos (sem classificar ainda).
        status, draft = self.call('POST', '/api/elaborations', {
            'title': 'Notas sobre garantias e uso cotidiano do BB-CORE',
            'notes': 'Investigar dois pontos: limite do checkpoint e ruptura na interface.',
            'limitations': 'Análise inicial baseada na revisão interna.',
            'excerpts': [
                {'receipt_id': doc_res['receipt_id'], 'version_id': doc_res['version_id'],
                 'label': 'BB-EVAL-01', 'declared_version': '0.1.0',
                 'quote': quote_1, 'start_byte': start_1, 'end_byte': start_1 + len(quote_1.encode('utf-8'))},
                {'receipt_id': doc_res['receipt_id'], 'version_id': doc_res['version_id'],
                 'label': 'BB-EVAL-01', 'declared_version': '0.1.0',
                 'quote': quote_2, 'start_byte': start_2, 'end_byte': start_2 + len(quote_2.encode('utf-8'))},
            ],
        })
        self.assertEqual(status, 201)

        # 6. Confirma primeiro resultado (achado conceitual inicial) a partir do primeiro trecho.
        status, rec = self.call('POST', '/api/document-records', {
            'request_id': str(uuid.uuid4()),
            'title': 'Alcance das garantias do diário BB-EVENT-1',
            'claim': 'O diário é à prova de mentira local.',
            'why_matters': 'Explicitar limites criptográficos.',
            'genesis': {'elaboration': 'Extraído da Mesa'},
            'limitations': 'Formulação inicial provisória.',
            'kind': 'CONCEPTUAL_FINDING',
            'work_state': 'PROPOSED',
            'formulation_origin': 'HUMAN_FORMULATION',
            'confirmed_by_declared': 'Pesquisador local',
            'confirmed': True,
            'anchors': [{
                'receipt_id': doc_res['receipt_id'],
                'quote': quote_1,
                'start_byte': start_1,
                'end_byte': start_1 + len(quote_1.encode('utf-8')),
                'role': 'documentary_support',
            }],
        })
        self.assertEqual(status, 201)

        # 7. Registra crítica externa e depois reformulação assumida mantendo identidade.
        status, _ = self.call('POST', '/api/events', {
            'request_id': str(uuid.uuid4()),
            'insight_id': rec['id'],
            'event_type': 'CRITIQUE_RECORDED',
            'mode': 'REPORTED',
            'origin': 'Revisão conceitual',
            'responsible': {'id': 'local:revisor', 'name': 'Revisor'},
            'content': {'summary': 'Chamar de "à prova de mentira" exagera a garantia criptográfica.'},
            'evidence': [{'kind': 'receipt', 'id': doc_res['receipt_id'], 'role': 'critique_basis'}],
            'limitations': 'Crítica externa não altera a formulação por si só.',
            'confirmed': True,
        })
        self.assertEqual(status, 201)

        status, _ = self.call('POST', '/api/events', {
            'request_id': str(uuid.uuid4()),
            'insight_id': rec['id'],
            'event_type': 'FORMULATION_REVISED',
            'mode': 'OBSERVED',
            'origin': 'Mesa de Elaboração',
            'responsible': {'id': 'local:pesquisador', 'name': 'Pesquisador local'},
            'content': {
                'summary': 'Refina formulação após crítica, mantendo identidade.',
                'changes': {'claim': quote_1},
            },
            'evidence': [{'kind': 'receipt', 'id': doc_res['receipt_id'], 'role': 'revision_basis'}],
            'limitations': 'Depende de checkpoint externo independente.',
            'confirmed': True,
        })
        self.assertEqual(status, 201)

        # 8. Elaboração restante continua preservada na Mesa após confirmações!
        status, still_there = self.call('GET', f"/api/elaborations/{draft['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(len(still_there['excerpts']), 2)

        # 9. Trajetória preserva formulação original e apresenta a corrente.
        status, traj = self.call('GET', f"/api/insights/{rec['id']}/trajectory")
        self.assertEqual(status, 200)
        self.assertEqual(traj['formulation_revision_count'], 1)
        self.assertEqual(traj['current_state']['claim'], quote_1)
        self.assertEqual(traj['baseline']['record']['claim'], 'O diário é à prova de mentira local.')

        # 10. Descarte manual da elaboração funciona.
        status, del_res = self.call('DELETE', f"/api/elaborations/{draft['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(del_res['deleted'])
