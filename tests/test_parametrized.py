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

        # 3. Rota legada /api/document-records não pode contornar confirmação autoritativa de Markdown parametrizado.
        cand_a = inspected['records'][0]
        with self.assertRaises(HTTPError) as bypass_err:
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
                'anchors': [{'receipt_id': rec1['receipt_id'], **cand_a['anchors'][0]}],
            })
        self.assertEqual(bypass_err.exception.code, 409)

        # Confirmação seletiva autoritativa apenas do primeiro registro (rec-a).
        status, confirmed_a = self.call('POST', '/api/documents/confirm-record', {
            'request_id': str(uuid.uuid4()),
            'receipt_id': rec1['receipt_id'],
            'id_local': cand_a['id_local'],
            'confirmed_by_declared': 'Pesquisador',
            'confirmed': True,
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

    def test_authoritative_confirm_context_divergence_version_conflict_legacy_and_export(self):
        self.call('POST', '/api/local-session', {})

        # 1. Registro legado criado antes de imported_record_identities (simulando BB-CORE-INSIGHT-001).
        ref_bytes = REF_DOC.read_bytes()
        _, leg_doc = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'legacy.md',
            'content_base64': base64.b64encode(b'# Legado\n\nTexto antigo.\n').decode(),
            'external_id': 'BB-CORE-INSIGHT-001',
            'declared_version': '0.1.0',
            'provenance': 'Documento legado',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        _, leg_ins = self.call('POST', '/api/document-records', {
            'request_id': str(uuid.uuid4()),
            'title': 'Distinção entre elaboração intelectual e preservação do conhecimento',
            'claim': 'Texto antigo.',
            'why_matters': 'Relevância',
            'genesis': {},
            'limitations': 'Limites',
            'kind': 'CONCEPTUAL_FINDING',
            'work_state': 'PROPOSED',
            'formulation_origin': 'DOCUMENT_EXCERPT',
            'confirmed_by_declared': 'Pesquisador',
            'confirmed': True,
            'context': {'external_document_id': 'BB-CORE-INSIGHT-001', 'document_version': '0.1.0'},
            'anchors': [{'receipt_id': leg_doc['receipt_id'], 'quote': 'Texto antigo.', 'start_byte': 10, 'end_byte': 23, 'role': 'primary'}],
        })

        # 2. Envio de BB-CORE-INSIGHT-001.parametrized.md com mesma versão 0.1.0 gera VERSION_CONFLICT.
        try:
            self.call('POST', '/api/documents', {
                'request_id': str(uuid.uuid4()),
                'filename': 'BB-CORE-INSIGHT-001.parametrized.md',
                'content_base64': base64.b64encode(ref_bytes).decode(),
                'external_id': 'BB-CORE-INSIGHT-001',
                'declared_version': '0.1.0',
                'provenance': 'Reenvio parametrizado na mesma versão',
                'received_by': 'Pesquisador',
                'confirmed': True,
            })
            self.fail('Esperado 409 VERSION_CONFLICT')
        except HTTPError as conflict_err:
            self.assertEqual(conflict_err.code, 409)
            conflict_body = json.loads(conflict_err.read())
            self.assertEqual(conflict_body['outcome'], 'VERSION_CONFLICT')

        # 3. Exame do recebimento divergente via /api/receipts/{id}/parametrized funciona sem substituir o original.
        _, div_param = self.call('GET', f"/api/receipts/{conflict_body['receipt_id']}/parametrized")
        self.assertTrue(div_param['is_parametrized'])
        self.assertEqual(div_param['records'][0]['archive_status'], 'LEGACY_MATCH_CANDIDATE')
        self.assertEqual(div_param['records'][0]['legacy_matches'][0]['insight_id'], leg_ins['id'])

        # Confirmação a partir de recebimento em conflito continua bloqueada.
        with self.assertRaises(HTTPError) as blocked:
            self.call('POST', '/api/documents/confirm-record', {
                'request_id': str(uuid.uuid4()),
                'receipt_id': conflict_body['receipt_id'],
                'id_local': 'achado-elaboracao-vs-preservacao',
                'confirmed_by_declared': 'Pesquisador',
                'confirmed': True,
            })
        self.assertEqual(blocked.exception.code, 409)

        # 4. Recebimento como versão 0.2.0 permite vínculo explícito ao registro legado sem duplicar.
        _, v2_doc = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'BB-CORE-INSIGHT-001.parametrized.md',
            'content_base64': base64.b64encode(ref_bytes).decode(),
            'external_id': 'BB-CORE-INSIGHT-001',
            'declared_version': '0.2.0',
            'provenance': 'Versão parametrizada',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        _, linked = self.call('POST', '/api/documents/link-legacy', {
            'request_id': str(uuid.uuid4()),
            'receipt_id': v2_doc['receipt_id'],
            'id_local': 'achado-elaboracao-vs-preservacao',
            'insight_id': leg_ins['id'],
            'confirmed_by_declared': 'Pesquisador',
            'confirmed': True,
            'rationale': 'Vínculo explícito verificado manualmente.',
        })
        self.assertTrue(linked['linked'])
        self.assertEqual(linked['recognition_kind'], 'LEGACY_IDENTITY_LINKED')
        self.assertFalse(linked['claim_matches'])
        self.assertFalse(linked['content_matches'])
        self.assertEqual(len(self.server.archive.list()), 1)

        # Mesmo sem external_id no documento, a mesma ocorrência (receipt_id, id_local) não pode ser confirmada duas vezes.
        anon_doc = (
            '---\nschema: "BB-CORE-ING-0.2.0"\ndocument: {}\n'
            'records:\n  - id_local: "anon-1"\n    kind: "OPEN_QUESTION"\n    work_state: "OPEN"\n'
            '    title: "Questão anônima"\n    formulation_origin: "DOCUMENT_EXCERPT"\n'
            '    claim_section: "Questão"\n    why_matters: "Importa"\n    limitations: "Limite"\n'
            '---\n\n## Questão\n\nTexto anônimo.\n'
        ).encode('utf-8')
        _, d_anon = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'anon.md',
            'content_base64': base64.b64encode(anon_doc).decode(),
            'provenance': 'Sem ID externo',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        status, anon_rec = self.call('POST', '/api/documents/confirm-record', {
            'request_id': str(uuid.uuid4()),
            'receipt_id': d_anon['receipt_id'],
            'id_local': 'anon-1',
            'confirmed_by_declared': 'Pesquisador',
            'confirmed': True,
        })
        self.assertEqual(status, 201)
        with self.assertRaises(HTTPError) as anon_dup:
            self.call('POST', '/api/documents/confirm-record', {
                'request_id': str(uuid.uuid4()),
                'receipt_id': d_anon['receipt_id'],
                'id_local': 'anon-1',
                'confirmed_by_declared': 'Pesquisador',
                'confirmed': True,
            })
        self.assertEqual(anon_dup.exception.code, 409)
        _, anon_insp = self.call('GET', f"/api/documents/{d_anon['version_id']}/parametrized")
        self.assertEqual(anon_insp['records'][0]['archive_status'], 'ALREADY_CONFIRMED')
        self.assertEqual(anon_insp['records'][0]['existing_insight_id'], anon_rec['id'])

        # Novo recebimento (RECEIVED_AGAIN) dos mesmos bytes anônimos também bloqueia confirmação repetida.
        _, d_anon_2 = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'anon-copia.md',
            'content_base64': base64.b64encode(anon_doc).decode(),
            'provenance': 'Segundo recebimento dos mesmos bytes',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        self.assertEqual(d_anon_2['outcome'], 'RECEIVED_AGAIN')
        with self.assertRaises(HTTPError) as anon_dup_2:
            self.call('POST', '/api/documents/confirm-record', {
                'request_id': str(uuid.uuid4()),
                'receipt_id': d_anon_2['receipt_id'],
                'id_local': 'anon-1',
                'confirmed_by_declared': 'Pesquisador',
                'confirmed': True,
            })
        self.assertEqual(anon_dup_2.exception.code, 409)

        # 5. Confirmação autoritativa no servidor + CONTEXT_DIVERGENCE + exportação Markdown.
        doc_ctx = (
            '---\nschema: "BB-CORE-ING-0.2.0"\ndocument:\n  external_id: "CTX-TEST"\n  version: "0.1.0"\n'
            '  source_context:\n    origin_kind: "CHATGPT_CONVERSATION"\n    transcript_included: false\n'
            '    provenance_gaps:\n      - "Sem transcrição completa"\n'
            'records:\n  - id_local: "r1"\n    kind: "CONCEPTUAL_FINDING"\n    work_state: "PROPOSED"\n'
            '    title: "Achado C"\n    formulation_origin: "DOCUMENT_EXCERPT"\n'
            '    claim_section: "Achado"\n    why_matters: "Importa"\n    limitations: "Limite 1"\n'
            '    declared_relations:\n      - left_id: "x"\n        right_id: "y"\n'
            '---\n\n## Achado\n\nFormulação C.\n'
        ).encode('utf-8')
        _, d_ctx = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'ctx.md',
            'content_base64': base64.b64encode(doc_ctx).decode(),
            'external_id': 'CTX-TEST',
            'declared_version': '0.1.0',
            'provenance': 'ChatGPT',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        _, auth_rec = self.call('POST', '/api/documents/confirm-record', {
            'request_id': str(uuid.uuid4()),
            'receipt_id': d_ctx['receipt_id'],
            'id_local': 'r1',
            'confirmed_by_declared': 'Pesquisador',
            'confirmed': True,
        })
        ctx_saved = self.server.archive.context(auth_rec['id'])
        self.assertEqual(ctx_saved['context']['source_context']['origin_kind'], 'CHATGPT_CONVERSATION')
        self.assertIn('Sem transcrição completa', ctx_saved['context']['missing'])
        self.assertEqual(ctx_saved['relations'], [])
        self.assertEqual(len(ctx_saved['context']['pending_declared_relations']), 1)

        # Alterar apenas limitações dispara CONTEXT_DIVERGENCE (não FORMULATION_DIVERGENCE).
        doc_ctx_2 = doc_ctx.replace(b'Limite 1', b'Limite 2 atualizado').replace(b'0.1.0', b'0.2.0')
        _, d_ctx_2 = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'ctx2.md',
            'content_base64': base64.b64encode(doc_ctx_2).decode(),
            'external_id': 'CTX-TEST',
            'declared_version': '0.2.0',
            'provenance': 'ChatGPT v2',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        _, insp_ctx_2 = self.call('GET', f"/api/documents/{d_ctx_2['version_id']}/parametrized")
        self.assertEqual(insp_ctx_2['records'][0]['archive_status'], 'CONTEXT_DIVERGENCE')

        # Alterar apenas proveniência documental dispara PROVENANCE_DIVERGENCE.
        doc_prov_2 = doc_ctx.replace(b'Sem transcri', b'Transcri').replace(b'0.1.0', b'0.3.0')
        _, d_prov_2 = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'ctx3.md',
            'content_base64': base64.b64encode(doc_prov_2).decode(),
            'external_id': 'CTX-TEST',
            'declared_version': '0.3.0',
            'provenance': 'ChatGPT v3',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        _, insp_prov_2 = self.call('GET', f"/api/documents/{d_prov_2['version_id']}/parametrized")
        self.assertEqual(insp_prov_2['records'][0]['archive_status'], 'PROVENANCE_DIVERGENCE')
        self.assertTrue(insp_prov_2['records'][0]['provenance_changed'])

        # Alteração de versão do algoritmo de hash é distinguida como HASH_COVERAGE_CHANGED.
        with self.server.archive.transaction():
            self.server.archive.db.execute(
                "UPDATE imported_record_identities SET content_hash_version='LEGACY_UNVERSIONED' WHERE declared_record_key='CTX-TEST:r1'"
            )
        _, insp_hash_v = self.call('GET', f"/api/documents/{d_ctx['version_id']}/parametrized")
        self.assertEqual(insp_hash_v['records'][0]['archive_status'], 'HASH_COVERAGE_CHANGED')

        # Exportação Markdown contextualizada (BB-CORE-EXP-0.1.0).
        with self.opener.open(f"http://127.0.0.1:{self.port}/api/insights/{auth_rec['id']}/export.md", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            md = resp.read().decode('utf-8')
            self.assertIn('export_schema: "BB-CORE-EXP-0.1.0"', md)
            self.assertIn('document_role: "EXPORTED_RECORD"', md)
            self.assertIn(f'insight_id: "{auth_rec["id"]}"', md)
            self.assertIn('exported_at:', md)
            self.assertIn('# Achado C', md)
            self.assertIn('Formulação C.', md)
            self.assertIn('CHATGPT_CONVERSATION', md)
            self.assertIn('Nenhuma relação registrada no acervo para este insight.', md)
            self.assertIn('receipt_id`: `', md)
            self.assertIn('start_byte`: `', md)
            self.assertIn('Trajetória documentada', md)

        # Proibição de criar novas identidades pela reimportação do registro exportado.
        _, reimport_check = self.call('POST', '/api/documents/inspect', {
            'content_base64': base64.b64encode(md.encode('utf-8')).decode(),
        })
        self.assertFalse(reimport_check['is_parametrized'])
        self.assertIn('exportação', reimport_check['error'].lower())

        # Exportação após reformulação distingue título, formulação e limitações correntes vs. originais.
        self.call('POST', '/api/events', {
            'request_id': str(uuid.uuid4()),
            'insight_id': auth_rec['id'],
            'event_type': 'FORMULATION_REVISED',
            'mode': 'OBSERVED',
            'origin': 'Exame humano',
            'responsible': {'id': 'local:pesquisador', 'name': 'Pesquisador'},
            'content': {
                'summary': 'Refina título, formulação e limitações de C.',
                'changes': {
                    'title': 'Achado C revisto',
                    'claim': 'Formulação C revista.',
                    'limitations': 'Limitação revista após exame.',
                },
            },
            'evidence': [{'kind': 'receipt', 'id': d_ctx['receipt_id'], 'role': 'basis'}],
            'limitations': 'Refinamento após exame.',
            'confirmed': True,
        })
        with self.opener.open(f"http://127.0.0.1:{self.port}/api/insights/{auth_rec['id']}/export.md", timeout=5) as resp2:
            md2 = resp2.read().decode('utf-8')
            self.assertIn('## Título corrente vs. original', md2)
            self.assertIn('Achado C revisto', md2)
            self.assertIn('## Formulação corrente (após 1 revisão/ões)', md2)
            self.assertIn('Formulação C revista.', md2)
            self.assertIn('## Formulação original preservada (histórico)', md2)
            self.assertIn('Formulação C.', md2)
            self.assertIn('## Limitações correntes', md2)
            self.assertIn('Limitação revista após exame.', md2)
            self.assertIn('## Limitações originais preservadas (histórico)', md2)
            self.assertIn('Evidências referenciadas:', md2)
            self.assertIn('Alterações declaradas (`changes`):', md2)

    def test_origin_reference_url_preservation_and_resume_link(self):
        from bbcore.store import valid_origin_url

        self.call('POST', '/api/local-session')

        self.assertEqual(
            valid_origin_url('  https://chatgpt.com/c/674321ab-1234-5678-9abc-def012345678  '),
            'https://chatgpt.com/c/674321ab-1234-5678-9abc-def012345678',
        )
        self.assertIsNone(valid_origin_url('Discussões de 24/11/2026 sobre avaliações'))
        self.assertIsNone(valid_origin_url('javascript:alert(1)'))
        self.assertIsNone(valid_origin_url('data:text/html,<script>alert(1)</script>'))
        self.assertIsNone(valid_origin_url('https://chatgpt.com/c/abc\nmalicious'))

        chat_url = 'https://chatgpt.com/c/674321ab-1234-5678-9abc-def012345678'
        doc_url = (
            '---\nschema: "BB-CORE-ING-0.2.0"\ndocument:\n  external_id: "URL-ORIGIN-1"\n  version: "0.1.0"\n'
            '  source_context:\n    origin_kind: "CHATGPT_CONVERSATION"\n'
            f'    origin_reference: "{chat_url}"\n'
            '    transcript_included: false\n'
            '    provenance_gaps:\n      - "Conversa privada no ChatGPT não transcrita integralmente"\n'
            'records:\n  - id_local: "r1"\n    kind: "CONCEPTUAL_FINDING"\n    work_state: "PROPOSED"\n'
            '    title: "Achado com URL de origem"\n    formulation_origin: "DOCUMENT_EXCERPT"\n'
            '    claim_section: "Achado"\n    why_matters: "Continuidade intelectual"\n    limitations: "Limite declarado"\n'
            '---\n\n## Achado\n\nFormulação ligada à conversa.\n'
        ).encode('utf-8')
        _, d_res = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'url-origin.md',
            'content_base64': base64.b64encode(doc_url).decode(),
            'external_id': 'URL-ORIGIN-1',
            'declared_version': '0.1.0',
            'provenance': 'ChatGPT',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        _, rec = self.call('POST', '/api/documents/confirm-record', {
            'request_id': str(uuid.uuid4()),
            'receipt_id': d_res['receipt_id'],
            'id_local': 'r1',
            'confirmed_by_declared': 'Pesquisador',
            'confirmed': True,
        })
        _, ctx = self.call('GET', f"/api/insights/{rec['id']}/context")
        self.assertEqual(ctx['context']['source_context']['origin_reference'], chat_url)
        initial_events = ctx['trajectory']['event_count']

        with self.opener.open(f"http://127.0.0.1:{self.port}/api/insights/{rec['id']}/export.md", timeout=5) as resp:
            md = resp.read().decode('utf-8')
            self.assertIn(f'[Retomar conversa original]({chat_url})', md)
            self.assertIn('não equivale à preservação integral da conversa nem à verificação de sua proveniência', md)
            self.assertIn(f'**origin_reference:** {chat_url}', md)

        _, ctx_after = self.call('GET', f"/api/insights/{rec['id']}/context")
        self.assertEqual(ctx_after['trajectory']['event_count'], initial_events)

        # Texto livre ou esquema inseguro em origin_reference não vira link de retomada na exportação.
        doc_text = doc_url.replace(chat_url.encode('utf-8'), b'javascript:alert(1)').replace(b'URL-ORIGIN-1', b'URL-ORIGIN-2')
        _, d_txt = self.call('POST', '/api/documents', {
            'request_id': str(uuid.uuid4()),
            'filename': 'text-origin.md',
            'content_base64': base64.b64encode(doc_text).decode(),
            'external_id': 'URL-ORIGIN-2',
            'declared_version': '0.1.0',
            'provenance': 'ChatGPT',
            'received_by': 'Pesquisador',
            'confirmed': True,
        })
        _, rec_txt = self.call('POST', '/api/documents/confirm-record', {
            'request_id': str(uuid.uuid4()),
            'receipt_id': d_txt['receipt_id'],
            'id_local': 'r1',
            'confirmed_by_declared': 'Pesquisador',
            'confirmed': True,
        })
        with self.opener.open(f"http://127.0.0.1:{self.port}/api/insights/{rec_txt['id']}/export.md", timeout=5) as resp_txt:
            md_txt = resp_txt.read().decode('utf-8')
            self.assertNotIn('[Retomar conversa original]', md_txt)

        # A interface de leitura expõe a operação complementar "Retomar conversa original".
        with self.opener.open(f"http://127.0.0.1:{self.port}/app.js", timeout=5) as js_resp:
            js = js_resp.read().decode('utf-8')
            self.assertIn('Retomar conversa original', js)
            self.assertIn('Dar continuidade ao registro no ChatGPT', js)
            self.assertIn('Exportar contexto em Markdown', js)
            self.assertIn('noopener noreferrer', js)
