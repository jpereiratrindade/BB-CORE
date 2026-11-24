"""BB-CORE-EXP-003 v0.2.0 — Descoberta semântica e abstração intelectual.

Experimento isolado sobre os 6 registros reais (002..007) do BB-CORE:
1. Representações vetoriais locais (qwen3-embedding:4b) integral e por campos.
2. Estratégias A (leitura integral), B (vizinhança semântica), C (transversal distante),
   D (incorporação incremental com estado determinístico fora da LLM),
   E (reexame coletivo e confrontação crítica independente segundo os 7 critérios).
"""
from __future__ import annotations

import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

LLM_MODEL = 'qwen2.5:14b'
EMBED_MODEL = 'qwen3-embedding:4b'
OLLAMA_CHAT_URL = 'http://127.0.0.1:11434/api/chat'
OLLAMA_EMBED_URL = 'http://127.0.0.1:11434/api/embed'
BBCORE_URL = 'http://127.0.0.1:8789'
OUT_DIR = Path(__file__).resolve().parent

SYSTEM_DISCOVERY = (
    'Você é um investigador analítico examinando registros intelectuais preservados no BB-CORE.\n'
    'OBJETIVO: Investigar o que pode ser DESCOBERTO a partir da integração dos conhecimentos fornecidos — '
    'estruturas conceituais, processos, princípios, tensões, lacunas, complementaridades ou possibilidades investigativas '
    'que não ficam suficientemente perceptíveis na leitura isolada.\n'
    'REGRAS ESTRITAS:\n'
    '1. Não presuma taxonomias, quantidades mínimas de descobertas ou pontuações numéricas.\n'
    '2. Não produza meros resumos individuais nem classificações temáticas vazias.\n'
    '3. Distinga claramente o que está explicitamente preservado nos registros daquilo que emerge como abstração ou descoberta.\n'
    '4. Fundamente cada descoberta com trechos literais exatos dos registros.\n'
    '5. Se nada novo emergir com fundamento suficiente, abstenha-se explicitamente.\n'
    'Responda em português e estritamente no formato JSON solicitado.'
)

DISCOVERY_ITEM_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'},
        'description': {'type': 'string'},
        'nature': {'type': 'string'},
        'formulation': {'type': 'string'},
        'supporting_records': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'record_id': {'type': 'string'},
                    'excerpts': {'type': 'array', 'items': {'type': 'string'}},
                    'specific_contribution': {'type': 'string'},
                },
                'required': ['record_id', 'excerpts', 'specific_contribution'],
            },
        },
        'integration_justification': {'type': 'string'},
        'distinction_from_preserved_content': {'type': 'string'},
        'potential_relevance': {'type': 'string'},
        'limitations_and_counterarguments': {'type': 'array', 'items': {'type': 'string'}},
        'investigation_possibilities': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': [
        'title', 'description', 'nature', 'formulation', 'supporting_records',
        'integration_justification', 'distinction_from_preserved_content',
        'potential_relevance', 'limitations_and_counterarguments', 'investigation_possibilities',
    ],
}

DISCOVERY_LIST_SCHEMA = {
    'type': 'object',
    'properties': {
        'discoveries': {'type': 'array', 'items': DISCOVERY_ITEM_SCHEMA},
        'abstentions': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['discoveries', 'abstentions'],
}

INCREMENTAL_OPS_SCHEMA = {
    'type': 'object',
    'properties': {
        'operations': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'action': {
                        'type': 'string',
                        'enum': [
                            'ADD_GROUND_TO_EXISTING',
                            'MODIFY_OR_CONTEST_DISCOVERY',
                            'PROPOSE_NEW_DISCOVERY',
                            'INTEGRATE_SEPARATE_KNOWLEDGE',
                            'ABSTAIN',
                        ],
                    },
                    'target_discovery_id': {'type': ['string', 'null']},
                    'reason': {'type': 'string'},
                    'new_or_updated_discovery': {
                        'anyOf': [DISCOVERY_ITEM_SCHEMA, {'type': 'null'}],
                    },
                },
                'required': ['action', 'target_discovery_id', 'reason', 'new_or_updated_discovery'],
            },
        },
    },
    'required': ['operations'],
}

