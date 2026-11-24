"""BB-CORE-EXP-001 v0.1.0 — Laboratório isolado de síntese conceitual com LLM local.

Lê apenas os registros canônicos via API somente-leitura do BB-CORE e executa os
Experimentos A (individual), B (coletivo) e C (incremental em duas ordens) no Ollama local,
sem fornecer dimensões, palavras-chave ou quantidades predefinidas.
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

MODEL = 'qwen2.5:14b'
OLLAMA_URL = 'http://127.0.0.1:11434/api/chat'
BBCORE_URL = 'http://127.0.0.1:8789'
OUT_DIR = Path(__file__).resolve().parent

NO_PRIOR_TAXONOMY_SYSTEM = (
    'Você é um analista conceitual operando sobre registros intelectuais do sistema BB-CORE.\n'
    'REGRAS EPISTEMOLÓGICAS ESTRITAS:\n'
    '1. Não presuma nenhuma taxonomia, lista de categorias ou quantidade de dimensões.\n'
    '2. Toda dimensão conceitual proposta deve emergir exclusivamente dos textos fornecidos.\n'
    '3. Fundamente cada associação com trechos literais dos registros.\n'
    '4. Se não houver fundamento suficiente para propor uma dimensão ou associar um registro, '
    'abstenha-se explicitamente e explique o motivo.\n'
    '5. Uma associação conceitual não é relação causal nem validação científica.\n'
    '6. Não atribua pontuações numéricas.\n'
    'Responda exclusivamente em português e estritamente no formato JSON solicitado.'
)


def load_bbcore_records():
    secret = Path.home() / '.config/bb-core/secret.env'
    cfg = dict(
        line.split('=', 1)
        for line in secret.read_text(encoding='utf-8').splitlines()
        if '=' in line and not line.startswith('#')
    )
    opener = build_opener(ProxyHandler({}))

    def get_json(path):
        req = Request(BBCORE_URL + path, headers={'Authorization': 'Bearer ' + cfg['BB_READ_TOKEN']})
        with opener.open(req, timeout=10) as resp:
            return json.load(resp)

    listing = get_json('/api/insights')['items']
    records = []
    for item in listing:
        ctx = get_json(f'/api/insights/{item["id"]}/context')
        elab = ctx.get('elaboration') or {}
        c = ctx.get('context') or {}
        records.append({
            'id': ctx['id'],
            'version': ctx['version'],
            'created_at': ctx['created_at'],
            'title': ctx['title'],
            'kind': elab.get('kind'),
            'work_state': elab.get('work_state'),
            'claim': ctx['claim'],
            'why_matters': c.get('why_matters'),
            'scope': c.get('scope'),
            'limitations': ctx['limitations'],
            'missing': c.get('missing', []),
        })
    # Ordenação cronológica de criação (002..007)
    records.sort(key=lambda r: (r['created_at'], r['title']))
    return records


def call_ollama(prompt, schema):
    opener = build_opener(ProxyHandler({}))
    payload = {
        'model': MODEL,
        'stream': False,
        'format': schema,
        'options': {'temperature': 0.1, 'num_ctx': 16384},
        'messages': [
            {'role': 'system', 'content': NO_PRIOR_TAXONOMY_SYSTEM},
            {'role': 'user', 'content': prompt},
        ],
    }
    t0 = time.monotonic()
    req = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    with opener.open(req, timeout=240) as resp:
        raw = json.load(resp)
    elapsed = round(time.monotonic() - t0, 2)
    parsed = json.loads(raw['message']['content'])
    return {
        'result': parsed,
        'metrics': {
            'elapsed_s': elapsed,
            'prompt_eval_count': raw.get('prompt_eval_count'),
            'eval_count': raw.get('eval_count'),
            'total_duration_ns': raw.get('total_duration'),
        },
    }


SCHEMA_INDIVIDUAL = {
    'type': 'object',
    'properties': {
        'concepts_identified': {'type': 'array', 'items': {'type': 'string'}},
        'proposed_dimensions': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string'},
                    'definition': {'type': 'string'},
                    'supporting_excerpts': {'type': 'array', 'items': {'type': 'string'}},
                    'justification': {'type': 'string'},
                },
                'required': ['name', 'definition', 'supporting_excerpts', 'justification'],
            },
        },
        'abstentions': {'type': 'array', 'items': {'type': 'string'}},
        'limitations': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['concepts_identified', 'proposed_dimensions', 'abstentions', 'limitations'],
}

SCHEMA_COLLECTIVE = {
    'type': 'object',
    'properties': {
        'proposed_dimensions': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string'},
                    'definition': {'type': 'string'},
                    'associated_records': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'record_id': {'type': 'string'},
                                'supporting_excerpts': {'type': 'array', 'items': {'type': 'string'}},
                                'justification': {'type': 'string'},
                            },
                            'required': ['record_id', 'supporting_excerpts', 'justification'],
                        },
                    },
                },
                'required': ['name', 'definition', 'associated_records'],
            },
        },
        'singularities': {'type': 'array', 'items': {'type': 'string'}},
        'abstentions': {'type': 'array', 'items': {'type': 'string'}},
        'limitations': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['proposed_dimensions', 'singularities', 'abstentions', 'limitations'],
}

SCHEMA_INCREMENTAL = {
    'type': 'object',
    'properties': {
        'recognized_existing_dimensions': {'type': 'array', 'items': {'type': 'string'}},
        'newly_proposed_dimensions': {'type': 'array', 'items': {'type': 'string'}},
        'revisions_to_prior_associations': {'type': 'array', 'items': {'type': 'string'}},
        'differentiations': {'type': 'array', 'items': {'type': 'string'}},
        'dimensions_state': SCHEMA_COLLECTIVE['properties']['proposed_dimensions'],
        'abstentions': {'type': 'array', 'items': {'type': 'string'}},
        'limitations': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': [
        'recognized_existing_dimensions', 'newly_proposed_dimensions',
        'revisions_to_prior_associations', 'differentiations',
        'dimensions_state', 'abstentions', 'limitations',
    ],
}


def format_record(r):
    return (
        f"ID: {r['id']} (versão {r['version']}, tipo {r['kind']}, estado {r['work_state']})\n"
        f"Título: {r['title']}\n"
        f"Escopo declarado: {r['scope']}\n"
        f"Formulação: {r['claim']}\n"
        f"Relevância: {r['why_matters']}\n"
        f"Limitações: {r['limitations']}"
    )


def run_all():
    records = load_bbcore_records()
    started_at = datetime.now(timezone.utc).isoformat(timespec='seconds')

    # Experimento A — Análise individual
    exp_a = []
    for r in records:
        prompt = (
            'Analise isoladamente o seguinte registro intelectual do BB-CORE.\n'
            'Identifique os conceitos centrais e proponha possíveis dimensões conceituais emergentes '
            'com fundamentação textual literal e limitações. Abstenha-se quando não houver base suficiente.\n\n'
            + format_record(r)
        )
        res = call_ollama(prompt, SCHEMA_INDIVIDUAL)
        exp_a.append({'record_id': r['id'], 'title': r['title'], **res})

    # Experimento B — Análise coletiva
    prompt_b = (
        'Analise conjuntamente todos os registros intelectuais abaixo do BB-CORE.\n'
        'Produza uma síntese conceitual emergente identificando dimensões compartilhadas, '
        'singularidades, associações fundamentadas por trechos literais, abstenções e limitações.\n'
        'Não há quantidade pré-definida de dimensões.\n\n'
        + '\n\n---\n\n'.join(format_record(r) for r in records)
    )
    exp_b = call_ollama(prompt_b, SCHEMA_COLLECTIVE)

    # Experimento C — Análise incremental em duas ordens
    def run_incremental(ordered_records, label):
        steps = []
        prior_state = []
        for idx, r in enumerate(ordered_records, 1):
            prompt_c = (
                f'Etapa incremental {idx}/{len(ordered_records)} ({label}).\n'
                'Você recebe um novo registro incorporado ao acervo e o estado analítico acumulado até a etapa anterior.\n'
                'Examine se o novo registro:\n'
                '- se associa a dimensões anteriormente propostas;\n'
                '- exige propor novas dimensões;\n'
                '- leva a revisar associações anteriores;\n'
                '- exige diferenciar dimensões aparentemente semelhantes;\n'
                '- ou requer abstenção por falta de fundamento suficiente.\n\n'
                f'ESTADO ANALÍTICO ANTERIOR:\n{json.dumps(prior_state, ensure_ascii=False, indent=2)}\n\n'
                f'NOVO REGISTRO INCORPORADO:\n{format_record(r)}'
            )
            res = call_ollama(prompt_c, SCHEMA_INCREMENTAL)
            prior_state = res['result']['dimensions_state']
            steps.append({'step': idx, 'record_id': r['id'], 'title': r['title'], **res})
        return steps

    exp_c1 = run_incremental(records, 'ordem cronológica')
    exp_c2 = run_incremental(list(reversed(records)), 'ordem inversa')

    ollama_ps = subprocess.run(['ollama', 'ps'], capture_output=True, text=True, check=False).stdout.strip()

    output = {
        'instruction': 'BB-CORE-EXP-001 v0.1.0',
        'executed_at': started_at,
        'model': MODEL,
        'parameters': {'temperature': 0.1, 'num_ctx': 16384},
        'ollama_ps': ollama_ps,
        'records_analyzed': [{'id': r['id'], 'version': r['version'], 'title': r['title']} for r in records],
        'experiment_a_individual': exp_a,
        'experiment_b_collective': exp_b,
        'experiment_c1_incremental_chronological': exp_c1,
        'experiment_c2_incremental_reverse': exp_c2,
    }
    out_file = OUT_DIR / 'results.json'
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SAVED:', out_file)
    print('OLLAMA_PS:\n' + ollama_ps)


if __name__ == '__main__':
    run_all()
