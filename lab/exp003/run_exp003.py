"""BB-CORE-EXP-003 v0.2.0 — Descoberta semântica e abstração intelectual.

Experimento isolado sobre os 6 registros reais (002..007) do BB-CORE:
1. Representações vetoriais locais (qwen3-embedding:4b) integral e por campos.
2. Estratégias A (leitura integral), B (vizinhança semântica), C (transversal distante),
   D (incorporação incremental com estado determinístico fora da LLM),
   E (reexame coletivo e confrontação crítica independente segundo os 7 critérios).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

ENGINE_VERSION = 'BB-CORE-EXP-004/0.1.0'
LLM_MODEL = 'qwen2.5:14b'
EMBED_MODEL = 'qwen3-embedding:4b'
OLLAMA_CHAT_URL = 'http://127.0.0.1:11434/api/chat'
OLLAMA_EMBED_URL = 'http://127.0.0.1:11434/api/embed'
OLLAMA_SHOW_URL = 'http://127.0.0.1:11434/api/show'
BBCORE_URL = 'http://127.0.0.1:8789'
OUT_DIR = Path(__file__).resolve().parent

DEFAULT_CONFIG = {
    'profile': 'reference',
    'investigator_model': LLM_MODEL,
    'embed_model': EMBED_MODEL,
    'confrontation_model': LLM_MODEL,
    'reference_temperature': 0.0,
    'exploratory_temperature': 0.2,
    'seed': 42,
    'context_window': 16384,
    'exploratory_repetitions': 3,
    'enabled_strategies': ['A', 'B', 'C', 'D', 'E'],
    'confrontation_temperature': 0.0,
    'confrontation_seed': 42,
}

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

    corpus_resp = get_json('/api/analytics/corpus')
    records = corpus_resp['records']
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


def sha256_json(obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def query_model_digest(model_name):
    opener = build_opener(ProxyHandler({}))
    try:
        req = Request(
            OLLAMA_SHOW_URL,
            data=json.dumps({'model': model_name}).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
        with opener.open(req, timeout=5) as resp:
            info = json.load(resp)
        details = info.get('details') or {}
        return {
            'name': model_name,
            'digest': info.get('digest') or details.get('digest'),
            'family': details.get('family'),
            'parameter_size': details.get('parameter_size'),
            'quantization_level': details.get('quantization_level'),
        }
    except Exception:
        return {'name': model_name, 'digest': None}


def embed_texts(texts, *, model=EMBED_MODEL):
    opener = build_opener(ProxyHandler({}))
    t0 = time.monotonic()
    req = Request(
        OLLAMA_EMBED_URL,
        data=json.dumps({'model': model, 'input': texts}).encode('utf-8'),
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


def call_llm(system_msg, prompt, schema, *, model=LLM_MODEL, temperature=0.0, seed=42, num_ctx=16384):
    opener = build_opener(ProxyHandler({}))
    options = {'temperature': float(temperature), 'num_ctx': int(num_ctx)}
    if seed is not None:
        options['seed'] = int(seed)
    payload = {
        'model': model,
        'stream': False,
        'format': schema,
        'options': options,
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


def _atomic_write_json(target: Path, payload: dict) -> None:
    tmp = target.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(target)


def run_all(config=None, replay_corpus_path=None, run_id=None, profile_override=None, seed_override=None, config_version=None, batch_id=None):
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    if profile_override:
        cfg['profile'] = profile_override
    if seed_override is not None:
        cfg['seed'] = int(seed_override)

    profile = cfg['profile']
    inv_model = cfg['investigator_model']
    emb_model = cfg['embed_model']
    conf_model = cfg['confrontation_model']
    num_ctx = int(cfg['context_window'])
    enabled = set(cfg.get('enabled_strategies') or ['A', 'B', 'C', 'D', 'E'])
    gen_temp = float(cfg['exploratory_temperature'] if profile == 'exploration' else cfg['reference_temperature'])
    gen_seed = int(cfg['seed'])
    conf_temp = float(cfg['confrontation_temperature'])
    conf_seed = int(cfg['confrontation_seed'])

    started_dt = datetime.now(timezone.utc)
    started_at = started_dt.isoformat(timespec='seconds')
    rid = run_id or f"run-{started_dt.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    run_dir = OUT_DIR / 'runs' / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    # Resolver execução de origem no perfil Verificação antes de congelar o corpus
    source_run_id = None
    prev_results_path = None
    source_corpus_path = None
    if profile == 'verification':
        prev_results_path = OUT_DIR / 'results.json'
        latest_ptr = OUT_DIR / 'latest.json'
        if latest_ptr.is_file():
            ptr = json.loads(latest_ptr.read_text(encoding='utf-8'))
            if ptr.get('run_id'):
                cand_res = OUT_DIR / 'runs' / ptr['run_id'] / 'results.json'
                cand_corp = OUT_DIR / 'runs' / ptr['run_id'] / 'corpus.json'
                if cand_res.is_file():
                    prev_results_path = cand_res
                    source_run_id = ptr['run_id']
                if cand_corp.is_file():
                    source_corpus_path = cand_corp

    # 0. Congelamento do universo investigativo (corpus.json)
    effective_replay = replay_corpus_path or (str(source_corpus_path) if source_corpus_path else None)
    if effective_replay:
        corpus_payload = json.loads(Path(effective_replay).read_text(encoding='utf-8'))
        records = corpus_payload['records']
    else:
        records = load_bbcore_records()

    formulation_basis = 'ORIGINAL_CANONICAL_RECORDS'
    rec_by_id = {r['id']: r for r in records}
    formatted_texts = {r['id']: format_record(r) for r in records}
    record_order = [r['id'] for r in records]
    corpus_sha256 = sha256_json(records)

    # 1. Representações vetoriais locais (integral + por campo)
    full_texts = [formatted_texts[r['id']] for r in records]
    claim_texts = [r['claim'] for r in records]
    why_texts = [r['why_matters'] or r['title'] for r in records]
    lim_texts = [r['limitations'] for r in records]

    emb_full, t_full = embed_texts(full_texts, model=emb_model)
    emb_claim, t_claim = embed_texts(claim_texts, model=emb_model)
    emb_why, t_why = embed_texts(why_texts, model=emb_model)
    emb_lim, t_lim = embed_texts(lim_texts, model=emb_model)

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

    # Seleção determinística dos subconjuntos B e C (para preservar no corpus.json)
    top_pair = sim_full[0]
    seed_ids = {top_pair['a_id'], top_pair['b_id']}
    for p in sim_full[1:]:
        if p['a_id'] in seed_ids or p['b_id'] in seed_ids:
            seed_ids.add(p['a_id'])
            seed_ids.add(p['b_id'])
            if len(seed_ids) >= 3:
                break
    subset_b = [r for r in records if r['id'] in seed_ids]

    distant_pair = sim_full[-1]
    dist_ids = {distant_pair['a_id'], distant_pair['b_id']}
    for p in reversed(sim_full[:-1]):
        if p['a_id'] in dist_ids or p['b_id'] in dist_ids:
            dist_ids.add(p['a_id'])
            dist_ids.add(p['b_id'])
            if len(dist_ids) >= 3:
                break
    subset_c = [r for r in records if r['id'] in dist_ids]

    # Salvar fotografia congelada do corpus imediatamente
    _atomic_write_json(run_dir / 'corpus.json', {
        'run_id': rid,
        'batch_id': batch_id,
        'frozen_at': started_at,
        'formulation_basis': formulation_basis,
        'corpus_sha256': corpus_sha256,
        'record_order': record_order,
        'records': records,
        'formatted_texts': formatted_texts,
        'selected_contexts': {
            'strategy_b_subset_ids': [r['id'] for r in subset_b],
            'strategy_c_subset_ids': [r['id'] for r in subset_c],
        },
        'replayed_from': effective_replay,
        'source_run_id': source_run_id,
    })

    if profile == 'verification':
        # Perfil Verificação: reutiliza descobertas e corpus da execução de origem e submete apenas à nova confrontação
        prev_data = json.loads(prev_results_path.read_text(encoding='utf-8'))
        if not source_run_id:
            source_run_id = prev_data.get('run_id')
        disc_a = verify_discoveries((prev_data.get('strategy_a_integral') or {}).get('discoveries', []), rec_by_id)
        disc_b = verify_discoveries((prev_data.get('strategy_b_semantic_neighborhood') or {}).get('discoveries', []), rec_by_id)
        disc_c = verify_discoveries((prev_data.get('strategy_c_transversal_distant') or {}).get('discoveries', []), rec_by_id)
        disc_d_verified = verify_discoveries((prev_data.get('strategy_d_incremental') or {}).get('final_discoveries', []), rec_by_id)
        res_a = {'parsed': {'abstentions': (prev_data.get('strategy_a_integral') or {}).get('abstentions', [])}, 'metrics': {}, 'raw_response': None}
        res_b = {'parsed': {'abstentions': (prev_data.get('strategy_b_semantic_neighborhood') or {}).get('abstentions', [])}, 'metrics': {}}
        res_c = {'parsed': {'abstentions': (prev_data.get('strategy_c_transversal_distant') or {}).get('abstentions', [])}, 'metrics': {}}
        steps_d = (prev_data.get('strategy_d_incremental') or {}).get('steps', [])
        strategies_executed = ['E']
    else:
        strategies_executed = []
        # 2. Estratégia A — Leitura integral do acervo
        if 'A' in enabled:
            prompt_a = (
                f'Examine conjuntamente todos os {len(records)} registros abaixo.\n'
                'Investigue o que pode ser descoberto pela integração desses conhecimentos (estruturas, processos, '
                'princípios, tensões, lacunas ou novas questões investigativas) que não está evidente na leitura isolada.\n\n'
                + '\n\n---\n\n'.join(formatted_texts[r['id']] for r in records)
            )
            res_a = call_llm(SYSTEM_DISCOVERY, prompt_a, DISCOVERY_LIST_SCHEMA, model=inv_model, temperature=gen_temp, seed=gen_seed, num_ctx=num_ctx)
            disc_a = verify_discoveries(res_a['parsed']['discoveries'], rec_by_id)
            strategies_executed.append('A')
        else:
            res_a = {'parsed': {'abstentions': []}, 'metrics': {}, 'raw_response': None}
            disc_a = []

        # 3. Estratégia B — Exploração semântica (vizinhança mais próxima)
        if 'B' in enabled:
            prompt_b = (
                'Examine este subconjunto de registros semanticamente próximos (recuperados por similaridade vetorial).\n'
                'Investigue que abstrações, princípios ou tensões emergem especificamente dessa vizinhança semântica.\n\n'
                + '\n\n---\n\n'.join(formatted_texts[r['id']] for r in subset_b)
            )
            res_b = call_llm(SYSTEM_DISCOVERY, prompt_b, DISCOVERY_LIST_SCHEMA, model=inv_model, temperature=gen_temp, seed=gen_seed, num_ctx=num_ctx)
            disc_b = verify_discoveries(res_b['parsed']['discoveries'], rec_by_id)
            strategies_executed.append('B')
        else:
            res_b = {'parsed': {'abstentions': []}, 'metrics': {}}
            disc_b = []

        # 4. Estratégia C — Exploração transversal (registros semanticamente mais distantes)
        if 'C' in enabled:
            prompt_c = (
                'Examine conjuntamente este subconjunto de registros semanticamente DISTANTES entre si.\n'
                'Investigue se a distância temática revela complementaridades, analogias estruturais, '
                'processos comuns ou tensões relevantes que não aparecem na proximidade imediata.\n\n'
                + '\n\n---\n\n'.join(formatted_texts[r['id']] for r in subset_c)
            )
            res_c = call_llm(SYSTEM_DISCOVERY, prompt_c, DISCOVERY_LIST_SCHEMA, model=inv_model, temperature=gen_temp, seed=gen_seed, num_ctx=num_ctx)
            disc_c = verify_discoveries(res_c['parsed']['discoveries'], rec_by_id)
            strategies_executed.append('C')
        else:
            res_c = {'parsed': {'abstentions': []}, 'metrics': {}}
            disc_c = []

        # 5. Estratégia D — Incorporação incremental com estado determinístico fora da LLM
        disc_state = []
        steps_d = []
        next_id = 1
        if 'D' in enabled:
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
                    f'NOVO REGISTRO:\n{formatted_texts[r["id"]]}'
                )
                res_d = call_llm(SYSTEM_DISCOVERY, prompt_d, INCREMENTAL_OPS_SCHEMA, model=inv_model, temperature=gen_temp, seed=gen_seed, num_ctx=num_ctx)
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
            strategies_executed.append('D')
        disc_d_verified = verify_discoveries(disc_state, rec_by_id)

    # 6. Estratégia E — Confrontação crítica independente das descobertas de A e D (B e C seguem em confront_all.py)
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
        f'REGISTROS ORIGINAIS:\n' + '\n\n---\n\n'.join(formatted_texts[r['id']] for r in records) + '\n\n'
        f'DESCOBERTAS CANDIDATAS:\n{json.dumps(all_to_confront, ensure_ascii=False, indent=2)}'
    )
    system_critique = (
        'Você é um revisor epistemológico rigoroso. Não elogie descobertas fracas ou redundantes. '
        'Classifique como WEAK_OR_REDUNDANT se a descoberta apenas resumir ou repetir um único registro. '
        'Responda em português e estritamente no JSON solicitado.'
    )
    if 'E' in enabled and all_to_confront:
        res_e = call_llm(system_critique, prompt_e, CONFRONTATION_SCHEMA, model=conf_model, temperature=conf_temp, seed=conf_seed, num_ctx=num_ctx)
        if 'E' not in strategies_executed:
            strategies_executed.append('E')
    else:
        res_e = {'parsed': {'assessments': []}, 'metrics': {}, 'raw_response': None}

    ollama_ps = subprocess.run(['ollama', 'ps'], capture_output=True, text=True, check=False).stdout.strip()
    output = {
        'instruction': 'BB-CORE-EXP-004 v0.1.0',
        'run_id': rid,
        'batch_id': batch_id,
        'source_run_id': source_run_id,
        'profile': profile,
        'config_version': config_version,
        'config_used': cfg,
        'formulation_basis': formulation_basis,
        'corpus_sha256': corpus_sha256,
        'executed_at': started_at,
        'llm_model': inv_model,
        'embed_model': emb_model,
        'confrontation_model': conf_model,
        'ollama_ps': ollama_ps,
        'records': [{'id': r['id'], 'version': r['version'], 'title': r['title']} for r in records],
        'embeddings': {
            'timings_s': {'full': t_full, 'claim': t_claim, 'why_matters': t_why, 'limitations': t_lim},
            'similarity_full': sim_full,
            'similarity_claim': sim_claim,
            'similarity_why_matters': sim_why,
            'similarity_limitations': sim_lim,
        },
        'strategy_a_integral': {'discoveries': disc_a, 'abstentions': res_a['parsed']['abstentions'], 'metrics': res_a['metrics'], 'raw_response': res_a.get('raw_response')},
        'strategy_b_semantic_neighborhood': {'subset_ids': [r['id'] for r in subset_b], 'discoveries': disc_b, 'abstentions': res_b['parsed']['abstentions'], 'metrics': res_b['metrics']},
        'strategy_c_transversal_distant': {'subset_ids': [r['id'] for r in subset_c], 'discoveries': disc_c, 'abstentions': res_c['parsed']['abstentions'], 'metrics': res_c['metrics']},
        'strategy_d_incremental': {'final_discoveries': disc_d_verified, 'steps': steps_d},
        'strategy_e_confrontation': res_e,
    }
    results_file = run_dir / 'results.json'
    _atomic_write_json(results_file, output)

    limitations = []
    if inv_model == conf_model:
        limitations.append(
            f'Mesmo modelo ({inv_model}) empregado na descoberta e na confrontação crítica; '
            'vieses compartilhados não são eliminados apenas por prompts distintos.'
        )

    manifest = {
        'run_id': rid,
        'batch_id': batch_id,
        'engine_version': ENGINE_VERSION,
        'status': 'pending_confrontation',
        'started_at': started_at,
        'finished_at': None,
        'profile': profile,
        'config_version': config_version,
        'config_used': cfg,
        'formulation_basis': formulation_basis,
        'verification_source': (
            {
                'source_run_id': source_run_id,
                'source_corpus_path': str(source_corpus_path) if source_corpus_path else None,
                'corpus_reused_from_source': bool(source_corpus_path),
            }
            if profile == 'verification'
            else None
        ),
        'effective_generation': {'model': inv_model, 'temperature': gen_temp, 'seed': gen_seed, 'num_ctx': num_ctx},
        'effective_confrontation': {'model': conf_model, 'temperature': conf_temp, 'seed': conf_seed, 'num_ctx': num_ctx},
        'models': {
            'investigator': query_model_digest(inv_model),
            'embeddings': query_model_digest(emb_model),
            'confrontation': query_model_digest(conf_model),
        },
        'prompts_sha256': sha256_json({'discovery': SYSTEM_DISCOVERY, 'critique': system_critique}),
        'schemas_sha256': sha256_json({
            'discovery': DISCOVERY_LIST_SCHEMA,
            'incremental': INCREMENTAL_OPS_SCHEMA,
            'confrontation': CONFRONTATION_SCHEMA,
        }),
        'corpus_sha256': corpus_sha256,
        'record_count': len(records),
        'strategies_executed': strategies_executed,
        'methodological_limitations': limitations,
        'timings_s': {
            'embeddings': {'full': t_full, 'claim': t_claim, 'why_matters': t_why, 'limitations': t_lim},
            'strategy_a': (res_a.get('metrics') or {}).get('elapsed_s'),
            'strategy_b': (res_b.get('metrics') or {}).get('elapsed_s'),
            'strategy_c': (res_c.get('metrics') or {}).get('elapsed_s'),
            'strategy_e_initial': (res_e.get('metrics') or {}).get('elapsed_s'),
        },
    }
    _atomic_write_json(run_dir / 'manifest.json', manifest)
    (OUT_DIR / '.pending_run').write_text(rid, encoding='utf-8')
    print('SAVED_RUN:', run_dir)
    return run_dir


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BB-CORE-EXP-004 runner')
    parser.add_argument('--config-json', type=str, default=None)
    parser.add_argument('--replay-corpus', type=str, default=None)
    parser.add_argument('--run-id', type=str, default=None)
    parser.add_argument('--profile', type=str, default=None)
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--config-version', type=int, default=None)
    parser.add_argument('--batch-id', type=str, default=None)
    args = parser.parse_args()
    loaded_cfg = json.loads(Path(args.config_json).read_text(encoding='utf-8')) if args.config_json else None
    run_all(
        config=loaded_cfg,
        replay_corpus_path=args.replay_corpus,
        run_id=args.run_id,
        profile_override=args.profile,
        seed_override=args.seed,
        config_version=args.config_version,
        batch_id=args.batch_id,
    )
