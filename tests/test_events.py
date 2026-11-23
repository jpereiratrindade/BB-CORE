import copy
import json
from pathlib import Path
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
import uuid

from bbcore.events import Events, ZERO_HASH, encoded, fingerprint
from bbcore.store import Archive, Conflict
from test_core import capsule
from test_documents import ingestion, anchored

ACTOR = {'id': 'operator:declared', 'name': 'Responsável declarado'}


def event(iid, **changes):
    return {'request_id': str(uuid.uuid4()), 'insight_id': iid, 'event_type': 'OCCURRENCE_RECORDED',
            'mode': 'REPORTED', 'occurred_at': None, 'origin': 'Relato fornecido pelo operador',
            'responsible': ACTOR, 'content': {'summary': 'Crítica recebida durante discussão.'},
            'evidence': [], 'prior_events': [], 'missing': ['Transcrição da discussão'],
            'limitations': 'Relato declarado, sem autenticação externa.', 'confirmed': True, **changes}


class EventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'archive.sqlite'
        self.archive = Archive(self.path)

    def tearDown(self):
        self.archive.db.close()
        self.tmp.cleanup()

    def create(self):
        return self.archive.capture(capsule())['id']

    def legacy(self):
        """Simula um registro previamente existente, sem gerar evento retrospectivo."""
        iid = uuid.uuid4().hex
        self.archive.db.execute('INSERT INTO insights VALUES(?,?,?,?,?,?,?,?,?,?)',
                                (iid, 'Registro anterior', 'Formulação preservada', 'REPORTED', '{}',
                                 'Origem histórica incompleta', '{}', 'PRIVATE', '2020-01-01T00:00:00+00:00', 1))
        return iid

    def evidence(self, iid):
        return [{'kind': 'insight', 'id': iid, 'role': 'record_under_examination'}]

    def test_existing_records_have_no_fictitious_trajectory(self):
        iid = self.legacy()
        self.archive.db.close()
        self.archive = Archive(self.path)
        trajectory = self.archive.events.trajectory(iid)
        self.assertEqual(trajectory['events'], [])
        self.assertIsNone(trajectory['baseline'])
        self.assertEqual(trajectory['current_state']['claim'], 'Formulação preservada')
        first = self.archive.events.append(event(iid, responsible=None, origin=None))
        self.assertEqual(first['baselines'][iid]['nature'], 'EXISTING_RECORD_AT_FIRST_EVENT')
        self.assertEqual(first['occurred_at'], None)
        self.assertIn('occurred_at', first['missing'])
        self.assertIn('responsible', first['missing'])
        self.assertIn('origin', first['missing'])
        self.assertNotEqual(first['recorded_at'], '2020-01-01T00:00:00+00:00')
        self.assertEqual([e['event_type'] for e in self.archive.events.trajectory(iid)['events']], ['OCCURRENCE_RECORDED'])

    def test_capture_is_observed_atomically_and_idempotently(self):
        payload = capsule()
        one = self.archive.capture(payload)
        self.assertEqual(one, self.archive.capture(payload))
        trajectory = self.archive.events.trajectory(one['id'])
        self.assertEqual(trajectory['event_count'], 1)
        created = trajectory['events'][0]
        self.assertEqual(created['event_type'], 'INSIGHT_REGISTERED')
        self.assertEqual(created['mode'], 'OBSERVED')
        self.assertEqual(created['responsible']['id'], 'bb-core:service')
        self.assertEqual(created['baselines'][one['id']]['nature'], 'CREATION_OBSERVED')
        self.assertEqual(trajectory['relation_attributions'], [])

    def test_replay_revision_keeps_identity_original_and_unknowns(self):
        iid = self.create()
        original = self.archive.get(iid)
        first = self.archive.events.append(event(iid, occurred_at='2025-03-04'))
        revised = self.archive.events.append(event(iid, event_type='FORMULATION_REVISED', mode='OBSERVED',
            occurred_at='2026-01-02T14:00:00-03:00',
            content={'summary': 'Reformulação após crítica declarada.', 'changes': {'claim': 'Formulação revista.', 'limitations': 'Limite explicitado.'}},
            evidence=self.evidence(iid), prior_events=[{'event_id': first['id'], 'relationship': 'RESPONDS_TO', 'basis': 'Revisão explicitamente declarada como resposta ao relato.'}]))
        self.assertNotEqual(first['occurred_at'], first['recorded_at'])
        self.assertEqual(revised['previous_hash'], first['event_hash'])
        self.assertEqual(self.archive.get(iid)['claim'], original['claim'])
        projection = self.archive.events.trajectory(iid)
        self.assertEqual(projection['current_state']['id'], iid)
        self.assertEqual(projection['current_state']['claim'], 'Formulação revista.')
        self.assertEqual(projection['formulation_revision_count'], 1)
        checkpoint = self.archive.events.checkpoint()
        exported = self.archive.events.export()
        offline = Events.replay_bundle(exported, iid, checkpoint)
        self.assertEqual(offline['current_state'], projection['current_state'])
        self.assertEqual(offline['evidence_integrity'], 'NOT_RECHECKED_OFFLINE')
        self.archive.db.close()
        self.archive = Archive(self.path)
        self.assertEqual(self.archive.events.trajectory(iid), projection)

    def test_document_sources_are_reused_and_later_events_are_explicit(self):
        receipt = self.archive.documents.ingest(ingestion())
        quote = 'A prioridade não implica considerar os dados de origem já auditados nem o indicador cientificamente validado.'
        data = anchored(receipt, quote)
        record = self.archive.documents.create_record(data)
        self.assertEqual(self.archive.events.trajectory(record['id'])['event_count'], 1)
        reference = self.archive.events.append(event(record['id'], event_type='EVIDENCE_REFERENCED',
            evidence=[{'kind': 'receipt', 'id': receipt['receipt_id'], 'role': 'source_of_report'}]))
        self.assertEqual(reference['evidence'][0]['snapshot']['sha256'], receipt['sha256'])
        revision = self.archive.documents.create_record({**data, 'request_id': str(uuid.uuid4()),
            'supersedes_id': record['id'], 'claim': 'Formulação humana revisada.', 'formulation_origin': 'HUMAN_FORMULATION'})
        old = self.archive.events.trajectory(record['id'])
        self.assertEqual(old['events'][-1]['event_type'], 'REVISION_REFERENCE_RECORDED')
        self.assertEqual(old['events'][-1]['content']['new_record_id'], revision['id'])
        self.assertEqual(old['current_state']['claim'], quote)
        self.assertEqual(self.archive.db.execute('SELECT count(*) FROM document_contents').fetchone()[0], 1)

    def test_common_sources_and_time_do_not_imply_relations(self):
        a, b = self.create(), self.create()
        ta, tb = self.archive.events.trajectory(a), self.archive.events.trajectory(b)
        self.assertEqual(ta['relation_attributions'], [])
        self.assertEqual(tb['relation_attributions'], [])
        self.assertEqual(tb['events'][0]['prior_events'], [])
        self.assertEqual(tb['events'][0]['previous_hash'], ta['events'][0]['event_hash'])
        self.assertNotIn(a, tb['events'][0]['baselines'])

    def test_relation_recognition_and_contestation_are_attributions(self):
        a, b = self.create(), self.create()
        proposal = self.archive.relate({'request_id': str(uuid.uuid4()), 'left_id': a, 'right_id': b,
            'rationale': 'Hipótese de complementaridade.', 'counterpoint': 'Podem ter alcances diferentes.',
            'responsible': ACTOR, 'origin': 'Exame manual', 'evidence': self.evidence(a)})
        recognized = self.archive.events.append(event(a, event_type='RELATION_RECOGNIZED',
            occurred_at='2026-02-03', evidence=self.evidence(a),
            content={'summary': 'Operador relata reconhecimento restrito.', 'relation_id': proposal['id'], 'scope': 'Complementaridade conceitual neste estudo, sem generalização.'}))
        contested = self.archive.events.append(event(b, event_type='RELATION_CONTESTED',
            responsible={'id': 'reviewer:declared', 'name': 'Revisor declarado'}, occurred_at='2026-02-04',
            evidence=self.evidence(b), content={'summary': 'Questiona-se o alcance do reconhecimento.', 'relation_id': proposal['id'], 'scope': 'Aplicabilidade empírica.'},
            prior_events=[{'event_id': recognized['id'], 'relationship': 'CONTESTS', 'basis': 'Contestação explícita da atribuição, conforme declaração do revisor.'}]))
        for iid in (a, b):
            trajectory = self.archive.events.trajectory(iid)
            self.assertEqual([e['event_type'] for e in trajectory['relation_attributions']], ['RELATION_PROPOSED', 'RELATION_RECOGNIZED', 'RELATION_CONTESTED'])
            self.assertEqual(self.archive.get(iid)['relations'][0]['status'], 'INFERRED_CANDIDATE')
        self.assertEqual(contested['mode'], 'REPORTED')
        self.assertNotEqual(contested['responsible'], recognized['responsible'])

    def test_validation_rejects_unattributed_recognition_and_implicit_links(self):
        iid = self.create()
        first = self.archive.events.trajectory(iid)['events'][0]
        for changes in ({'confirmed': False}, {'occurred_at': '2026-01-01T12:00:00'},
                        {'event_type': 'INSIGHT_REGISTERED'}, {'event_type': 'INTERPRETATION_PROPOSED', 'mode': 'OBSERVED'},
                        {'event_type': 'RELATION_RECOGNIZED', 'responsible': None},
                        {'event_type': 'FORMULATION_REVISED', 'mode': 'OBSERVED', 'content': {'summary': 'Mudar status', 'changes': {'status': 'VALIDATED'}}},
                        {'prior_events': [{'event_id': first['id'], 'relationship': 'MOTIVATED_BY', 'basis': 'Somente posterioridade temporal.'}]}):
            with self.subTest(changes=changes):
                with self.assertRaises((ValueError, Conflict)):
                    self.archive.events.append(event(iid, **changes))
        self.assertEqual(self.archive.events.trajectory(iid)['event_count'], 1)

    def test_request_retry_and_atomic_rollback_on_chain_failure(self):
        iid = self.create()
        data = event(iid)
        first = self.archive.events.append(data)
        self.assertEqual(self.archive.events.append(data), first)
        with self.assertRaises(Conflict):
            self.archive.events.append({**data, 'origin': 'Origem alterada'})
        self.archive.db.execute('UPDATE event_log_head SET last_hash=?', ('f'*64,))
        before = self.archive.db.execute('SELECT count(*) FROM insights').fetchone()[0]
        with self.assertRaises(Conflict):
            self.create()
        self.assertEqual(self.archive.db.execute('SELECT count(*) FROM insights').fetchone()[0], before)
        self.assertEqual(self.archive.verify()['event_integrity'], 'FAILED')

    def test_append_only_tampering_truncation_and_reference_corruption(self):
        iid = self.create()
        for command in ('UPDATE intellectual_events SET event_hash="bad"', 'DELETE FROM intellectual_events'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.archive.db.execute(command)
        exported = self.archive.events.export()
        for mutate in (lambda b: b['events'][0]['content'].update(summary='Alterado'),
                       lambda b: b['events'].clear(),
                       lambda b: b['events'][0].update(insight_id='outra-identidade')):
            changed = copy.deepcopy(exported)
            mutate(changed)
            with self.assertRaises(Conflict):
                Events.verify_bundle(changed)
        self.archive.db.execute('UPDATE sources SET origin="procedência adulterada"')
        with self.assertRaises(Conflict):
            self.archive.events.trajectory(iid)
        self.assertEqual(self.archive.verify()['integrity'], 'FAILED')

    def test_external_checkpoint_detects_rehashed_history_and_accepts_extension(self):
        iid = self.create()
        checkpoint = self.archive.events.checkpoint()
        self.archive.events.append(event(iid))
        bundle = self.archive.events.export()
        self.assertTrue(Events.verify_bundle(bundle, checkpoint)['checkpoint_checked'])
        changed = copy.deepcopy(bundle)
        changed['events'][0]['content']['summary'] = 'História reescrita'
        previous = ZERO_HASH
        for item in changed['events']:
            item['previous_hash'] = previous
            item['event_hash'] = fingerprint({k: v for k, v in item.items() if k != 'event_hash'})
            previous = item['event_hash']
        changed['head']['last_hash'] = previous
        self.assertEqual(Events.verify_bundle(changed)['integrity'], 'VERIFIED')
        with self.assertRaises(Conflict):
            Events.verify_bundle(changed, checkpoint)

    def test_concurrent_appends_have_no_forks_or_duplicate_retries(self):
        iid = self.create()
        data = event(iid)
        def append(_):
            archive = Archive(self.path)
            try:
                return archive.events.append(data)['id']
            finally:
                archive.db.close()
        with ThreadPoolExecutor(max_workers=3) as pool:
            ids = list(pool.map(append, range(6)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(self.archive.events.trajectory(iid)['event_count'], 2)
        self.assertEqual(self.archive.events.verify()['event_integrity'], 'VERIFIED')

    def test_sqlite_backup_restore_preserves_events_documents_and_checkpoint(self):
        receipt = self.archive.documents.ingest(ingestion())
        quote = 'A prioridade não implica considerar os dados de origem já auditados nem o indicador cientificamente validado.'
        record = self.archive.documents.create_record(anchored(receipt, quote))
        iid = record['id']
        self.archive.events.append(event(iid, evidence=[{'kind': 'receipt', 'id': receipt['receipt_id'], 'role': 'support'}]))
        expected = self.archive.events.trajectory(iid)
        checkpoint = self.archive.events.checkpoint()
        destination = Path(self.tmp.name) / 'restored.sqlite'
        target = sqlite3.connect(destination)
        try:
            self.archive.db.backup(target)
        finally:
            target.close()
        restored = Archive(destination)
        try:
            self.assertEqual(restored.events.trajectory(iid), expected)
            self.assertEqual(restored.documents.original(receipt['version_id']), self.archive.documents.original(receipt['version_id']))
            self.assertEqual(Events.verify_bundle(restored.events.export(), checkpoint)['integrity'], 'VERIFIED')
            self.assertEqual(restored.verify()['integrity'], 'VERIFIED')
        finally:
            restored.db.close()

    def test_verified_reads_during_concurrent_unique_appends(self):
        iid = self.create()
        def write(_):
            archive = Archive(self.path)
            try:
                return archive.events.append(event(iid))['id']
            finally:
                archive.db.close()
        def read(_):
            archive = Archive(self.path)
            try:
                for _ in range(5):
                    self.assertEqual(archive.events.verify()['event_integrity'], 'VERIFIED')
                    Events.verify_bundle(archive.events.export())
            finally:
                archive.db.close()
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(write, i) for i in range(5)] + [pool.submit(read, 0)]
            for future in futures:
                future.result()
        self.assertEqual(self.archive.events.trajectory(iid)['event_count'], 6)

    def test_payload_cannot_hide_an_unhashed_hash_field(self):
        self.create()
        row = self.archive.db.execute('SELECT payload FROM intellectual_events WHERE seq=1').fetchone()
        body = json.loads(row['payload'])
        body['event_hash'] = 'campo extra não permitido dentro do payload'
        self.archive.db.execute('DROP TRIGGER intellectual_events_no_update')
        self.archive.db.execute('UPDATE intellectual_events SET payload=? WHERE seq=1', (encoded(body),))
        with self.assertRaises(Conflict):
            self.archive.events.export()

    def test_physical_payload_and_tail_corruption_detected(self):
        iid = self.create()
        self.archive.events.append(event(iid))
        self.archive.db.execute('DROP TRIGGER intellectual_events_no_update')
        self.archive.db.execute('UPDATE intellectual_events SET payload=? WHERE seq=1', ('{}',))
        with self.assertRaises(Conflict):
            self.archive.events.export()


if __name__ == '__main__':
    unittest.main()
