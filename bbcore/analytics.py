"""Projeção analítica somente-leitura do acervo BB-CORE (grafo conceitual e calendário temporal).

Gera projeções reconstruíveis a partir do estado canônico (SQLite + diário BB-EVENT-1),
sem modificar registros, sem criar relações intelectuais reconhecidas e sem fallback
forçado para registros sem correspondência lexical.
"""
from __future__ import annotations

import json
from collections import OrderedDict

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


def build_overview(archive):
    """Constrói projeção analítica completa (grafo + calendário) em fotografia transacional."""
    with archive.events.snapshot():
        rows = archive.db.execute(
            'SELECT i.id, i.title, i.claim, i.limitations, i.context, i.status, i.created_at, '
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
                'Projeção analítica reconstruível somente-leitura. Associações lexicais '
                'não constituem relações intelectuais reconhecidas nem alteram o acervo.'
            ),
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
