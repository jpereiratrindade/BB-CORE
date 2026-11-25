"""Configuração persistente, validada e versionada para investigação e descoberta (BB-CORE-EXP-004).

Mantida fora do acervo canônico (insights, relations, intellectual_events).
"""
from __future__ import annotations

import copy
import json
from typing import Any

from .store import stamp

VALID_PROFILES = ('reference', 'exploration', 'verification')
VALID_STRATEGIES = ('A', 'B', 'C', 'D', 'E')

PROFILE_LABELS = {
    'reference': 'Referência',
    'exploration': 'Exploração',
    'verification': 'Verificação',
}

DEFAULT_INVESTIGATION_CONFIG: dict[str, Any] = {
    'profile': 'reference',
    'investigator_model': 'qwen2.5:14b',
    'embed_model': 'qwen3-embedding:4b',
    'confrontation_model': 'qwen2.5:14b',
    'reference_temperature': 0.0,
    'exploratory_temperature': 0.2,
    'seed': 42,
    'context_window': 16384,
    'exploratory_repetitions': 3,
    'enabled_strategies': ['A', 'B', 'C', 'D', 'E'],
    'confrontation_temperature': 0.0,
    'confrontation_seed': 42,
}

PARAMETER_DOCS: dict[str, str] = {
    'profile': 'Perfil investigativo padrão utilizado automaticamente ao acionar novas análises.',
    'investigator_model': 'Modelo de linguagem utilizado na geração de descobertas e abstrações (estratégias A–D).',
    'embed_model': 'Modelo de embeddings vetoriais usado para seleção de vizinhança e contraste semântico.',
    'confrontation_model': 'Modelo de linguagem usado na confrontação crítica independente (estratégia E).',
    'reference_temperature': 'Temperatura aplicada no perfil Referência (0.0 prioriza estabilidade comparativa).',
    'exploratory_temperature': 'Temperatura aplicada no perfil Exploração para investigar formulações alternativas.',
    'seed': 'Semente inicial de geração para o perfil Referência (e base para variações no perfil Exploração).',
    'context_window': 'Tamanho da janela de contexto (num_ctx) enviada ao modelo.',
    'exploratory_repetitions': 'Quantidade de execuções com seeds distintas no perfil Exploração.',
    'enabled_strategies': 'Subconjunto de estratégias habilitadas para a execução (A, B, C, D e E).',
    'confrontation_temperature': 'Temperatura independente usada exclusivamente na etapa de confrontação crítica.',
    'confrontation_seed': 'Seed independente usada exclusivamente na etapa de confrontação crítica.',
}


def ensure_investigation_tables(db) -> None:
    """Garante as tabelas não canônicas de configuração experimental."""
    db.execute(
        '''
        CREATE TABLE IF NOT EXISTS investigation_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL,
            config_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        '''
    )
    db.execute(
        '''
        CREATE TABLE IF NOT EXISTS investigation_settings_history (
            version INTEGER PRIMARY KEY,
            config_json TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            change_note TEXT
        )
        '''
    )
    row = db.execute('SELECT version FROM investigation_settings WHERE id = 1').fetchone()
    if row is None:
        now = stamp()
        payload = json.dumps(DEFAULT_INVESTIGATION_CONFIG, ensure_ascii=False, sort_keys=True)
        with db:
            db.execute(
                'INSERT INTO investigation_settings (id, version, config_json, updated_at) VALUES (1, 1, ?, ?)',
                (payload, now),
            )
            db.execute(
                'INSERT INTO investigation_settings_history (version, config_json, changed_at, change_note) VALUES (1, ?, ?, ?)',
                (payload, now, 'Configuração inicial padrão (EXP-004)'),
            )


def _require_nonempty_str(val: Any, field: str) -> str:
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f'{field} deve ser uma string não vazia.')
    return val.strip()


def _require_float_range(val: Any, field: str, low: float, high: float) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(f'{field} deve ser numérico.')
    f = float(val)
    if not (low <= f <= high):
        raise ValueError(f'{field} deve estar entre {low} e {high}.')
    return round(f, 4)


def _require_int_range(val: Any, field: str, low: int, high: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int):
        raise ValueError(f'{field} deve ser um número inteiro.')
    if not (low <= val <= high):
        raise ValueError(f'{field} deve estar entre {low} e {high}.')
    return val


