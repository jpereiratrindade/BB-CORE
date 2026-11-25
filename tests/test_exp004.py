"""Testes do BB-CORE-EXP-004: configurações persistentes/versionadas, verificação
determinística, preservação de execuções, continuidade e rotas HTTP.
"""
import json
import sys
import tempfile
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from bbcore.analytics import build_discovery_continuity, list_exp003_runs
from bbcore.investigation_config import (
    DEFAULT_INVESTIGATION_CONFIG,
    get_investigation_settings,
    reset_investigation_settings,
    update_investigation_settings,
)
from bbcore.server import Handler
from bbcore.store import Archive

from tests.test_analytics import make_capsule  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'lab' / 'exp003'))
from confront_all import deterministic_verify  # noqa: E402


class Exp004Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / 'bb.sqlite'
        self.archive = Archive(self.db_path)
        self.archive.capture(make_capsule(
            title='Registro base',
            claim='A continuidade intelectual exige preservação de contexto.',
        ))
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.srv.archive = self.archive
        self.srv.read_token = 'r-tok'
        self.srv.write_token = 'w-tok'
        self.srv.browser_token = 'b-tok'
        self.srv.allowed_origins = set()
        self.srv.oauth_verifier = None
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        self.opener = build_opener(ProxyHandler({}))

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.archive.db.close()
        self.tmp.cleanup()

    def test_settings_persistence_validation_versioning_and_reset(self):
        s1 = get_investigation_settings(self.archive.db)
        self.assertEqual(s1['version'], 1)
        self.assertEqual(s1['config'], DEFAULT_INVESTIGATION_CONFIG)

        with self.assertRaises(ValueError):
            update_investigation_settings(self.archive.db, {'reference_temperature': 5.0})
        with self.assertRaises(ValueError):
            update_investigation_settings(self.archive.db, {'enabled_strategies': ['Z']})
        with self.assertRaises(ValueError):
            update_investigation_settings(self.archive.db, {'profile': 'invalid'})

        s2 = update_investigation_settings(
            self.archive.db,
            {'profile': 'exploration', 'seed': 101, 'exploratory_temperature': 0.35},
            change_note='Teste exploratório',
        )
        self.assertEqual(s2['version'], 2)
        self.assertEqual(s2['config']['profile'], 'exploration')
        self.assertEqual(s2['config']['seed'], 101)
        self.assertEqual(s2['config']['exploratory_temperature'], 0.35)

        # Reabrir banco garante persistência entre reinicializações sem alterar acervo canônico
        reopened = Archive(self.db_path)
        try:
            s_reloaded = get_investigation_settings(reopened.db)
            self.assertEqual(s_reloaded['version'], 2)
            self.assertEqual(s_reloaded['config']['seed'], 101)
            self.assertEqual(len(reopened.list()), 1)
        finally:
            reopened.db.close()

        s3 = reset_investigation_settings(self.archive.db)
        self.assertEqual(s3['version'], 3)
        self.assertEqual(s3['config'], DEFAULT_INVESTIGATION_CONFIG)
        self.assertEqual(len(s3['history']), 3)

    def test_http_settings_and_runs_routes(self):
        with self.opener.open(Request(f'http://127.0.0.1:{self.port}/settings.js'), timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn('settings-investigation-form', resp.read().decode('utf-8'))

        req_get = Request(
            f'http://127.0.0.1:{self.port}/api/settings/investigation',
            headers={'Authorization': 'Bearer r-tok'},
        )
        with self.opener.open(req_get, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            payload = json.load(resp)
            self.assertEqual(payload['config']['profile'], 'reference')

        req_put = Request(
            f'http://127.0.0.1:{self.port}/api/settings/investigation',
            method='PUT',
            headers={'Authorization': 'Bearer w-tok', 'Content-Type': 'application/json'},
            data=json.dumps({'profile': 'verification', 'confrontation_seed': 77}).encode('utf-8'),
        )
        with self.opener.open(req_put, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            updated = json.load(resp)
            self.assertEqual(updated['config']['profile'], 'verification')
            self.assertEqual(updated['config']['confrontation_seed'], 77)

        with self.assertRaises(HTTPError) as cm_bad:
            self.opener.open(
                Request(
                    f'http://127.0.0.1:{self.port}/api/settings/investigation',
                    method='PUT',
                    headers={'Authorization': 'Bearer w-tok', 'Content-Type': 'application/json'},
                    data=json.dumps({'context_window': 10}).encode('utf-8'),
                ),
                timeout=5,
            )
        self.assertEqual(cm_bad.exception.code, 400)

        req_runs = Request(
            f'http://127.0.0.1:{self.port}/api/analytics/runs',
            headers={'Authorization': 'Bearer r-tok'},
        )
        with self.opener.open(req_runs, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            runs_payload = json.load(resp)
            self.assertIn('runs', runs_payload)
            self.assertIn('continuity', runs_payload)

    def test_deterministic_verification_catches_inconsistencies(self):
        rec_by_id = {
            'r1': {'id': 'r1', 'title': 'R1', 'scope': '', 'claim': 'Preservar contexto importa.', 'why_matters': '', 'limitations': 'L1'},
            'r2': {'id': 'r2', 'title': 'R2', 'scope': '', 'claim': 'Continuidade exige identidade.', 'why_matters': '', 'limitations': 'L2'},
        }
        consistent_item = {
            'supporting_records': [
                {'record_id': 'r1', 'excerpts': ['Preservar contexto importa.']},
                {'record_id': 'r2', 'excerpts': ['Continuidade exige identidade.']},
            ],
        }
        good_assess = {
            'verdict': 'SUSTAINED_CANDIDATE',
            'already_explicit_in_single_record': False,
            'merely_summary_or_classification': False,
            'depends_on_integration': True,
            'records_sustain_interpretation': True,
            'adds_comprehension_or_investigation': True,
        }
        det_ok = deterministic_verify(consistent_item, rec_by_id, good_assess)
        self.assertEqual(det_ok['effective_status'], 'SUSTAINED_CANDIDATE')
        self.assertEqual(det_ok['inconsistencies'], [])

        # Incoerência: LLM disse SUSTAINED_CANDIDATE mas marcou already_explicit_in_single_record=True
        bad_assess = {**good_assess, 'already_explicit_in_single_record': True}
        det_bad = deterministic_verify(consistent_item, rec_by_id, bad_assess)
        self.assertEqual(det_bad['effective_status'], 'CONTESTED')
        self.assertFalse(det_bad['criteria_verdict_coherent'])
        self.assertTrue(len(det_bad['inconsistencies']) >= 1)

        # Avaliação ausente também deve ser explicitada
        det_missing = deterministic_verify(consistent_item, rec_by_id, None)
        self.assertEqual(det_missing['effective_status'], 'NOT_EXAMINED')
        self.assertIn('Avaliação crítica automatizada ausente para este candidato.', det_missing['inconsistencies'])

    def test_preserved_runs_and_continuity(self):
        base = Path(self.tmp.name) / 'exp003'
        for rid, prof, recs in [
            ('run-1', 'reference', [{'record_id': 'r1'}, {'record_id': 'r2'}, {'record_id': 'r3'}]),
            ('run-2', 'exploration', [{'record_id': 'r1'}, {'record_id': 'r2'}]),
        ]:
            rdir = base / 'runs' / rid
            rdir.mkdir(parents=True)
            (rdir / 'manifest.json').write_text(json.dumps({
                'run_id': rid, 'status': 'completed', 'profile': prof, 'config_version': 2,
                'formulation_basis': 'ORIGINAL_CANONICAL_RECORDS',
                'started_at': '2026-11-25T10:00:00Z', 'corpus_sha256': 'abc',
            }), encoding='utf-8')
            (rdir / 'results.json').write_text(json.dumps({
                'run_id': rid, 'profile': prof, 'config_version': 2,
                'executed_at': '2026-11-25T10:00:00Z',
                'strategy_a_integral': {'discoveries': [{
                    'discovery_id': f'{rid}-A-01',
                    'title': 'Continuidade intelectual e preservação de contexto',
                    'formulation': 'Preservar contexto sustenta continuidade intelectual entre ambientes.',
                    'supporting_records': recs,
                    'effective_status': 'SUSTAINED_CANDIDATE',
                }]},
            }), encoding='utf-8')

        runs = list_exp003_runs(base)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]['config_version'], 2)
        cont = build_discovery_continuity(base)
        self.assertEqual(cont['runs_compared'], 2)
        self.assertEqual(len(cont['links']), 1)
        self.assertEqual(cont['links'][0]['kind'], 'CANDIDATE_LEXICAL_OVERLAP_EXPANDED_GROUNDS')
        self.assertTrue(cont['links'][0]['heuristic_only'])

    def test_full_corpus_exceeds_30_and_concurrent_settings_updates(self):
        # Inserir 34 registros adicionais (total 35 > 30 do Archive.list padrão)
        for i in range(34):
            self.archive.capture(make_capsule(
                title=f'Registro extra {i:02d}',
                claim=f'Formulação original {i:02d} preservada.',
            ))
        req_corpus = Request(
            f'http://127.0.0.1:{self.port}/api/analytics/corpus',
            headers={'Authorization': 'Bearer r-tok'},
        )
        with self.opener.open(req_corpus, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            corpus = json.load(resp)
            self.assertEqual(corpus['total_records'], 35)
            self.assertEqual(len(corpus['records']), 35)
            self.assertEqual(corpus['formulation_basis'], 'ORIGINAL_CANONICAL_RECORDS')

        # Concorrência em configurações: 6 threads atualizando simultaneamente sem colisão de versão
        errors = []
        versions = []
        vlock = threading.Lock()

        def worker(idx):
            try:
                res = update_investigation_settings(
                    self.archive.db,
                    {'seed': 100 + idx},
                    change_note=f'Concorrente {idx}',
                    lock=self.archive.lock,
                )
                with vlock:
                    versions.append(res['version'])
            except Exception as exc:
                with vlock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(versions), 6)
        self.assertEqual(len(set(versions)), 6)


if __name__ == '__main__':
    unittest.main()
