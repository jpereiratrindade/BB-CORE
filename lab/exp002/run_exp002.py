"""BB-CORE-EXP-002 v0.1.0 — Análise experimental de conexões intelectuais par-a-par com LLM local.

Examina os 15 pares distintos dos 6 registros reais (002..007) do BB-CORE em ordem direta
(A, B) e inversa (B, A), sem taxonomias ou pontuações predefinidas, validando deterministicamente
a existência dos registros e a correspondência literal dos trechos citados.
"""
from __future__ import annotations

import itertools
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

SYSTEM_PROMPT = (
    'Você é um analista conceitual operando sobre registros intelectuais do sistema BB-CORE.\n'
    'REGRAS EPISTEMOLÓGICAS ESTRITAS:\n'
    '1. Você recebe dois registros intelectuais (Registro A e Registro B).\n'
    '2. Examine se existe uma conexão intelectualmente relevante entre eles.\n'
    '3. Não presuma categorias, tipologias obrigatórias, taxonomias ou pontuações numéricas.\n'
    '4. NÃO confunda compartilhamento superficial de palavras, fontes ou temas genéricos com '
    'fundamentação suficiente de uma conexão intelectual.\n'
    '5. Se houver conexão relevante, descreva livremente sua natureza, apresente trechos literais '
    'exatos de AMBOS os registros (copiados exatamente do texto fornecido), justifique sua relevância '
    'intelectual e explicite as limitações.\n'
    '6. Se não houver fundamentação suficiente, abstenha-se explicitamente (`connection_proposed: false`) '
    'e explique o motivo da abstenção.\n'
    'Responda exclusivamente em português e estritamente no formato JSON solicitado.'
)

PAIR_SCHEMA = {
    'type': 'object',
    'properties': {
        'connection_proposed': {'type': 'boolean'},
        'connection_nature': {'type': ['string', 'null']},
        'excerpts_a': {'type': 'array', 'items': {'type': 'string'}},
        'excerpts_b': {'type': 'array', 'items': {'type': 'string'}},
        'justification': {'type': 'string'},
        'limitations': {'type': 'array', 'items': {'type': 'string'}},
        'abstention_reason': {'type': ['string', 'null']},
    },
    'required': [
        'connection_proposed', 'connection_nature', 'excerpts_a',
        'excerpts_b', 'justification', 'limitations', 'abstention_reason',
    ],
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
        })
    records.sort(key=lambda r: (r['created_at'], r['title']))
    return records


def format_record(label, r):
    return (
        f"[{label}]\n"
        f"ID: {r['id']} (versão {r['version']}, tipo {r['kind']}, estado {r['work_state']})\n"
        f"Título: {r['title']}\n"
        f"Escopo declarado: {r['scope']}\n"
        f"Formulação: {r['claim']}\n"
        f"Relevância: {r['why_matters']}\n"
        f"Limitações: {r['limitations']}"
    )


def verify_excerpts(excerpts, record):
    corpus = '\n'.join(
        str(x) for x in (
            record.get('title'), record.get('scope'),
            record.get('claim'), record.get('why_matters'), record.get('limitations'),
        ) if x
    )
    checks = []
    for ex in excerpts:
        cleaned = ex.strip()
        exact = bool(cleaned) and (cleaned in corpus)
        checks.append({'excerpt': ex, 'exact_match': exact})
    return checks


def call_pair(rec_a, rec_b):
    opener = build_opener(ProxyHandler({}))
    prompt = (
        'Examine se existe uma conexão intelectualmente relevante entre os dois registros abaixo.\n\n'
        + format_record('Registro A', rec_a)
        + '\n\n---\n\n'
        + format_record('Registro B', rec_b)
    )
    payload = {
        'model': MODEL,
        'stream': False,
        'format': PAIR_SCHEMA,
        'options': {'temperature': 0.1, 'num_ctx': 16384},
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt},
        ],
    }
    t0 = time.monotonic()
    req = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    with opener.open(req, timeout=180) as resp:
        raw = json.load(resp)
    elapsed = round(time.monotonic() - t0, 2)
    raw_text = raw['message']['content']
    parsed = json.loads(raw_text)
    return {
        'parsed': parsed,
        'raw_response': raw_text,
        'excerpts_a_check': verify_excerpts(parsed.get('excerpts_a', []), rec_a),
        'excerpts_b_check': verify_excerpts(parsed.get('excerpts_b', []), rec_b),
        'metrics': {
            'elapsed_s': elapsed,
            'prompt_eval_count': raw.get('prompt_eval_count'),
            'eval_count': raw.get('eval_count'),
            'total_duration_ns': raw.get('total_duration'),
        },
    }


def run_all():
    records = load_bbcore_records()
    started_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    pairs = list(itertools.combinations(records, 2))
    assert len(pairs) == 15, len(pairs)

    pair_results = []
    for idx, (rec_a, rec_b) in enumerate(pairs, 1):
        fwd = call_pair(rec_a, rec_b)
        rev = call_pair(rec_b, rec_a)
        fwd_prop = fwd['parsed']['connection_proposed']
        rev_prop = rev['parsed']['connection_proposed']
        if fwd_prop and rev_prop:
            stability = 'CONCORDANT_CONNECTED'
        elif not fwd_prop and not rev_prop:
            stability = 'CONCORDANT_ABSTAINED'
        else:
            stability = 'DIVERGENT_ORDER_DEPENDENT'

        pair_results.append({
            'pair_index': idx,
            'record_a': {'id': rec_a['id'], 'version': rec_a['version'], 'title': rec_a['title']},
            'record_b': {'id': rec_b['id'], 'version': rec_b['version'], 'title': rec_b['title']},
            'stability': stability,
            'forward_ab': fwd,
            'reverse_ba': rev,
        })
        print(f'Pair {idx:02d}/15: {stability} | {rec_a["title"][:28]} <-> {rec_b["title"][:28]}', flush=True)

    ollama_ps = subprocess.run(['ollama', 'ps'], capture_output=True, text=True, check=False).stdout.strip()
    output = {
        'instruction': 'BB-CORE-EXP-002 v0.1.0',
        'executed_at': started_at,
        'model': MODEL,
        'parameters': {'temperature': 0.1, 'num_ctx': 16384},
        'ollama_ps': ollama_ps,
        'records': [{'id': r['id'], 'version': r['version'], 'title': r['title']} for r in records],
        'pairs': pair_results,
    }
    out_file = OUT_DIR / 'results.json'
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SAVED:', out_file)


if __name__ == '__main__':
    run_all()
