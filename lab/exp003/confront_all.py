"""Pós-processamento do BB-CORE-EXP-003: garante IDs únicos por estratégia/execução
e submete os resultados das estratégias B e C à mesma confrontação crítica de E.
"""
from __future__ import annotations

import json
from pathlib import Path

from run_exp003 import (
    CONFRONTATION_SCHEMA,
    OUT_DIR,
    call_llm,
    format_record,
    load_bbcore_records,
)


def main():
    path = OUT_DIR / 'results.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    records = load_bbcore_records()
    exec_tag = data['executed_at']

    # 1. Garantir IDs únicos considerando execução e estratégia
    strat_groups = [
        ('A', data['strategy_a_integral']['discoveries']),
        ('B', data['strategy_b_semantic_neighborhood']['discoveries']),
        ('C', data['strategy_c_transversal_distant']['discoveries']),
        ('D', data['strategy_d_incremental']['final_discoveries']),
    ]
    id_map = {}
    for strat, items in strat_groups:
        for idx, item in enumerate(items, 1):
            old_id = item.get('discovery_id') or f'{strat}-{idx:02d}'
            new_id = f'EXP003-{exec_tag}-{strat}-{idx:02d}'
            id_map[(strat, old_id)] = new_id
            item['discovery_id'] = new_id
            item['strategy'] = strat

    # Atualizar IDs nas avaliações existentes (A e D)
    existing_assessments = data['strategy_e_confrontation']['parsed']['assessments']
    for a in existing_assessments:
        old = a['discovery_id']
        if old.startswith('D-') and ('A', old) in id_map:
            a['discovery_id'] = id_map[('A', old)]
        elif old.startswith('INC-') and ('D', old) in id_map:
            a['discovery_id'] = id_map[('D', old)]

    # 2. Confrontar B e C com o mesmo protocolo crítico de E
    already_assessed = {a['discovery_id'] for a in existing_assessments}
    pending = []
    for strat in ('B', 'C'):
        items = data['strategy_b_semantic_neighborhood']['discoveries'] if strat == 'B' else data['strategy_c_transversal_distant']['discoveries']
        for item in items:
            if item['discovery_id'] not in already_assessed:
                pending.append({
                    'discovery_id': item['discovery_id'],
                    'title': item['title'],
                    'formulation': item['formulation'],
                    'supporting_record_ids': [s['record_id'] for s in item['supporting_records']],
                })

    if pending:
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
        res_bc = call_llm(system_critique, prompt_e, CONFRONTATION_SCHEMA)
        existing_assessments.extend(res_bc['parsed']['assessments'])
        data['strategy_e_confrontation']['bc_supplement'] = res_bc

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('UPDATED:', path)
    for a in existing_assessments:
        print(f"  {a['discovery_id']} -> {a['verdict']} | {a['critique'][:80]}")


if __name__ == '__main__':
    main()
