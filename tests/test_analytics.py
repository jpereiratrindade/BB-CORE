import json
import tempfile
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from bbcore.analytics import METHODOLOGY_VERSION, build_overview
from bbcore.server import Handler
from bbcore.store import Archive

from test_core import capsule


def make_capsule(**overrides):
    data = capsule()
    data.update(overrides)
    return data


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.archive = Archive(Path(self.tmp.name) / 'bb.sqlite')

    def tearDown(self):
        self.archive.db.close()
        self.tmp.cleanup()

    def test_lexical_inference_no_fallback_auditability_and_calendar_counts(self):
        # 1. Registro com correspondência clara (continuidade + proveniência)
        r1 = self.archive.capture(make_capsule(
            title='Continuidade e proveniência da retomada',
            claim='A continuidade intelectual preserva a identidade e a proveniência.',
            why_matters='Evita perda de contexto de origem.',
            limitations='Sem transcrição integral.',
            context={'scope': 'continuidade e retomada', 'missing': ['Transcrição']},
        ))
        # 2. Registro sem correspondência lexical -> deve permanecer isolado (sem fallback!)
        r2 = self.archive.capture(make_capsule(
            title='Nota botânica sobre flora local',
            claim='Espécies nativas apresentam fenologia sazonal distinta.',
            why_matters='Observação descritiva de campo.',
            limitations='Amostra reduzida.',
            context={'scope': 'botânica descritiva', 'missing': []},
        ))
        # 3. Acontecimento posterior sem occurred_at em r1
        self.archive.events.append({
            'request_id': str(uuid.uuid4()),
            'insight_id': r1['id'],
            'event_type': 'CRITIQUE_RECORDED',
            'mode': 'REPORTED',
            'occurred_at': None,
            'origin': 'Nota de revisão',
            'responsible': {'id': 'pesquisador', 'name': 'Pesquisador'},
            'content': {'summary': 'Observação posterior sem data declarada.'},
            'evidence': [],
            'missing': [],
            'limitations': 'Sem data declarada.',
            'confirmed': True,
        })
        # 4. Relação candidata explícita entre r1 e r2
        rel = self.archive.relate({
            'request_id': str(uuid.uuid4()),
            'left_id': r1['id'],
            'right_id': r2['id'],
            'rationale': 'Comparação metodológica de escopo',
            'counterpoint': 'Domínios distintos',
            'responsible': {'id': 'pesquisador', 'name': 'Pesquisador'},
            'origin': 'Exame local',
            'evidence': [],
        })

        overview = build_overview(self.archive)
        self.assertEqual(overview['methodology']['version'], METHODOLOGY_VERSION)
        self.assertTrue(overview['methodology']['reconstructible'])
        self.assertEqual(overview['methodology']['record_universe_count'], 2)

        graph = overview['graph']
        self.assertEqual(graph['unclassified_record_ids'], [r2['id']])
        anchors = {a['id']: a for a in graph['anchors']}
        self.assertTrue(anchors[r2['id']]['unclassified'])
        self.assertEqual(anchors[r2['id']]['matched_dimensions'], [])
        self.assertFalse(anchors[r1['id']]['unclassified'])

        # Auditar pontuação absoluta, normalizada e evidências de r1
        r1_assocs = [a for a in graph['inferred_associations'] if a['insight_id'] == r1['id']]
        self.assertTrue(len(r1_assocs) >= 2)
        for a in r1_assocs:
            self.assertEqual(a['category_origin'], 'PREDEFINED_LEXICON')
            self.assertGreater(a['absolute_score'], 0)
            self.assertGreater(a['normalized_weight'], 0)
            self.assertLessEqual(a['normalized_weight'], 1.0)
            self.assertEqual(round(sum(e['contribution'] for e in a['evidence']), 4), a['absolute_score'])

        # Relações registradas separadas das associações inferidas
        self.assertEqual(len(graph['registered_relations']), 1)
        self.assertEqual(graph['registered_relations'][0]['id'], rel['id'])

        # Calendário: 2 INSIGHT_REGISTERED + 1 CRITIQUE_RECORDED + 1 RELATION_PROPOSED = 4
        cal = overview['calendar']
        self.assertEqual(cal['total_events'], 4)
        self.assertEqual(cal['new_record_events'], 2)
        self.assertEqual(cal['subsequent_events'], 2)
        self.assertEqual(cal['without_occurred_at'], 2)  # CRITIQUE_RECORDED + RELATION_PROPOSED


class AnalyticsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.archive = Archive(Path(self.tmp.name) / 'bb.sqlite')
        self.archive.capture(make_capsule(
            title='Continuidade no BB-CORE',
            claim='A continuidade intelectual preserva identidade.',
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

    def test_analytics_overview_and_asset_routes(self):
        with self.assertRaises(HTTPError) as cm:
            self.opener.open(Request(f'http://127.0.0.1:{self.port}/api/analytics/overview'), timeout=5)
        self.assertEqual(cm.exception.code, 401)

        req = Request(
            f'http://127.0.0.1:{self.port}/api/analytics/overview',
            headers={'Authorization': 'Bearer r-tok'},
        )
        with self.opener.open(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.load(resp)
            self.assertEqual(data['methodology']['version'], METHODOLOGY_VERSION)
            self.assertEqual(len(data['graph']['anchors']), 1)

        with self.opener.open(Request(f'http://127.0.0.1:{self.port}/analytics.js'), timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            js = resp.read().decode('utf-8')
            self.assertIn('/api/analytics/overview', js)


if __name__ == '__main__':
    unittest.main()
