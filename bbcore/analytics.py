"""Projeção analítica somente-leitura do acervo BB-CORE (grafo conceitual e calendário temporal).

Gera projeções reconstruíveis a partir do estado canônico (SQLite + diário BB-EVENT-1),
sem modificar registros, sem criar relações intelectuais reconhecidas e sem fallback
forçado para registros sem correspondência lexical.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections import OrderedDict, deque
from pathlib import Path

from .store import stamp

METHODOLOGY_VERSION = 'bb-analytics-lexicon/0.1.0'

FIELD_WEIGHTS = {
    'title': 3.0,
    'scope': 2.5,
    'claim': 2.0,
    'why_matters': 1.5,
    'limitations': 1.0,
}

# Léxico explícito, auditável e versionado (distinto de dimensões emergentes futuras).
PREDEFINED_DIMENSIONS = [
    {
        'id': 'continuidade-retomada',
        'label': 'Continuidade e Retomada',
        'origin': 'PREDEFINED_LEXICON',
        'color': '#1c9b98',
        'terms': [
            'continuidade', 'retomar', 'retomada', 'contexto de origem',
            'nova conversa', 'mobilização', 'trajetória', 'acontecimento',
        ],
    },
    {
        'id': 'identidade-preservacao',
        'label': 'Identidade e Preservação',
        'origin': 'PREDEFINED_LEXICON',
        'color': '#2563eb',
        'terms': [
            'identidade', 'preservação', 'preservar', 'imutabilidade',
            'equivalência', 'duplicação', 'legado', 'revisão',
        ],
    },
    {
        'id': 'proveniencia-fidelidade',
        'label': 'Proveniência e Fidelidade',
        'origin': 'PREDEFINED_LEXICON',
        'color': '#8a63d2',
        'terms': [
            'proveniência', 'fidelidade', 'origem', 'transcrição',
            'lacuna', 'âncora', 'autoria', 'integridade', 'representação',
        ],
    },
    {
        'id': 'arquitetura-escopo',
        'label': 'Arquitetura e Escopo',
        'origin': 'PREDEFINED_LEXICON',
        'color': '#d97706',
        'terms': [
            'arquitetura', 'escopo', 'suficiência', 'memória',
            'ambiente de elaboração', 'interface', 'mcp', 'etapa',
        ],
    },
    {
        'id': 'epistemologia-evidencia',
        'label': 'Epistemologia e Evidência',
        'origin': 'PREDEFINED_LEXICON',
        'color': '#4f7f52',
        'terms': [
            'epistemológic', 'epistêmic', 'evidência', 'validação',
            'empíric', 'resiliência', 'indicador', 'paramétrico', 'crítica',
        ],
    },
]


def _extract_fields(record):
    ctx = record.get('context') or {}
    return {
        'title': (record.get('title') or '').lower(),
        'scope': (ctx.get('scope') or '').lower(),
        'claim': (record.get('claim') or '').lower(),
        'why_matters': (ctx.get('why_matters') or '').lower(),
        'limitations': (record.get('limitations') or '').lower(),
    }


def _compute_topology(record_ids, edges):
    """Calcula componentes conexos emergentes e nós-ponte (articulação) apenas pela topologia."""
    adj = {rid: set() for rid in record_ids}
    for u, v in edges:
        if u in adj and v in adj and u != v:
            adj[u].add(v)
            adj[v].add(u)

    visited = set()
    clusters = []
    node_cluster = {}
    for rid in record_ids:
        if rid in visited:
            continue
        comp = []
        q = deque([rid])
        visited.add(rid)
        while q:
            cur = q.popleft()
            comp.append(cur)
            for nxt in adj[cur]:
                if nxt not in visited:
                    visited.add(nxt)
                    q.append(nxt)
        if len(comp) > 1:
            cid = f'cluster-{len(clusters) + 1}'
            clusters.append({'id': cid, 'record_ids': comp, 'size': len(comp)})
            for member in comp:
                node_cluster[member] = cid

    # Pontos de articulação (registros que conectam subgrupos distintos dentro de um componente)
    bridges = set()
    timer = [0]
    tin, low, seen = {}, {}, set()

    def dfs(u, parent=None):
        seen.add(u)
        timer[0] += 1
        tin[u] = low[u] = timer[0]
        children = 0
        for v in adj[u]:
            if v == parent:
                continue
            if v in seen:
                low[u] = min(low[u], tin[v])
            else:
                dfs(v, u)
                low[u] = min(low[u], low[v])
                if parent is not None and low[v] >= tin[u]:
                    bridges.add(u)
                children += 1
        if parent is None and children > 1:
            bridges.add(u)

    for rid in record_ids:
        if rid not in seen and adj[rid]:
            dfs(rid)

    isolated = [rid for rid in record_ids if not adj[rid]]
    return {
        'clusters': clusters,
        'node_cluster': node_cluster,
        'bridge_record_ids': sorted(bridges),
        'isolated_record_ids': isolated,
        'degrees': {rid: len(adj[rid]) for rid in record_ids},
    }


def _load_exp002_network(record_ids, exp002_path=None):
    path = Path(exp002_path) if exp002_path else (Path(__file__).resolve().parent.parent / 'lab' / 'exp002' / 'results.json')
    if not path.is_file():
        return {
            'source_available': False,
            'source_path': str(path),
            'mechanism': None,
            'executed_at': None,
            'candidate_connections': [],
            'abstained_count': 0,
            'concordant_connected_count': 0,
            'divergent_count': 0,
        }
    raw = json.loads(path.read_text(encoding='utf-8'))
    valid_ids = set(record_ids)
    candidates = []
    abstained = 0
    concordant = 0
    divergent = 0
    for pair in raw.get('pairs', []):
        aid = (pair.get('record_a') or {}).get('id')
        bid = (pair.get('record_b') or {}).get('id')
        if aid not in valid_ids or bid not in valid_ids:
            continue
        stability = pair.get('stability')
        if stability == 'CONCORDANT_ABSTAINED':
            abstained += 1
            continue
        if stability == 'CONCORDANT_CONNECTED':
            concordant += 1
        elif stability == 'DIVERGENT_ORDER_DEPENDENT':
            divergent += 1
        fwd = pair.get('forward_ab') or {}
        rev = pair.get('reverse_ba') or {}
        fwd_p = fwd.get('parsed') or {}
        rev_p = rev.get('parsed') or {}
        candidates.append({
            'id': f"exp002:{pair.get('pair_index')}",
            'source_id': aid,
            'target_id': bid,
            'mechanism': f"{raw.get('instruction', 'BB-CORE-EXP-002')} ({raw.get('model', 'LLM local')})",
            'executed_at': raw.get('executed_at'),
            'stability': stability,
            'epistemic_status': 'CANDIDATE_ANALYTICAL_CONNECTION',
            'nature': fwd_p.get('connection_nature') or rev_p.get('connection_nature'),
            'forward_ab': {
                'connection_proposed': fwd_p.get('connection_proposed'),
                'connection_nature': fwd_p.get('connection_nature'),
                'excerpts_a': fwd.get('excerpts_a_check', []),
                'excerpts_b': fwd.get('excerpts_b_check', []),
                'justification': fwd_p.get('justification'),
                'limitations': fwd_p.get('limitations', []),
                'abstention_reason': fwd_p.get('abstention_reason'),
            },
            'reverse_ba': {
                'connection_proposed': rev_p.get('connection_proposed'),
                'connection_nature': rev_p.get('connection_nature'),
                'excerpts_a': rev.get('excerpts_a_check', []),
                'excerpts_b': rev.get('excerpts_b_check', []),
                'justification': rev_p.get('justification'),
                'limitations': rev_p.get('limitations', []),
                'abstention_reason': rev_p.get('abstention_reason'),
            },
        })

    return {
        'source_available': True,
        'source_path': str(path),
        'mechanism': f"{raw.get('instruction', 'BB-CORE-EXP-002')} · {raw.get('model', '')}".strip(' ·'),
        'executed_at': raw.get('executed_at'),
        'candidate_connections': candidates,
        'abstained_count': abstained,
        'concordant_connected_count': concordant,
        'divergent_count': divergent,
    }


def _default_exp003_dir() -> Path:
    return Path(__file__).resolve().parent.parent / 'lab' / 'exp003'


def _resolve_exp003_results_path(exp003_path=None, run_id=None) -> Path:
    if exp003_path:
        return Path(exp003_path)
    base = _default_exp003_dir()
    if run_id:
        cand = base / 'runs' / run_id / 'results.json'
        if cand.is_file():
            return cand
    latest = base / 'latest.json'
    if latest.is_file():
        try:
            ptr = json.loads(latest.read_text(encoding='utf-8'))
            rid = ptr.get('run_id')
            if rid:
                cand = base / 'runs' / rid / 'results.json'
                if cand.is_file():
                    return cand
        except Exception:
            pass
    return base / 'results.json'


def list_exp003_runs(exp003_dir=None) -> list[dict]:
    """Lista execuções preservadas em lab/exp003/runs/, ordenadas da mais recente para a mais antiga."""
    base = Path(exp003_dir) if exp003_dir else _default_exp003_dir()
    runs_dir = base / 'runs'
    if not runs_dir.is_dir():
        return []
    runs = []
    for sub in sorted(runs_dir.iterdir(), reverse=True):
        if not sub.is_dir():
            continue
        manifest_file = sub / 'manifest.json'
        if not manifest_file.is_file():
            continue
        try:
            m = json.loads(manifest_file.read_text(encoding='utf-8'))
            runs.append({
                'run_id': m.get('run_id') or sub.name,
                'status': m.get('status'),
                'profile': m.get('profile'),
                'started_at': m.get('started_at'),
                'finished_at': m.get('finished_at'),
                'corpus_sha256': m.get('corpus_sha256'),
                'record_count': m.get('record_count'),
                'strategies_executed': m.get('strategies_executed', []),
                'effective_generation': m.get('effective_generation'),
                'confrontation_summary': m.get('confrontation_summary'),
                'methodological_limitations': m.get('methodological_limitations', []),
            })
        except Exception:
            continue
    return runs


def _token_set(text: str | None) -> set[str]:
    if not text:
        return set()
    return {t for t in ''.join(ch.lower() if ch.isalnum() else ' ' for ch in text).split() if len(t) > 3}


def build_discovery_continuity(exp003_dir=None) -> dict:
    """Identifica sinais candidatos de continuidade entre execuções preservadas, sem fusão automática."""
    base = Path(exp003_dir) if exp003_dir else _default_exp003_dir()
    runs_dir = base / 'runs'
    if not runs_dir.is_dir():
        return {'runs_compared': 0, 'links': []}

    occurrences = []
    run_ids_seen = set()
    for sub in sorted(runs_dir.iterdir()):
        res_file = sub / 'results.json'
        if not sub.is_dir() or not res_file.is_file():
            continue
        try:
            raw = json.loads(res_file.read_text(encoding='utf-8'))
        except Exception:
            continue
        rid = raw.get('run_id') or sub.name
        run_ids_seen.add(rid)
        profile = raw.get('profile') or 'reference'
        for strat, key in (
            ('A', 'strategy_a_integral'),
            ('B', 'strategy_b_semantic_neighborhood'),
            ('C', 'strategy_c_transversal_distant'),
            ('D', 'strategy_d_incremental'),
        ):
            grp = raw.get(key) or {}
            items = grp.get('final_discoveries' if strat == 'D' else 'discoveries') or []
            for item in items:
                status = item.get('effective_status') or 'NOT_EXAMINED'
                if status != 'SUSTAINED_CANDIDATE':
                    continue
                rec_ids = {s.get('record_id') for s in item.get('supporting_records', []) if s.get('record_id')}
                tokens = _token_set(f"{item.get('title', '')} {item.get('formulation', '')}")
                occurrences.append({
                    'run_id': rid,
                    'profile': profile,
                    'executed_at': raw.get('executed_at'),
                    'discovery_id': item.get('discovery_id'),
                    'strategy': strat,
                    'title': item.get('title'),
                    'record_ids': rec_ids,
                    'tokens': tokens,
                })

    links = []
    for i in range(len(occurrences)):
        for j in range(i + 1, len(occurrences)):
            a, b = occurrences[i], occurrences[j]
            if a['run_id'] == b['run_id']:
                continue
            union_tok = a['tokens'] | b['tokens']
            tok_sim = len(a['tokens'] & b['tokens']) / len(union_tok) if union_tok else 0.0
            rec_inter = a['record_ids'] & b['record_ids']
            rec_union = a['record_ids'] | b['record_ids']
            rec_sim = len(rec_inter) / len(rec_union) if rec_union else 0.0
            if tok_sim < 0.25 and rec_sim < 0.5:
                continue
            if a['record_ids'] == b['record_ids'] and tok_sim >= 0.45:
                kind = 'RECURRENCE'
            elif (a['record_ids'] < b['record_ids'] or b['record_ids'] > a['record_ids']) and tok_sim >= 0.30:
                kind = 'GROUND_EXPANSION'
            elif rec_inter and tok_sim >= 0.20:
                kind = 'CONCEPTUAL_REFORMULATION'
            else:
                kind = 'EXPERIMENTAL_SENSITIVITY'
            links.append({
                'kind': kind,
                'left_run_id': a['run_id'],
                'left_discovery_id': a['discovery_id'],
                'left_title': a['title'],
                'left_profile': a['profile'],
                'right_run_id': b['run_id'],
                'right_discovery_id': b['discovery_id'],
                'right_title': b['title'],
                'right_profile': b['profile'],
                'lexical_overlap': round(tok_sim, 3),
                'shared_records': sorted(rec_inter),
                'note': 'Sinal candidato de continuidade entre execuções; não constitui fusão automática nem equivalência reconhecida.',
            })

    return {'runs_compared': len(run_ids_seen), 'links': links}


def _load_exp003_discoveries(records_by_id, events_raw, exp003_path=None, run_id=None):
    path = _resolve_exp003_results_path(exp003_path=exp003_path, run_id=run_id)
    if not path.is_file():
        return {
            'source_available': False,
            'source_path': str(path),
            'run_id': run_id,
            'profile': None,
            'config_used': None,
            'corpus_sha256': None,
            'instruction': None,
            'executed_at': None,
            'llm_model': None,
            'embed_model': None,
            'confrontation_model': None,
            'same_model_limitation': False,
            'discoveries': [],
            'semantic_space': None,
            'abstentions_by_strategy': {},
            'counts': {'total': 0, 'sustained': 0, 'weak_or_redundant': 0, 'contested': 0, 'not_examined': 0, 'stale': 0},
            'runs': list_exp003_runs(),
            'continuity': build_discovery_continuity(),
        }

    raw = json.loads(path.read_text(encoding='utf-8'))
    executed_at = raw.get('executed_at')
    analyzed_versions = {r['id']: r.get('version') for r in raw.get('records', []) if r.get('id')}
    conf_model = raw.get('confrontation_model') or raw.get('llm_model')
    same_model_limitation = bool(raw.get('llm_model') and conf_model and raw.get('llm_model') == conf_model)

    # Detectar reformulações posteriores no diário BB-EVENT-1 para sinalizar descobertas potencialmente desatualizadas.
    revised_after = {}
    for ev in events_raw:
        if ev.get('event_type') == 'FORMULATION_REVISED':
            rec_at = ev.get('recorded_at') or ''
            if not executed_at or rec_at > executed_at:
                revised_after.setdefault(ev['insight_id'], []).append(ev['id'])

    assessments_by_id = {
        a['discovery_id']: a
        for a in ((raw.get('strategy_e_confrontation') or {}).get('parsed') or {}).get('assessments', [])
        if a.get('discovery_id')
    }

    strategy_specs = [
        ('A', 'Estratégia A · Leitura integral do acervo', (raw.get('strategy_a_integral') or {}).get('discoveries', [])),
        ('B', 'Estratégia B · Vizinhança semântica', (raw.get('strategy_b_semantic_neighborhood') or {}).get('discoveries', [])),
        ('C', 'Estratégia C · Exploração transversal distante', (raw.get('strategy_c_transversal_distant') or {}).get('discoveries', [])),
        ('D', 'Estratégia D · Incorporação incremental', (raw.get('strategy_d_incremental') or {}).get('final_discoveries', [])),
    ]

    discoveries = []
    counts = {'total': 0, 'sustained': 0, 'weak_or_redundant': 0, 'contested': 0, 'not_examined': 0, 'stale': 0}

    for strat_code, strat_label, items in strategy_specs:
        for idx, d in enumerate(items, 1):
            did = d.get('discovery_id') or f'EXP003-{executed_at}-{strat_code}-{idx:02d}'
            ver_map = {v['record_id']: v for v in d.get('verification', []) if v.get('record_id')}
            stale_reasons = []
            supporting = []
            for sr in d.get('supporting_records', []):
                rid = sr['record_id']
                cur_rec = records_by_id.get(rid)
                ver = ver_map.get(rid) or {}
                if cur_rec is None:
                    stale_reasons.append(f'Registro {rid} ausente no acervo atual')
                else:
                    if rid in analyzed_versions and cur_rec.get('version') != analyzed_versions[rid]:
                        stale_reasons.append(f'Versão do registro {rid} alterada ({analyzed_versions[rid]} → {cur_rec.get("version")})')
                    if rid in revised_after:
                        stale_reasons.append(f'Registro {rid} teve formulação revista após a execução')
                supporting.append({
                    'record_id': rid,
                    'record_title': cur_rec['title'] if cur_rec else rid,
                    'record_version_analyzed': analyzed_versions.get(rid),
                    'record_version_current': cur_rec.get('version') if cur_rec else None,
                    'specific_contribution': sr.get('specific_contribution'),
                    'excerpts': ver.get('excerpts') or [{'excerpt': ex, 'exact_match': None} for ex in sr.get('excerpts', [])],
                })

            assess = assessments_by_id.get(did)
            det_verif = d.get('deterministic_verification')
            verdict = (det_verif or {}).get('effective_status') or (assess['verdict'] if assess else 'NOT_EXAMINED')
            counts['total'] += 1
            if verdict == 'SUSTAINED_CANDIDATE':
                counts['sustained'] += 1
            elif verdict == 'WEAK_OR_REDUNDANT':
                counts['weak_or_redundant'] += 1
            elif verdict == 'CONTESTED':
                counts['contested'] += 1
            else:
                counts['not_examined'] += 1
            if stale_reasons:
                counts['stale'] += 1

            discoveries.append({
                'discovery_id': did,
                'strategy': strat_code,
                'strategy_label': strat_label,
                'title': d.get('title'),
                'description': d.get('description'),
                'nature': d.get('nature'),
                'formulation': d.get('formulation'),
                'supporting_records': supporting,
                'integration_justification': d.get('integration_justification'),
                'distinction_from_preserved_content': d.get('distinction_from_preserved_content'),
                'potential_relevance': d.get('potential_relevance'),
                'limitations_and_counterarguments': d.get('limitations_and_counterarguments', []),
                'investigation_possibilities': d.get('investigation_possibilities', []),
                'added_grounds': d.get('added_grounds', []),
                'deterministic_verification': det_verif,
                'confrontation': assess,
                'confrontation_status': verdict,
                'same_model_limitation': same_model_limitation,
                'human_recognition': {
                    'status': 'NOT_RECOGNIZED_IN_CANONICAL_ARCHIVE',
                    'note': 'Proposição candidata fora do acervo canônico; reconhecimento intelectual humano não realizado.',
                },
                'stale': bool(stale_reasons),
                'stale_reasons': stale_reasons,
                'epistemic_notice': 'Proposição analítica candidata; veredito automatizado não constitui validação científica nem conhecimento canônico.',
            })

    emb = raw.get('embeddings') or {}
    return {
        'source_available': True,
        'source_path': str(path),
        'run_id': raw.get('run_id'),
        'profile': raw.get('profile'),
        'config_used': raw.get('config_used'),
        'corpus_sha256': raw.get('corpus_sha256'),
        'instruction': raw.get('instruction', 'BB-CORE-EXP-003'),
        'executed_at': executed_at,
        'llm_model': raw.get('llm_model'),
        'embed_model': raw.get('embed_model'),
        'confrontation_model': conf_model,
        'same_model_limitation': same_model_limitation,
        'discoveries': discoveries,
        'counts': counts,
        'semantic_space': {
            'embed_model': raw.get('embed_model'),
            'timings_s': emb.get('timings_s'),
            'similarity_full': emb.get('similarity_full', []),
            'similarity_claim': emb.get('similarity_claim', []),
            'similarity_why_matters': emb.get('similarity_why_matters', []),
            'similarity_limitations': emb.get('similarity_limitations', []),
            'epistemic_note': 'Proximidade vetorial auxiliar de seleção de contexto; não equivale a relação intelectual reconhecida.',
        },
        'abstentions_by_strategy': {
            'A': (raw.get('strategy_a_integral') or {}).get('abstentions', []),
            'B': (raw.get('strategy_b_semantic_neighborhood') or {}).get('abstentions', []),
            'C': (raw.get('strategy_c_transversal_distant') or {}).get('abstentions', []),
        },
        'runs': list_exp003_runs(),
        'continuity': build_discovery_continuity(),
    }


def build_overview(archive, *, exp002_path=None, exp003_path=None, run_id=None):
    """Constrói projeção analítica completa (descobertas + rede + grafo lexical + calendário) em fotografia transacional."""
    with archive.events.snapshot():
        rows = archive.db.execute(
            'SELECT i.id, i.title, i.claim, i.limitations, i.context, i.status, i.version, i.created_at, '
            'e.kind, e.work_state '
            'FROM insights i LEFT JOIN record_elaborations e ON e.insight_id = i.id '
            'ORDER BY i.created_at DESC, i.rowid DESC'
        ).fetchall()

        records = []
        for row in rows:
            rec = dict(row)
            rec['context'] = json.loads(rec['context']) if isinstance(rec['context'], str) else (rec['context'] or {})
            records.append(rec)

        bundle = archive.events._verified()
        events_raw = bundle['events']

        rel_rows = archive.db.execute(
            'SELECT id, left_id, right_id, rationale, counterpoint, status, created_at '
            'FROM relations ORDER BY created_at DESC'
        ).fetchall()

    # Mapear revisões/atribuições de relações a partir do diário já verificado.
    relation_events = {}
    for ev in events_raw:
        if ev.get('event_type') in ('RELATION_RECOGNIZED', 'RELATION_CONTESTED'):
            rid = (ev.get('content') or {}).get('relation_id')
            if rid:
                relation_events.setdefault(rid, []).append({
                    'event_id': ev['id'],
                    'event_type': ev['event_type'],
                    'mode': ev['mode'],
                    'occurred_at': ev.get('occurred_at'),
                    'recorded_at': ev['recorded_at'],
                    'responsible': ev.get('responsible'),
                })

    registered_relations = []
    for r in rel_rows:
        rel = dict(r)
        rel['attributions'] = relation_events.get(rel['id'], [])
        registered_relations.append(rel)

    # Inferir associações conceituais sem fallback forçado.
    dim_map = OrderedDict((d['id'], {
        'id': d['id'],
        'label': d['label'],
        'origin': d['origin'],
        'color': d['color'],
        'record_count': 0,
        'record_ids': [],
        'total_score': 0.0,
    }) for d in PREDEFINED_DIMENSIONS)

    associations = []
    nodes = []
    unclassified_ids = []

    for rec in records:
        fields = _extract_fields(rec)
        matched_dims = []
        for dim in PREDEFINED_DIMENSIONS:
            evidence = []
            score = 0.0
            for field_name, field_text in fields.items():
                if not field_text:
                    continue
                f_weight = FIELD_WEIGHTS[field_name]
                for term in dim['terms']:
                    if term in field_text:
                        evidence.append({
                            'field': field_name,
                            'field_weight': f_weight,
                            'term': term,
                            'contribution': f_weight,
                        })
                        score += f_weight
            if score > 0:
                score = round(score, 4)
                associations.append({
                    'insight_id': rec['id'],
                    'dimension_id': dim['id'],
                    'dimension_label': dim['label'],
                    'category_origin': dim['origin'],
                    'absolute_score': score,
                    'normalized_weight': 0.0,  # preenchido após max_score
                    'evidence': evidence,
                })
                matched_dims.append(dim['id'])
                dim_entry = dim_map[dim['id']]
                dim_entry['record_count'] += 1
                dim_entry['record_ids'].append(rec['id'])
                dim_entry['total_score'] = round(dim_entry['total_score'] + score, 4)

        is_unclassified = len(matched_dims) == 0
        if is_unclassified:
            unclassified_ids.append(rec['id'])

        nodes.append({
            'id': rec['id'],
            'title': rec['title'],
            'status': rec['status'],
            'kind': rec.get('kind'),
            'work_state': rec.get('work_state'),
            'created_at': rec['created_at'],
            'matched_dimensions': matched_dims,
            'unclassified': is_unclassified,
        })

    max_score = max((a['absolute_score'] for a in associations), default=1.0) or 1.0
    for assoc in associations:
        assoc['normalized_weight'] = round(assoc['absolute_score'] / max_score, 4)

    active_dimensions = [d for d in dim_map.values() if d['record_count'] > 0]

    # Projeção de acontecimentos para o calendário temporal.
    record_dims_by_id = {n['id']: n['matched_dimensions'] for n in nodes}
    calendar_events = []
    for ev in events_raw:
        ev_dims = set(record_dims_by_id.get(ev['insight_id'], []))
        if ev.get('related_insight_id'):
            ev_dims.update(record_dims_by_id.get(ev['related_insight_id'], []))
        calendar_events.append({
            'id': ev['id'],
            'seq': ev['seq'],
            'insight_id': ev['insight_id'],
            'related_insight_id': ev.get('related_insight_id'),
            'event_type': ev['event_type'],
            'mode': ev['mode'],
            'category': 'NEW_RECORD' if ev['event_type'] == 'INSIGHT_REGISTERED' else 'SUBSEQUENT_EVENT',
            'recorded_at': ev['recorded_at'],
            'occurred_at': ev.get('occurred_at'),
            'summary': (ev.get('content') or {}).get('summary', ''),
            'responsible_name': (ev.get('responsible') or {}).get('name') if ev.get('responsible') else None,
            'dimensions': sorted(ev_dims),
        })

    record_ids = [n['id'] for n in nodes]
    records_by_id = {r['id']: r for r in records}
    exp002 = _load_exp002_network(record_ids, exp002_path=exp002_path)
    exp003 = _load_exp003_discoveries(records_by_id, events_raw, exp003_path=exp003_path, run_id=run_id)
    topology_edges = [(c['source_id'], c['target_id']) for c in exp002['candidate_connections']]
    topology_edges.extend((r['left_id'], r['right_id']) for r in registered_relations)
    topology = _compute_topology(record_ids, topology_edges)

    return {
        'methodology': {
            'version': METHODOLOGY_VERSION,
            'computed_at': stamp(),
            'reconstructible': True,
            'record_universe_count': len(records),
            'event_universe_count': len(calendar_events),
            'field_weights': FIELD_WEIGHTS,
            'lexicon': [
                {'id': d['id'], 'label': d['label'], 'origin': d['origin'], 'terms': d['terms']}
                for d in PREDEFINED_DIMENSIONS
            ],
            'epistemic_note': (
                'Projeção analítica reconstruível somente-leitura. Descobertas candidatas, '
                'conexões analíticas e associações lexicais não constituem relações reconhecidas nem conhecimento canônico.'
            ),
        },
        'discoveries_overview': exp003,
        'record_network': {
            'nodes': nodes,
            'candidate_connections': exp002['candidate_connections'],
            'registered_relations': registered_relations,
            'topology': topology,
            'source_available': exp002['source_available'],
            'mechanism': exp002['mechanism'],
            'executed_at': exp002.get('executed_at'),
            'abstained_count': exp002['abstained_count'],
            'concordant_connected_count': exp002['concordant_connected_count'],
            'divergent_count': exp002['divergent_count'],
        },
        'graph': {
            'anchors': nodes,
            'dimensions': active_dimensions,
            'all_dimensions': list(dim_map.values()),
            'inferred_associations': associations,
            'max_absolute_score': max_score if associations else 0.0,
            'unclassified_record_ids': unclassified_ids,
            'registered_relations': registered_relations,
        },
        'calendar': {
            'events': calendar_events,
            'total_events': len(calendar_events),
            'new_record_events': sum(1 for e in calendar_events if e['category'] == 'NEW_RECORD'),
            'subsequent_events': sum(1 for e in calendar_events if e['category'] == 'SUBSEQUENT_EVENT'),
            'without_occurred_at': sum(1 for e in calendar_events if not e['occurred_at']),
        },
    }


_EXP003_LOCK = threading.Lock()
_EXP003_STATE = {
    'status': 'idle',  # 'idle' | 'running' | 'completed' | 'error'
    'stage': None,
    'started_at': None,
    'finished_at': None,
    'error': None,
}


def get_exp003_status():
    """Retorna o estado atual da execução sob demanda do experimento EXP-003."""
    with _EXP003_LOCK:
        return dict(_EXP003_STATE)


def _run_exp003_worker(run_script: Path, confront_script: Path, workdir: Path, config: dict | None):
    cfg_file = None
    try:
        cfg = dict(config or {})
        profile = cfg.get('profile', 'reference')
        repetitions = int(cfg.get('exploratory_repetitions', 1)) if profile == 'exploration' else 1
        base_seed = int(cfg.get('seed', 42))

        if cfg:
            cfg_file = workdir / '.active_run_config.json'
            cfg_file.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')

        for rep in range(repetitions):
            rep_seed = base_seed + rep
            rep_note = f' (repetição {rep + 1}/{repetitions}, seed={rep_seed})' if repetitions > 1 else ''
            with _EXP003_LOCK:
                _EXP003_STATE['stage'] = f'Executando síntese semântica (perfil {profile}){rep_note}…'
            cmd1 = [sys.executable, str(run_script), '--seed', str(rep_seed)]
            if cfg_file is not None:
                cmd1.extend(['--config-json', str(cfg_file)])
            res1 = subprocess.run(cmd1, cwd=str(workdir), capture_output=True, text=True, check=False)
            if res1.returncode != 0:
                err_msg = (res1.stderr or res1.stdout or f'Código de saída {res1.returncode}').strip().splitlines()[-1]
                raise RuntimeError(f'Falha na etapa de síntese: {err_msg}')

            with _EXP003_LOCK:
                _EXP003_STATE['stage'] = f'Aplicando confrontação crítica e verificação determinística{rep_note}…'
            res2 = subprocess.run(
                [sys.executable, str(confront_script)],
                cwd=str(workdir),
                capture_output=True,
                text=True,
                check=False,
            )
            if res2.returncode != 0:
                err_msg = (res2.stderr or res2.stdout or f'Código de saída {res2.returncode}').strip().splitlines()[-1]
                raise RuntimeError(f'Falha na confrontação crítica: {err_msg}')

        with _EXP003_LOCK:
            _EXP003_STATE['status'] = 'completed'
            _EXP003_STATE['stage'] = 'Nova análise concluída e preservada.'
            _EXP003_STATE['finished_at'] = stamp()
            _EXP003_STATE['error'] = None
    except Exception as exc:
        with _EXP003_LOCK:
            _EXP003_STATE['status'] = 'error'
            _EXP003_STATE['stage'] = 'Execução interrompida por erro.'
            _EXP003_STATE['finished_at'] = stamp()
            _EXP003_STATE['error'] = str(exc)
    finally:
        if cfg_file is not None and cfg_file.is_file():
            try:
                cfg_file.unlink()
            except OSError:
                pass


def start_exp003_run(exp003_dir=None, *, config: dict | None = None):
    """Inicia a reexecução assíncrona de EXP-003/004 sobre o acervo ativo com a configuração vigente."""
    workdir = Path(exp003_dir) if exp003_dir else _default_exp003_dir()
    run_script = workdir / 'run_exp003.py'
    confront_script = workdir / 'confront_all.py'
    if not run_script.is_file() or not confront_script.is_file():
        raise FileNotFoundError('Scripts de execução do EXP-003 não encontrados no runtime.')

    with _EXP003_LOCK:
        if _EXP003_STATE['status'] == 'running':
            raise RuntimeError('EXP003_ALREADY_RUNNING')
        _EXP003_STATE['status'] = 'running'
        _EXP003_STATE['stage'] = 'Iniciando análise semântica com perfil vigente…'
        _EXP003_STATE['started_at'] = stamp()
        _EXP003_STATE['finished_at'] = None
        _EXP003_STATE['error'] = None
        snapshot = dict(_EXP003_STATE)

    t = threading.Thread(
        target=_run_exp003_worker,
        args=(run_script, confront_script, workdir, config),
        daemon=True,
    )
    t.start()
    return snapshot