CONFRONTATION_SCHEMA = {
    'type': 'object',
    'properties': {
        'assessments': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'discovery_id': {'type': 'string'},
                    'already_explicit_in_single_record': {'type': 'boolean'},
                    'merely_summary_or_classification': {'type': 'boolean'},
                    'reveals_grounded_transversal_structure': {'type': 'boolean'},
                    'depends_on_integration': {'type': 'boolean'},
                    'records_sustain_interpretation': {'type': 'boolean'},
                    'contradicting_or_limiting_records': {'type': 'array', 'items': {'type': 'string'}},
                    'adds_comprehension_or_investigation': {'type': 'boolean'},
                    'verdict': {'type': 'string', 'enum': ['SUSTAINED_CANDIDATE', 'WEAK_OR_REDUNDANT', 'CONTESTED']},
                    'critique': {'type': 'string'},
                },
                'required': [
                    'discovery_id', 'already_explicit_in_single_record', 'merely_summary_or_classification',
                    'reveals_grounded_transversal_structure', 'depends_on_integration',
                    'records_sustain_interpretation', 'contradicting_or_limiting_records',
                    'adds_comprehension_or_investigation', 'verdict', 'critique',
                ],
            },
        },
    },
    'required': ['assessments'],
}


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
        traj = ctx.get('trajectory') or {}
        records.append({
            'id': ctx['id'],
            'version': ctx['version'],
            'created_at': ctx['created_at'],
            'title': ctx['title'],
            'kind': elab.get('kind'),
            'work_state': elab.get('work_state'),
            'claim': ctx['claim'],
            'why_matters': c.get('why_matters') or '',
            'scope': c.get('scope') or '',
            'limitations': ctx['limitations'],
            'genesis': ctx.get('genesis') or {},
            'provenance_status': (traj.get('provenance') or {}).get('origin_status'),
            'event_count': traj.get('event_count', 0),
        })
    records.sort(key=lambda r: (r['created_at'], r['title']))
    return records


def format_record(r):
    return (
        f"ID: {r['id']} (versão {r['version']}, tipo {r['kind']}, estado {r['work_state']}, eventos {r['event_count']})\n"
        f"Título: {r['title']}\n"
        f"Escopo: {r['scope']}\n"
        f"Formulação: {r['claim']}\n"
        f"Relevância: {r['why_matters']}\n"
        f"Limitações: {r['limitations']}"
    )