def validate_investigation_config(raw: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Valida e normaliza um dicionário de configuração investigativa."""
    if not isinstance(raw, dict):
        raise ValueError('Configuração deve ser um objeto JSON.')
    merged = copy.deepcopy(base if base is not None else DEFAULT_INVESTIGATION_CONFIG)
    for k in DEFAULT_INVESTIGATION_CONFIG:
        if k in raw:
            merged[k] = raw[k]

    profile = _require_nonempty_str(merged['profile'], 'profile').lower()
    if profile not in VALID_PROFILES:
        raise ValueError(f'profile deve ser um de: {", ".join(VALID_PROFILES)}.')

    strategies_raw = merged['enabled_strategies']
    if not isinstance(strategies_raw, list) or not strategies_raw:
        raise ValueError('enabled_strategies deve ser uma lista não vazia.')
    strategies: list[str] = []
    for item in strategies_raw:
        s = _require_nonempty_str(item, 'enabled_strategies').upper()
        if s not in VALID_STRATEGIES:
            raise ValueError(f'Estratégia inválida: {s}.')
        if s not in strategies:
            strategies.append(s)

    return {
        'profile': profile,
        'investigator_model': _require_nonempty_str(merged['investigator_model'], 'investigator_model'),
        'embed_model': _require_nonempty_str(merged['embed_model'], 'embed_model'),
        'confrontation_model': _require_nonempty_str(merged['confrontation_model'], 'confrontation_model'),
        'reference_temperature': _require_float_range(merged['reference_temperature'], 'reference_temperature', 0.0, 2.0),
        'exploratory_temperature': _require_float_range(merged['exploratory_temperature'], 'exploratory_temperature', 0.0, 2.0),
        'seed': _require_int_range(merged['seed'], 'seed', 0, 2_147_483_647),
        'context_window': _require_int_range(merged['context_window'], 'context_window', 1024, 131072),
        'exploratory_repetitions': _require_int_range(merged['exploratory_repetitions'], 'exploratory_repetitions', 1, 10),
        'enabled_strategies': strategies,
        'confrontation_temperature': _require_float_range(merged['confrontation_temperature'], 'confrontation_temperature', 0.0, 2.0),
        'confrontation_seed': _require_int_range(merged['confrontation_seed'], 'confrontation_seed', 0, 2_147_483_647),
    }


def get_investigation_settings(db) -> dict[str, Any]:
    """Retorna a configuração vigente, padrões, documentação e histórico de versões."""
    ensure_investigation_tables(db)
    row = db.execute('SELECT version, config_json, updated_at FROM investigation_settings WHERE id = 1').fetchone()
    history_rows = db.execute(
        'SELECT version, config_json, changed_at, change_note FROM investigation_settings_history ORDER BY version DESC LIMIT 20'
    ).fetchall()
    return {
        'version': row['version'],
        'updated_at': row['updated_at'],
        'config': json.loads(row['config_json']),
        'defaults': copy.deepcopy(DEFAULT_INVESTIGATION_CONFIG),
        'parameter_docs': dict(PARAMETER_DOCS),
        'profile_labels': dict(PROFILE_LABELS),
        'history': [
            {
                'version': h['version'],
                'changed_at': h['changed_at'],
                'change_note': h['change_note'],
                'config': json.loads(h['config_json']),
            }
            for h in history_rows
        ],
    }


def update_investigation_settings(db, raw_config: dict[str, Any], *, change_note: str | None = None) -> dict[str, Any]:
    """Valida, versiona e persiste nova configuração investigativa."""
    ensure_investigation_tables(db)
    current_row = db.execute('SELECT version, config_json FROM investigation_settings WHERE id = 1').fetchone()
    current_cfg = json.loads(current_row['config_json'])
    validated = validate_investigation_config(raw_config, base=current_cfg)
    next_version = int(current_row['version']) + 1
    now = stamp()
    payload = json.dumps(validated, ensure_ascii=False, sort_keys=True)
    note = (change_note or 'Atualização de parâmetros investigativos').strip()[:240]
    with db:
        db.execute(
            'UPDATE investigation_settings SET version = ?, config_json = ?, updated_at = ? WHERE id = 1',
            (next_version, payload, now),
        )
        db.execute(
            'INSERT INTO investigation_settings_history (version, config_json, changed_at, change_note) VALUES (?, ?, ?, ?)',
            (next_version, payload, now, note),
        )
    return get_investigation_settings(db)


def reset_investigation_settings(db) -> dict[str, Any]:
    """Restaura a configuração padrão como nova versão registrada no histórico."""
    return update_investigation_settings(
        db,
        copy.deepcopy(DEFAULT_INVESTIGATION_CONFIG),
        change_note='Restauração dos valores padrão (EXP-004)',
    )
