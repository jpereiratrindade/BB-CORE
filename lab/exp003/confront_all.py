"""Pós-processamento do BB-CORE-EXP-004: confrontação uniforme (A–D), verificação
determinística dos fundamentos, distinção em três dimensões, manifesto e atualização
atômica da referência para a última execução bem-sucedida.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from run_exp003 import (
    CONFRONTATION_SCHEMA,
    DEFAULT_CONFIG,
    OUT_DIR,
    _atomic_write_json,
    call_llm,
    format_record,
    load_bbcore_records,
)


def deterministic_verify(item: dict, rec_by_id: dict, assessment: dict | None) -> dict:
    """Verificação determinística dos fundamentos e coerência critérios/veredito."""
    supporting = item.get('supporting_records') or []
    rec_ids = [s.get('record_id') for s in supporting if s.get('record_id')]
    missing_ids = [rid for rid in rec_ids if rid not in rec_by_id]

    excerpts_total = 0
    excerpts_exact = 0
    for sr in supporting:
        rid = sr.get('record_id')
        rec = rec_by_id.get(rid)
        corpus = ''
        if rec:
            corpus = '\n'.join(
                str(x) for x in (rec.get('title'), rec.get('scope'), rec.get('claim'), rec.get('why_matters'), rec.get('limitations')) if x
            )
        for ex in sr.get('excerpts') or []:
            excerpts_total += 1
            if ex and ex.strip() and ex.strip() in corpus:
                excerpts_exact += 1

    inconsistencies: list[str] = []
    if not supporting:
        inconsistencies.append('Nenhum registro fundamentador declarado.')
    if missing_ids:
        inconsistencies.append(f'Identificadores ausentes no corpus: {", ".join(missing_ids)}.')
    if excerpts_total == 0:
        inconsistencies.append('Nenhum trecho literal informado para fundamentação.')
    elif excerpts_exact < excerpts_total:
        inconsistencies.append(f'Trechos literais não verificados exatamente: {excerpts_total - excerpts_exact}/{excerpts_total}.')

    criteria_coherent = True
    if assessment is None:
        inconsistencies.append('Avaliação crítica automatizada ausente para este candidato.')
    else:
        verdict = assessment.get('verdict')
        if verdict == 'SUSTAINED_CANDIDATE':
            if len(set(rec_ids)) < 2:
                criteria_coherent = False
                inconsistencies.append('Veredito SUSTAINED_CANDIDATE com menos de 2 registros distintos.')
            if assessment.get('already_explicit_in_single_record'):
                criteria_coherent = False
                inconsistencies.append('Incoerência: veredito SUSTAINED_CANDIDATE, mas marcada como explícita em único registro.')
            if assessment.get('merely_summary_or_classification'):
                criteria_coherent = False
                inconsistencies.append('Incoerência: veredito SUSTAINED_CANDIDATE, mas marcada como mero resumo/classificação.')
            if not assessment.get('depends_on_integration'):
                criteria_coherent = False
                inconsistencies.append('Incoerência: veredito SUSTAINED_CANDIDATE sem dependência de integração.')
            if not assessment.get('records_sustain_interpretation'):
                criteria_coherent = False
                inconsistencies.append('Incoerência: veredito SUSTAINED_CANDIDATE sem sustentação pelos registros.')
            if not assessment.get('adds_comprehension_or_investigation'):
                criteria_coherent = False
                inconsistencies.append('Incoerência: veredito SUSTAINED_CANDIDATE sem acréscimo de compreensão/investigação.')

    raw_verdict = assessment.get('verdict') if assessment else 'NOT_EXAMINED'
    if raw_verdict == 'SUSTAINED_CANDIDATE' and inconsistencies:
        effective_status = 'CONTESTED'
    else:
        effective_status = raw_verdict

    return {
        'supporting_records_present': bool(supporting) and not missing_ids,
        'distinct_supporting_records': len(set(rec_ids)),
        'all_record_ids_valid': not missing_ids,
        'missing_record_ids': missing_ids,
        'excerpts_total': excerpts_total,
        'excerpts_exact_match': excerpts_exact,
        'criteria_verdict_coherent': criteria_coherent,
        'inconsistencies': inconsistencies,
        'effective_status': effective_status,
    }


def _resolve_run_dir(explicit_dir: str | None) -> Path:
    if explicit_dir:
        return Path(explicit_dir)
    pending = OUT_DIR / '.pending_run'
    if pending.is_file():
        rid = pending.read_text(encoding='utf-8').strip()
        cand = OUT_DIR / 'runs' / rid
        if cand.is_dir():
            return cand
    return OUT_DIR


def main(run_dir_arg: str | None = None):
    run_dir = _resolve_run_dir(run_dir_arg)
    path = run_dir / 'results.json'
    data = json.loads(path.read_text(encoding='utf-8'))

    corpus_file = run_dir / 'corpus.json'
    if corpus_file.is_file():
        corpus_data = json.loads(corpus_file.read_text(encoding='utf-8'))
        records = corpus_data['records']
    else:
        records = load_bbcore_records()
    rec_by_id = {r['id']: r for r in records}

    cfg = {**DEFAULT_CONFIG, **(data.get('config_used') or {})}
    conf_model = cfg['confrontation_model']
    conf_temp = float(cfg['confrontation_temperature'])
    conf_seed = int(cfg['confrontation_seed'])
    num_ctx = int(cfg['context_window'])
    same_model_limitation = (cfg['investigator_model'] == conf_model)

    exec_tag = data.get('run_id') or data['executed_at']

    # 1. Garantir IDs únicos considerando execução e estratégia
    strat_groups = [
        ('A', (data.get('strategy_a_integral') or {}).get('discoveries', [])),
        ('B', (data.get('strategy_b_semantic_neighborhood') or {}).get('discoveries', [])),
        ('C', (data.get('strategy_c_transversal_distant') or {}).get('discoveries', [])),
        ('D', (data.get('strategy_d_incremental') or {}).get('final_discoveries', [])),
    ]
    id_map = {}
    all_items = []
    for strat, items in strat_groups:
        for idx, item in enumerate(items, 1):
            old_id = item.get('discovery_id') or f'{strat}-{idx:02d}'
            new_id = old_id if old_id.startswith(f'EXP003-{exec_tag}-') or old_id.startswith(f'{exec_tag}-') else f'EXP003-{exec_tag}-{strat}-{idx:02d}'
            id_map[(strat, old_id)] = new_id
            item['discovery_id'] = new_id
            item['strategy'] = strat
            all_items.append(item)

    # Atualizar IDs nas avaliações existentes (A e D)
    existing_assessments = (data.get('strategy_e_confrontation') or {}).get('parsed', {}).get('assessments', [])
    for a in existing_assessments:
        old = a['discovery_id']
        if old.startswith('D-') and ('A', old) in id_map:
            a['discovery_id'] = id_map[('A', old)]
        elif old.startswith('INC-') and ('D', old) in id_map:
            a['discovery_id'] = id_map[('D', old)]

    # 2. Confrontar B e C (ou quaisquer pendentes) com o mesmo protocolo crítico de E
    already_assessed = {a['discovery_id'] for a in existing_assessments}
    pending = []
    for item in all_items:
        if item['discovery_id'] not in already_assessed:
            pending.append({
                'discovery_id': item['discovery_id'],
                'title': item['title'],
                'formulation': item['formulation'],
                'supporting_record_ids': [s['record_id'] for s in item.get('supporting_records', [])],
            })

    if pending and 'E' in set(cfg.get('enabled_strategies') or ['E']):
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
            'REGISTROS ORIGINAIS:\n' + '\n\n---\n\n'.join(format_record(r) for r in records) + '\n\n'
            f'DESCOBERTAS CANDIDATAS:\n{json.dumps(pending, ensure_ascii=False, indent=2)}'
        )
        system_critique = (
            'Você é um revisor epistemológico rigoroso. Não elogie descobertas fracas ou redundantes. '
            'Classifique como WEAK_OR_REDUNDANT se a descoberta apenas resumir ou repetir um único registro. '
            'Responda em português e estritamente no JSON solicitado.'
        )
        res_bc = call_llm(
            system_critique,
            prompt_e,
            CONFRONTATION_SCHEMA,
            model=conf_model,
            temperature=conf_temp,
            seed=conf_seed,
            num_ctx=num_ctx,
        )
        existing_assessments.extend(res_bc['parsed']['assessments'])
        data['strategy_e_confrontation']['bc_supplement'] = res_bc

    # 3. Verificação determinística + distinção em três dimensões (EXP-004 §9)
    assess_by_id = {a['discovery_id']: a for a in existing_assessments}
    confrontation_entries = []
    candidate_ids = {item['discovery_id'] for item in all_items}
    orphan_assessments = [a for a in existing_assessments if a.get('discovery_id') not in candidate_ids]
    det_summary = {
        'total': len(all_items),
        'consistent': 0,
        'inconsistent': 0,
        'effective_sustained': 0,
        'orphan_assessments_count': len(orphan_assessments),
    }

    for item in all_items:
        did = item['discovery_id']
        # Recalcular verificação por registro contra o corpus congelado para consistência total
        recomputed_verif = []
        for sr in item.get('supporting_records') or []:
            rid = sr.get('record_id')
            rec = rec_by_id.get(rid)
            corpus = ''
            if rec:
                corpus = '\n'.join(
                    str(x) for x in (rec.get('title'), rec.get('scope'), rec.get('claim'), rec.get('why_matters'), rec.get('limitations')) if x
                )
            ex_checks = [{'excerpt': ex, 'exact_match': bool(ex and ex.strip()) and (ex.strip() in corpus)} for ex in sr.get('excerpts', [])]
            recomputed_verif.append({'record_id': rid, 'record_exists': rec is not None, 'excerpts': ex_checks})
        item['verification'] = recomputed_verif

        assess = assess_by_id.get(did)
        det = deterministic_verify(item, rec_by_id, assess)
        item['deterministic_verification'] = det
        item['effective_status'] = det['effective_status']
        if det['inconsistencies']:
            det_summary['inconsistent'] += 1
        else:
            det_summary['consistent'] += 1
        if det['effective_status'] == 'SUSTAINED_CANDIDATE':
            det_summary['effective_sustained'] += 1

        confrontation_entries.append({
            'discovery_id': did,
            'strategy': item.get('strategy'),
            'title': item.get('title'),
            'deterministic_verification': det,
            'automated_critique': {
                **(assess or {'verdict': 'NOT_EXAMINED'}),
                'model': conf_model,
                'same_model_limitation': same_model_limitation,
            },
            'human_recognition': {
                'status': 'NOT_RECOGNIZED_IN_CANONICAL_ARCHIVE',
                'note': 'Proposição candidata fora do acervo canônico; reconhecimento intelectual humano não realizado.',
            },
        })

    _atomic_write_json(path, data)
    _atomic_write_json(run_dir / 'confrontation.json', {
        'run_id': data.get('run_id'),
        'corpus_sha256': data.get('corpus_sha256'),
        'confrontation_model': conf_model,
        'same_model_limitation': same_model_limitation,
        'summary': det_summary,
        'orphan_assessments': orphan_assessments,
        'entries': confrontation_entries,
    })

    manifest_path = run_dir / 'manifest.json'
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['status'] = 'completed'
        manifest['finished_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        manifest['deterministic_checks_summary'] = det_summary
        manifest['confrontation_summary'] = {
            'total_assessed': len(existing_assessments),
            'sustained_llm': sum(1 for a in existing_assessments if a.get('verdict') == 'SUSTAINED_CANDIDATE'),
            'weak_or_redundant': sum(1 for a in existing_assessments if a.get('verdict') == 'WEAK_OR_REDUNDANT'),
            'contested': sum(1 for a in existing_assessments if a.get('verdict') == 'CONTESTED'),
            'effective_sustained': det_summary['effective_sustained'],
            'orphan_assessments_count': len(orphan_assessments),
        }
        manifest['abstentions_count'] = (
            len((data.get('strategy_a_integral') or {}).get('abstentions', []))
            + len((data.get('strategy_b_semantic_neighborhood') or {}).get('abstentions', []))
            + len((data.get('strategy_c_transversal_distant') or {}).get('abstentions', []))
        )
        _atomic_write_json(manifest_path, manifest)

    # 4. Atualização atômica de latest.json e results.json raiz somente após sucesso integral
    if run_dir != OUT_DIR and data.get('run_id'):
        _atomic_write_json(OUT_DIR / 'latest.json', {
            'run_id': data['run_id'],
            'profile': data.get('profile'),
            'executed_at': data.get('executed_at'),
            'finished_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'corpus_sha256': data.get('corpus_sha256'),
            'summary': det_summary,
        })
        _atomic_write_json(OUT_DIR / 'results.json', data)
        pending_file = OUT_DIR / '.pending_run'
        if pending_file.is_file():
            pending_file.unlink()

    print('UPDATED:', path)
    for c in confrontation_entries:
        det = c['deterministic_verification']
        print(f"  {c['discovery_id']} -> effective={det['effective_status']} (llm={c['automated_critique'].get('verdict')}, inc={len(det['inconsistencies'])})")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BB-CORE-EXP-004 confrontation post-processor')
    parser.add_argument('--run-dir', type=str, default=None)
    args = parser.parse_args()
    main(args.run_dir)