def embed_texts(texts):
    opener = build_opener(ProxyHandler({}))
    t0 = time.monotonic()
    req = Request(
        OLLAMA_EMBED_URL,
        data=json.dumps({'model': EMBED_MODEL, 'input': texts}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    with opener.open(req, timeout=120) as resp:
        res = json.load(resp)
    return res['embeddings'], round(time.monotonic() - t0, 3)


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return round(dot / (na * nb), 4)


def call_llm(system_msg, prompt, schema):
    opener = build_opener(ProxyHandler({}))
    payload = {
        'model': LLM_MODEL,
        'stream': False,
        'format': schema,
        'options': {'temperature': 0.1, 'num_ctx': 16384},
        'messages': [
            {'role': 'system', 'content': system_msg},
            {'role': 'user', 'content': prompt},
        ],
    }
    t0 = time.monotonic()
    req = Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    with opener.open(req, timeout=240) as resp:
        raw = json.load(resp)
    elapsed = round(time.monotonic() - t0, 2)
    text = raw['message']['content']
    return {
        'parsed': json.loads(text),
        'raw_response': text,
        'metrics': {
            'elapsed_s': elapsed,
            'prompt_eval_count': raw.get('prompt_eval_count'),
            'eval_count': raw.get('eval_count'),
        },
    }


def verify_discoveries(discoveries, records_by_id):
    verified = []
    for idx, d in enumerate(discoveries, 1):
        rec_checks = []
        for sr in d.get('supporting_records', []):
            rid = sr['record_id']
            rec = records_by_id.get(rid)
            corpus = ''
            if rec:
                corpus = '\n'.join(
                    str(x) for x in (rec['title'], rec['scope'], rec['claim'], rec['why_matters'], rec['limitations']) if x
                )
            ex_checks = [{'excerpt': ex, 'exact_match': bool(ex.strip()) and (ex.strip() in corpus)} for ex in sr.get('excerpts', [])]
            rec_checks.append({'record_id': rid, 'record_exists': rec is not None, 'excerpts': ex_checks})
        verified.append({
            'discovery_id': d.get('discovery_id') or f'D-{idx:02d}',
            **d,
            'verification': rec_checks,
        })
    return verified


def run_all():
    records = load_bbcore_records()
    rec_by_id = {r['id']: r for r in records}
    started_at = datetime.now(timezone.utc).isoformat(timespec='seconds')

    # 1. Representações vetoriais locais (integral + por campo)
    full_texts = [format_record(r) for r in records]
    claim_texts = [r['claim'] for r in records]
    why_texts = [r['why_matters'] or r['title'] for r in records]
    lim_texts = [r['limitations'] for r in records]

    emb_full, t_full = embed_texts(full_texts)
    emb_claim, t_claim = embed_texts(claim_texts)
    emb_why, t_why = embed_texts(why_texts)
    emb_lim, t_lim = embed_texts(lim_texts)

    def sim_matrix(vecs):
        pairs = []
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                pairs.append({
                    'a_id': records[i]['id'],
                    'a_title': records[i]['title'],
                    'b_id': records[j]['id'],
                    'b_title': records[j]['title'],
                    'cosine': cosine(vecs[i], vecs[j]),
                })
        pairs.sort(key=lambda x: x['cosine'], reverse=True)
        return pairs

    sim_full = sim_matrix(emb_full)
    sim_claim = sim_matrix(emb_claim)
    sim_why = sim_matrix(emb_why)
    sim_lim = sim_matrix(emb_lim)

    # 2. Estratégia A — Leitura integral do acervo
    prompt_a = (
        'Examine conjuntamente todos os 6 registros abaixo.\n'
        'Investigue o que pode ser descoberto pela integração desses conhecimentos (estruturas, processos, '
        'princípios, tensões, lacunas ou novas questões investigativas) que não está evidente na leitura isolada.\n\n'
        + '\n\n---\n\n'.join(format_record(r) for r in records)
    )
    res_a = call_llm(SYSTEM_DISCOVERY, prompt_a, DISCOVERY_LIST_SCHEMA)
    disc_a = verify_discoveries(res_a['parsed']['discoveries'], rec_by_id)

    # 3. Estratégia B — Exploração semântica (vizinhança mais próxima a partir do par mais similar)
    top_pair = sim_full[0]
    seed_ids = {top_pair['a_id'], top_pair['b_id']}
    # Adicionar o 3º registro mais próximo ao par semente
    for p in sim_full[1:]:
        if p['a_id'] in seed_ids or p['b_id'] in seed_ids:
            seed_ids.add(p['a_id'])
            seed_ids.add(p['b_id'])
            if len(seed_ids) >= 3:
                break
    subset_b = [r for r in records if r['id'] in seed_ids]
    prompt_b = (
        'Examine este subconjunto de registros semanticamente próximos (recuperados por similaridade vetorial).\n'
        'Investigue que abstrações, princípios ou tensões emergem especificamente dessa vizinhança semântica.\n\n'
        + '\n\n---\n\n'.join(format_record(r) for r in subset_b)
    )
    res_b = call_llm(SYSTEM_DISCOVERY, prompt_b, DISCOVERY_LIST_SCHEMA)
    disc_b = verify_discoveries(res_b['parsed']['discoveries'], rec_by_id)

    # 4. Estratégia C — Exploração transversal (registros semanticamente mais distantes)
    distant_pair = sim_full[-1]
    dist_ids = {distant_pair['a_id'], distant_pair['b_id']}
    for p in reversed(sim_full[:-1]):
        if p['a_id'] in dist_ids or p['b_id'] in dist_ids:
            dist_ids.add(p['a_id'])
            dist_ids.add(p['b_id'])
            if len(dist_ids) >= 3:
                break
    subset_c = [r for r in records if r['id'] in dist_ids]
    prompt_c = (
        'Examine conjuntamente este subconjunto de registros semanticamente DISTANTES entre si.\n'
        'Investigue se a distância temática revela complementaridades, analogias estruturais, '
        'processos comuns ou tensões relevantes que não aparecem na proximidade imediata.\n\n'
        + '\n\n---\n\n'.join(format_record(r) for r in subset_c)
    )
    res_c = call_llm(SYSTEM_DISCOVERY, prompt_c, DISCOVERY_LIST_SCHEMA)
    disc_c = verify_discoveries(res_c['parsed']['discoveries'], rec_by_id)

    # 5. Estratégia D — Incorporação incremental com estado determinístico fora da LLM
    disc_state = []
    steps_d = []
    next_id = 1
    for step_idx, r in enumerate(records, 1):
        prompt_d = (
            f'Etapa incremental {step_idx}/{len(records)}.\n'
            'Você recebe o estado atual das descobertas acumuladas (gerenciado externamente) e um novo registro incorporado.\n'
            'Decida mediante operações atômicas se o novo registro:\n'
            '- ADD_GROUND_TO_EXISTING: acrescenta fundamento a uma descoberta existente;\n'
            '- MODIFY_OR_CONTEST_DISCOVERY: modifica ou contesta uma descoberta existente;\n'
            '- PROPOSE_NEW_DISCOVERY: revela nova estrutura/abstração;\n'
            '- INTEGRATE_SEPARATE_KNOWLEDGE: integra conhecimentos antes separados;\n'
            '- ABSTAIN: não oferece contribuição identificável às abstrações.\n\n'
            f'DESCOBERTAS ACUMULADAS:\n{json.dumps(disc_state, ensure_ascii=False, indent=2)}\n\n'
            f'NOVO REGISTRO:\n{format_record(r)}'
        )
        res_d = call_llm(SYSTEM_DISCOVERY, prompt_d, INCREMENTAL_OPS_SCHEMA)
        ops = res_d['parsed']['operations']
        for op in ops:
            act = op['action']
            if act in ('PROPOSE_NEW_DISCOVERY', 'INTEGRATE_SEPARATE_KNOWLEDGE') and op.get('new_or_updated_discovery'):
                item = {'discovery_id': f'INC-{next_id:02d}', **op['new_or_updated_discovery']}
                next_id += 1
                disc_state.append(item)
            elif act == 'MODIFY_OR_CONTEST_DISCOVERY' and op.get('target_discovery_id') and op.get('new_or_updated_discovery'):
                for k, existing in enumerate(disc_state):
                    if existing['discovery_id'] == op['target_discovery_id']:
                        disc_state[k] = {'discovery_id': existing['discovery_id'], **op['new_or_updated_discovery'], 'revised_at_step': step_idx}
            elif act == 'ADD_GROUND_TO_EXISTING' and op.get('target_discovery_id') and op.get('new_or_updated_discovery'):
                for existing in disc_state:
                    if existing['discovery_id'] == op['target_discovery_id']:
                        existing.setdefault('added_grounds', []).append({'step': step_idx, 'record_id': r['id'], 'reason': op['reason']})
        steps_d.append({'step': step_idx, 'record_id': r['id'], 'title': r['title'], **res_d})

    disc_d_verified = verify_discoveries(disc_state, rec_by_id)

    # 6. Estratégia E — Confrontação crítica independente das descobertas de A e D
    all_to_confront = [
        {'discovery_id': d['discovery_id'], 'title': d['title'], 'formulation': d['formulation'],
         'supporting_record_ids': [s['record_id'] for s in d['supporting_records']]}
        for d in (disc_a + disc_d_verified)
    ]
    prompt_e = (
        'Examine criticamente cada descoberta candidata abaixo contra os registros originais do BB-CORE.\n'
        'Verifique os 7 critérios:\n'
        '1) Já está explicitamente presente em um único registro?\n'
        '2) É apenas classificação, resumo ou reformulação?\n'
        '3) Revela estrutura transversal fundamentada?\n'
        '4) Depende efetivamente da integração dos registros?\n'
        '5) Os registros sustentam a interpretação?\n'
        '6) Há registros que contradizem ou limitam?\n'
        '7) Acrescenta possibilidade de compreensão ou investigação?\n\n'
        f'REGISTROS ORIGINAIS:\n' + '\n\n---\n\n'.join(format_record(r) for r in records) + '\n\n'
        f'DESCOBERTAS CANDIDATAS:\n{json.dumps(all_to_confront, ensure_ascii=False, indent=2)}'
    )
    system_critique = (
        'Você é um revisor epistemológico rigoroso. Não elogie descobertas fracas ou redundantes. '
        'Classifique como WEAK_OR_REDUNDANT se a descoberta apenas resumir ou repetir um único registro. '
        'Responda em português e estritamente no JSON solicitado.'
    )
    res_e = call_llm(system_critique, prompt_e, CONFRONTATION_SCHEMA)

    ollama_ps = subprocess.run(['ollama', 'ps'], capture_output=True, text=True, check=False).stdout.strip()
    output = {
        'instruction': 'BB-CORE-EXP-003 v0.2.0',
        'executed_at': started_at,
        'llm_model': LLM_MODEL,
        'embed_model': EMBED_MODEL,
        'ollama_ps': ollama_ps,
        'records': [{'id': r['id'], 'version': r['version'], 'title': r['title']} for r in records],
        'embeddings': {
            'timings_s': {'full': t_full, 'claim': t_claim, 'why_matters': t_why, 'limitations': t_lim},
            'similarity_full': sim_full,
            'similarity_claim': sim_claim,
            'similarity_why_matters': sim_why,
            'similarity_limitations': sim_lim,
        },
        'strategy_a_integral': {'discoveries': disc_a, 'abstentions': res_a['parsed']['abstentions'], 'metrics': res_a['metrics'], 'raw_response': res_a['raw_response']},
        'strategy_b_semantic_neighborhood': {'subset_ids': [r['id'] for r in subset_b], 'discoveries': disc_b, 'abstentions': res_b['parsed']['abstentions'], 'metrics': res_b['metrics']},
        'strategy_c_transversal_distant': {'subset_ids': [r['id'] for r in subset_c], 'discoveries': disc_c, 'abstentions': res_c['parsed']['abstentions'], 'metrics': res_c['metrics']},
        'strategy_d_incremental': {'final_discoveries': disc_d_verified, 'steps': steps_d},
        'strategy_e_confrontation': res_e,
    }
    out_file = OUT_DIR / 'results.json'
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SAVED:', out_file)


if __name__ == '__main__':
    run_all()
