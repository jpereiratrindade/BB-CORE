"""Testes do interpretador determinístico de Markdown parametrizado (BB-CORE-ING-0.2.0)."""
import base64
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from bbcore.parametrized import (
    MAX_FRONTMATTER_BYTES,
    ParametrizedError,
    parse_parametrized_markdown,
)
from bbcore.server import serve

REF_DOC = Path(__file__).resolve().parents[1] / 'docs/reference/BB-CORE-INSIGHT-001.parametrized.md'


class ParametrizedTests(unittest.TestCase):
    def test_reference_document_is_deterministic_and_anchors_exact_utf8_bytes(self):
        raw = REF_DOC.read_bytes()
        first = parse_parametrized_markdown(raw)
        second = parse_parametrized_markdown(raw)
        self.assertEqual(first, second)
        self.assertEqual(first['schema'], 'BB-CORE-ING-0.2.0')
        self.assertEqual(first['state'], 'INTERPRETED')
        self.assertEqual(first['byte_length'], len(raw))
        self.assertEqual(first['document']['external_id'], 'BB-CORE-INSIGHT-001')
        self.assertEqual(len(first['records']), 1)

        rec = first['records'][0]
        self.assertEqual(rec['external_record_id'], 'BB-CORE-INSIGHT-001:achado-elaboracao-vs-preservacao')
        self.assertEqual(rec['kind'], 'CONCEPTUAL_FINDING')
        self.assertEqual(rec['work_state'], 'PROPOSED')
        self.assertEqual(rec['formulation_origin'], 'DOCUMENT_EXCERPT')
        self.assertEqual(len(rec['anchors']), 4)
        for anchor in rec['anchors']:
            self.assertEqual(
                raw[anchor['start_byte']:anchor['end_byte']].decode('utf-8'),
                anchor['quote'],
            )

    def test_zero_records_and_multiple_records_with_bom_crlf_and_ai_origin(self):
        zero_doc = (
            '---\nschema: "BB-CORE-ING-0.2.0"\ndocument:\n  external_id: "CTX-01"\n'
            '  provenance: "Documento apenas de contexto"\nrecords: []\n---\n\nTexto livre.\n'
        ).encode('utf-8')
        parsed_zero = parse_parametrized_markdown(zero_doc)
        self.assertEqual(parsed_zero['records'], [])

        multi_text = (
            '\ufeff---\r\n'
            'schema: "BB-CORE-ING-0.2.0"\r\n'
            'document:\r\n'
            '  external_id: "MULTI-01"\r\n'
            '  version: "0.1.0"\r\n'
            '  declared_date: 2026-11-24\r\n'
            'records:\r\n'
            '  - id_local: "r1"\r\n'
            '    kind: "METHODOLOGICAL_DECISION"\r\n'
            '    work_state: "ADOPTED"\r\n'
            '    title: "Decisão A"\r\n'
            '    formulation_origin: "DOCUMENT_EXCERPT"\r\n'
            '    claim_section: "Decisão"\r\n'
            '    why_matters: "Relevância"\r\n'
            '    limitations: "Limites"\r\n'
            '    attribution:\r\n'
            '      external_tool: "ChatGPT"\r\n'
            '      ai_assisted: true\r\n'
            '  - id_local: "r2"\r\n'
            '    kind: "OPEN_QUESTION"\r\n'
            '    work_state: "OPEN"\r\n'
            '    title: "Questão B"\r\n'
            '    formulation_origin: "DOCUMENT_EXCERPT"\r\n'
            '    claim_section: "Questão"\r\n'
            '    why_matters: "Relevância"\r\n'
            '    limitations: "Limites"\r\n'
            '---\r\n\r\n'
            '## Decisão\r\n\r\nUsar PyYAML estrito.\r\n\r\n'
            '## Questão\r\n\r\nComo validar reimportações?\r\n'
        )
        raw_multi = multi_text.encode('utf-8')
        parsed = parse_parametrized_markdown(raw_multi)
        self.assertEqual(len(parsed['records']), 2)
        self.assertEqual(parsed['records'][0]['formulation_origin'], 'DOCUMENT_EXCERPT')
        self.assertTrue(parsed['records'][0]['attribution']['ai_assisted'])
        self.assertNotEqual(parsed['records'][0]['claim_sha256'], parsed['records'][0]['content_sha256'])
        self.assertEqual(parsed['records'][0]['declared_relations'], [])
        for rec in parsed['records']:
            a = rec['anchors'][0]
            self.assertEqual(raw_multi[a['start_byte']:a['end_byte']].decode('utf-8'), a['quote'])

    def test_rejects_invalid_yaml_contracts_and_ambiguities(self):
        cases = [
            # Sem front matter
            b'# Apenas markdown\n',
            # Front matter sem fechamento
            b'---\nschema: "BB-CORE-ING-0.2.0"\n',
            # Chave duplicada
            b'---\nschema: "BB-CORE-ING-0.2.0"\nschema: "BB-CORE-ING-0.2.0"\ndocument: {}\nrecords: []\n---\ntexto\n',
            # Campo desconhecido
            b'---\nschema: "BB-CORE-ING-0.2.0"\ndocument: {}\nrecords: []\nextra: 1\n---\ntexto\n',
            # Versão incompatível
            b'---\nschema: "BB-CORE-ING-9.9.9"\ndocument: {}\nrecords: []\n---\ntexto\n',
            # Aliases YAML
            b'---\nschema: "BB-CORE-ING-0.2.0"\ndocument:\n  provenance: &a "x"\n  external_id: *a\nrecords: []\n---\ntexto\n',
            # Tag YAML arbitrária
            b'---\nschema: "BB-CORE-ING-0.2.0"\ndocument:\n  provenance: !!python/object/apply:os.system ["echo"]\nrecords: []\n---\ntexto\n',
            # NaN
            b'---\nschema: "BB-CORE-ING-0.2.0"\ndocument:\n  external_id: .nan\nrecords: []\n---\ntexto\n',
            # Seção ausente
            (
                '---\nschema: "BB-CORE-ING-0.2.0"\ndocument: {}\nrecords:\n'
                '  - id_local: "r1"\n    kind: "OPEN_QUESTION"\n    work_state: "OPEN"\n'
                '    title: "T"\n    formulation_origin: "DOCUMENT_EXCERPT"\n'
                '    claim_section: "Inexistente"\n    why_matters: "W"\n    limitations: "L"\n'
                '---\n\n## Outra\n\nTexto\n'
            ).encode('utf-8'),
            # Seção ambígua (duas ocorrências)
            (
                '---\nschema: "BB-CORE-ING-0.2.0"\ndocument: {}\nrecords:\n'
                '  - id_local: "r1"\n    kind: "OPEN_QUESTION"\n    work_state: "OPEN"\n'
                '    title: "T"\n    formulation_origin: "DOCUMENT_EXCERPT"\n'
                '    claim_section: "Mesma"\n    why_matters: "W"\n    limitations: "L"\n'
                '---\n\n## Mesma\n\nUm\n\n## Mesma\n\nDois\n'
            ).encode('utf-8'),
            # Front matter acima do limite
            b'---\nschema: "BB-CORE-ING-0.2.0"\ndocument:\n  provenance: "' + (b'a' * (MAX_FRONTMATTER_BYTES + 10)) + b'"\nrecords: []\n---\ntexto\n',
        ]
        for payload in cases:
            with self.subTest(payload=payload[:60]):
                with self.assertRaises(ParametrizedError):
                    parse_parametrized_markdown(payload)


class ParametrizedHTTPFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.read_token = 'r' * 40
        self.write_token = 'w' * 40
        self.server = serve('127.0.0.1', 0, Path(self.tmp.name) / 'bb.sqlite', self.read_token, self.write_token)
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

    def test_receive_examine_selective_confirm_reimport_and_divergence(self):
        self.call('POST', '/api/local-session', {})

        doc_v1 = (
            '---\n'
            'schema: "BB-CORE-ING-0.2.0"\n'
            'document:\n'
            '  external_id: "DOC-MULTI"\n'
            '  version: "0.1.0"\n'
            '  provenance: "Discussão no ChatGPT"\n'
            'records:\n'
            '  - id_local: "rec-a"\n'
            '    kind: "CONCEPTUAL_FINDING"\n'
            '    work_state: "PROPOSED"\n'
            '    title: "Achado A"\n'
            '    formulation_origin: "DOCUMENT_EXCERPT"\n'
            '    claim_section: "Achado A"\n'
            '    why_matters: "Importante"\n'
            '    limitations: "Provisório"\n'
            '  - id_local: "rec-b"\n'
            '    kind: "OPEN_QUESTION"\n'
            '    work_state: "OPEN"\n'
            '    title: "Questão B"\n'
            '    formulation_origin: "DOCUMENT_EXCERPT"\n'
            '    claim_section: "Questão B"\n'
            '    why_matters: "Em aberto"\n'
            '    limitations: "Sem dados"\n'
            '---\n\n'
            '## Achado A\n\nFormulação original do achado A.\n\n'
            '## Questão B\n\nPergunta aberta B.\n'
        ).encode('utf-8')

        # 1. Pré-inspeção sem gravar.
        status, pre = self.call('POST', '/api/documents/inspect', {'content_base64': base64.b64encode(doc_v1).decode()})
        self.assertEqual(status, 200)
        self.assertTrue(pre['is_parametrized'])
        self.assertEqual(len(pre['records']), 2)
        self.assertEqual(self.server.archive.list(), [])

        # 2. Recebimento e exame.
        _, rec1 = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'multi.md',
            'content_base64': base64.b64encode(doc_v1).decode(),
            'external_id': 'DOC-MULTI',
            'declared_version': '0.1.0',
            'provenance': 'Discussão no ChatGPT',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        _, inspected = self.call('GET', f"/api/documents/{rec1['version_id']}/parametrized")
        self.assertEqual(inspected['records'][0]['archive_status'], 'NEW_CANDIDATE')
        self.assertEqual(inspected['records'][1]['archive_status'], 'NEW_CANDIDATE')

        # 3. Confirmação seletiva apenas do primeiro registro (rec-a).
        cand_a = inspected['records'][0]
        status, confirmed_a = self.call('POST', '/api/document-records', {
            'request_id': str(uuid.uuid4()),
            'title': cand_a['title'],
            'claim': cand_a['claim'],
            'why_matters': cand_a['why_matters'],
            'genesis': cand_a['genesis'],
            'limitations': cand_a['limitations'],
            'kind': cand_a['kind'],
            'work_state': cand_a['work_state'],
            'formulation_origin': cand_a['formulation_origin'],
            'confirmed_by_declared': 'Pesquisador',
            'confirmed': True,
            'declared_record_key': cand_a['external_record_id'],
            'content_sha256': cand_a['content_sha256'],
            'context': {'external_document_id': 'DOC-MULTI', 'document_version': '0.1.0'},
            'anchors': [{'receipt_id': rec1['receipt_id'], **cand_a['anchors'][0]}],
        })
        self.assertEqual(status, 201)

        # 4. Reimportação do mesmo documento (novo request_id) não duplica.
        _, rec_again = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'multi.md',
            'content_base64': base64.b64encode(doc_v1).decode(),
            'external_id': 'DOC-MULTI',
            'declared_version': '0.1.0',
            'provenance': 'Reimportação',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        self.assertEqual(rec_again['outcome'], 'RECEIVED_AGAIN')
        _, inspected_again = self.call('GET', f"/api/documents/{rec_again['version_id']}/parametrized")
        self.assertEqual(inspected_again['records'][0]['archive_status'], 'ALREADY_CONFIRMED')
        self.assertEqual(inspected_again['records'][0]['existing_insight_id'], confirmed_a['id'])
        self.assertEqual(inspected_again['records'][1]['archive_status'], 'NEW_CANDIDATE')

        with self.assertRaises(HTTPError) as dup_err:
            self.call('POST', '/api/document-records', {
                'request_id': str(uuid.uuid4()),
                'title': cand_a['title'],
                'claim': cand_a['claim'],
                'why_matters': cand_a['why_matters'],
                'genesis': cand_a['genesis'],
                'limitations': cand_a['limitations'],
                'kind': cand_a['kind'],
                'work_state': cand_a['work_state'],
                'formulation_origin': cand_a['formulation_origin'],
                'confirmed_by_declared': 'Pesquisador',
                'confirmed': True,
                'declared_record_key': cand_a['external_record_id'],
                'content_sha256': cand_a['content_sha256'],
                'anchors': [{'receipt_id': rec_again['receipt_id'], **cand_a['anchors'][0]}],
            })
        self.assertEqual(dup_err.exception.code, 409)

        # 5. Nova versão com formulação divergente sinaliza FORMULATION_DIVERGENCE sem sobrescrever.
        doc_v2 = doc_v1.replace(b'version: "0.1.0"', b'version: "0.2.0"').replace(
            'Formulação original do achado A.'.encode('utf-8'),
            'Formulação divergente do achado A.'.encode('utf-8'),
        )
        _, rec_v2 = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'multi.md',
            'content_base64': base64.b64encode(doc_v2).decode(),
            'external_id': 'DOC-MULTI',
            'declared_version': '0.2.0',
            'provenance': 'Nova versão externa',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        _, inspected_v2 = self.call('GET', f"/api/documents/{rec_v2['version_id']}/parametrized")
        self.assertEqual(inspected_v2['records'][0]['archive_status'], 'FORMULATION_DIVERGENCE')
        self.assertEqual(inspected_v2['records'][0]['existing_insight_id'], confirmed_a['id'])
        self.assertEqual(self.server.archive.get(confirmed_a['id'])['claim'], 'Formulação original do achado A.')
