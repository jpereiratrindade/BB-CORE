"""Testes do interpretador determinístico de Markdown parametrizado (BB-CORE-ING-0.2.0)."""
import json
import unittest
from pathlib import Path

from bbcore.parametrized import (
    MAX_FRONTMATTER_BYTES,
    ParametrizedError,
    parse_parametrized_markdown,
)

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
