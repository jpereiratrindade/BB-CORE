import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from bbcore.store import Archive, Conflict

ROOT = Path(__file__).resolve().parents[1]
METIS = ROOT / 'docs/reference/METIS-ACH-20261123-001_v0.1.0.md'


def ingestion(body=None, **changes):
    return {'request_id': str(uuid.uuid4()), 'filename': METIS.name,
            'content_base64': base64.b64encode(body if body is not None else METIS.read_bytes()).decode(),
            'external_id': 'METIS-ACH-20261123-001', 'declared_version': '0.1.0',
            'declared_date': '2026-11-23', 'provenance': 'Documento fornecido pelo usuário',
            'received_by': 'Operador declarado', 'confirmed': True, **changes}


def anchored(receipt, quote, body=None, **changes):
    body = METIS.read_bytes() if body is None else body
    start = body.index(quote.encode())
    return {'request_id': str(uuid.uuid4()), 'title': 'Decisão de consolidar a base paramétrica de R',
            'claim': quote, 'why_matters': 'Preservar a decisão de prioridade com seu fundamento.',
            'limitations': 'Relato documental de decisão; não comprova validade empírica de R.',
            'kind': 'METHODOLOGICAL_DECISION', 'work_state': 'ADOPTED',
            'formulation_origin': 'DOCUMENT_EXCERPT', 'confirmed_by_declared': 'Operador declarado',
            'confirmed': True, 'anchors': [{'receipt_id': receipt['receipt_id'], 'quote': quote,
                'start_byte': start, 'end_byte': start + len(quote.encode()), 'role': 'documentary_support'}],
            **changes}


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'archive.sqlite'
        self.archive = Archive(self.path)
        self.docs = self.archive.documents

    def tearDown(self):
        self.archive.db.close()
        self.tmp.cleanup()

    def test_metis_acceptance_two_distinct_records_and_restart(self):
        receipt = self.docs.ingest(ingestion())
        decision = self.docs.create_record(anchored(receipt, 'Estabilizar a **base técnico-científica e computacional de R** por meio de:'))
        question = 'Onde, quando e em que escala espacial, temporal e relacional uma perturbação afeta funções de um sistema e permite, ou não, identificar uma propriedade emergente associada à manutenção, reorganização ou recuperação dessas funções?'
        open_question = self.docs.create_record(anchored(receipt, question, title='Questão científica da emergência', kind='OPEN_QUESTION', work_state='OPEN'))
        self.assertEqual(self.docs.original(receipt['version_id']), METIS.read_bytes())
        self.assertEqual(self.docs.get(receipt['version_id'])['integrity'], 'VERIFIED_LOCAL_BYTES')
        self.assertEqual(self.archive.context(decision['id'])['elaboration']['work_state'], 'ADOPTED')
        self.assertEqual(self.archive.context(open_question['id'])['elaboration']['work_state'], 'OPEN')
        self.assertEqual(len(self.docs.get(receipt['version_id'])['records']), 2)
        self.archive.db.close()
        self.archive = Archive(self.path)
        self.assertEqual(self.archive.context(open_question['id'])['sources'][0]['quote'], question)
        self.assertEqual(self.archive.verify()['integrity'], 'VERIFIED')

    def test_repeated_content_preserves_distinct_receipts_and_one_blob(self):
        data = ingestion()
        first = self.docs.ingest(data)
        self.assertEqual(first, self.docs.ingest(data))
        second = self.docs.ingest({**data, 'request_id': str(uuid.uuid4()), 'provenance': 'Outra procedência declarada'})
        self.assertEqual(second['outcome'], 'RECEIVED_AGAIN')
        self.assertEqual(first['version_id'], second['version_id'])
        self.assertNotEqual(first['receipt_id'], second['receipt_id'])
        document = self.docs.get(first['version_id'])
        self.assertEqual(len(document['receipts']), 2)
        self.assertNotEqual(document['receipts'][0]['provenance'], document['receipts'][1]['provenance'])
        self.assertEqual(self.archive.db.execute('SELECT count(*) FROM document_contents').fetchone()[0], 1)
        self.assertEqual(self.archive.db.execute('SELECT count(*) FROM insights').fetchone()[0], 0)

    def test_version_conflict_is_preserved_and_never_overwrites(self):
        original = self.docs.ingest(ingestion())
        altered = METIS.read_bytes() + b'\nConteudo divergente.\n'
        payload = ingestion(altered)
        conflict = self.docs.ingest(payload)
        self.assertEqual(conflict['outcome'], 'VERSION_CONFLICT')
        self.assertEqual(self.docs.ingest(payload), conflict)
        self.assertEqual(self.docs.original(original['version_id']), METIS.read_bytes())
        self.assertEqual(self.docs.original(receipt_id=conflict['receipt_id']), altered)
        with self.assertRaises(Conflict):
            self.docs.create_record(anchored(conflict, 'Estabilizar a **base técnico-científica e computacional de R** por meio de:'))
        new = self.docs.ingest(ingestion(altered, declared_version='0.1.1'))
        self.assertEqual(new['document_id'], original['document_id'])
        self.assertNotEqual(new['version_id'], original['version_id'])
        self.assertEqual(len(self.docs.get(new['version_id'])['versions']), 2)

    def test_multiple_documents_and_immutable_record_revision(self):
        one = self.docs.ingest(ingestion())
        body = 'Texto adicional: decisão de trabalho.'.encode()
        two = self.docs.ingest(ingestion(body, external_id='OUTRO', declared_version='1'))
        data = anchored(one, 'A prioridade não implica considerar os dados de origem já auditados nem o indicador cientificamente validado.')
        data['anchors'].extend(anchored(two, 'decisão de trabalho.', body)['anchors'])
        original = self.docs.create_record(data)
        self.assertEqual(self.docs.create_record(data), original)
        revised = self.docs.create_record({**data, 'request_id': str(uuid.uuid4()), 'claim': 'Formulação revista, com as mesmas fontes.', 'supersedes_id': original['id'], 'formulation_origin': 'HUMAN_FORMULATION'})
        self.assertEqual(len(self.archive.context(original['id'])['sources']), 2)
        self.assertEqual(self.archive.get(original['id'])['claim'], data['claim'])
        self.assertIn(revised['id'], self.archive.get(original['id'])['revised_by'])
        self.assertEqual(self.archive.context(revised['id'])['elaboration']['supersedes_id'], original['id'])

    def test_repeated_quote_requires_correct_byte_offsets(self):
        body = 'Árvore: R. Árvore: R.'.encode()
        receipt = self.docs.ingest(ingestion(body))
        data = anchored(receipt, 'Árvore: R.', body)
        data['anchors'][0]['start_byte'] = len('Árvore: R. '.encode())
        data['anchors'][0]['end_byte'] = len(body)
        result = self.docs.create_record(data)
        self.assertEqual(self.archive.context(result['id'])['sources'][0]['start_byte'], len('Árvore: R. '.encode()))
        data['request_id'] = str(uuid.uuid4())
        data['anchors'][0]['start_byte'] += 1
        with self.assertRaises(ValueError):
            self.docs.create_record(data)

    def test_tampering_detected_for_originals_anchors_and_health(self):
        receipt = self.docs.ingest(ingestion())
        result = self.docs.create_record(anchored(receipt, 'A investigação deve aceitar ausência de emergência detectável, resultados inconclusivos, escalas inadequadas e hipóteses alternativas.'))
        self.archive.db.execute('UPDATE document_anchors SET start_byte=start_byte+1')
        with self.assertRaises(Conflict):
            self.archive.context(result['id'])
        self.assertEqual(self.archive.verify()['integrity'], 'FAILED')
        self.archive.db.execute('UPDATE document_contents SET body=?', (b'tampered',))
        with self.assertRaises(Conflict):
            self.docs.original(receipt['version_id'])

    def test_validation_confirmation_uuid_and_atomicity(self):
        for change in ({'confirmed': False}, {'content_base64': '???'}, {'filename': '../file.md'}, {'filename': 'file.pdf'}, {'content_base64': base64.b64encode(b'\xff').decode()}, {'declared_date': '2026-02-31'}, {'content_base64': base64.b64encode(b'x'*256001).decode()}):
            with self.subTest(change=list(change)):
                with self.assertRaises(ValueError):
                    self.docs.ingest(ingestion(**change))
        payload = ingestion()
        self.docs.ingest(payload)
        with self.assertRaises(Conflict):
            self.docs.ingest({**payload, 'provenance': 'Alterada no mesmo pedido'})
        self.assertEqual(self.archive.db.execute('SELECT count(*) FROM document_receipts').fetchone()[0], 1)
        receipt = self.docs.ingest(ingestion())
        data = anchored(receipt, 'A prioridade não implica considerar os dados de origem já auditados nem o indicador cientificamente validado.')
        for change in ({'confirmed': False}, {'kind': 'OPEN_QUESTION', 'work_state': 'ADOPTED'}, {'formulation_origin': 'AI_SUGGESTION'}):
            with self.assertRaises(ValueError):
                self.docs.create_record({**data, **change})
        self.assertEqual(self.archive.db.execute('SELECT count(*) FROM insights').fetchone()[0], 0)

    def test_bom_crlf_and_unicode_bytes_are_not_normalized(self):
        body = b'\xef\xbb\xbf' + 'Árvore e 🌱\r\nSegunda linha.\r\n'.encode()
        receipt = self.docs.ingest(ingestion(body))
        self.assertEqual(self.docs.original(receipt['version_id']), body)
        self.assertEqual(self.docs.get(receipt['version_id'])['text'].encode('utf-8'), body)
        record = self.docs.create_record(anchored(receipt, 'Árvore e 🌱\r\nSegunda linha.', body))
        self.assertEqual(self.archive.context(record['id'])['sources'][0]['start_byte'], 3)

    def test_anonymous_documents_do_not_invent_identifiers(self):
        first = self.docs.ingest(ingestion(external_id=None, declared_version=None))
        second = self.docs.ingest(ingestion(external_id=None, declared_version=None, provenance='Outra origem'))
        self.assertEqual(first['version_id'], second['version_id'])
        self.assertIsNone(self.docs.get(first['version_id'])['external_id'])


if __name__ == '__main__':
    unittest.main()
