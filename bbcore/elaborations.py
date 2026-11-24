"""Mesa de Elaboração: persistência local independente do acervo canônico.

Armazena elaborações provisórias em tabela SQLite isolada (`elaborations`),
sem chaves estrangeiras bloqueantes, sem entrada no diário `BB-EVENT-1` e sem
indexação no acervo confirmado (`insights` / `insights_fts`).
"""
import json
import uuid

from .store import NotFound, canonical, required_string, stamp

MAX_ELABORATION_ITEMS = 64


def optional_draft_text(value, name, limit):
    if value is None:
        return ''
    if not isinstance(value, str) or len(value.encode('utf-8')) > limit:
        raise ValueError(f'{name}: texto inválido (limite de {limit} bytes)')
    return value


def _normalize_excerpts(items):
    if items is None:
        return []
    if not isinstance(items, list) or len(items) > MAX_ELABORATION_ITEMS:
        raise ValueError(f'excerpts: lista de até {MAX_ELABORATION_ITEMS} trechos')
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('excerpts: cada trecho deve ser objeto')
        quote = required_string(item.get('quote'), 'excerpts.quote', 20_000, preserve=True)
        receipt_id = required_string(item.get('receipt_id'), 'excerpts.receipt_id', 64)
        start, end = item.get('start_byte'), item.get('end_byte')
        if type(start) is not int or type(end) is not int or not 0 <= start < end:
            raise ValueError('excerpts: offsets em bytes inválidos')
        result.append({
            'receipt_id': receipt_id,
            'version_id': optional_draft_text(item.get('version_id'), 'excerpts.version_id', 64),
            'label': optional_draft_text(item.get('label'), 'excerpts.label', 240),
            'declared_version': optional_draft_text(item.get('declared_version'), 'excerpts.declared_version', 120),
            'quote': quote,
            'start_byte': start,
            'end_byte': end,
            'role': optional_draft_text(item.get('role'), 'excerpts.role', 100) or 'documentary_support',
        })
    return result


def _normalize_references(items):
    if items is None:
        return []
    if not isinstance(items, list) or len(items) > MAX_ELABORATION_ITEMS:
        raise ValueError(f'references: lista de até {MAX_ELABORATION_ITEMS} referências')
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('references: cada referência deve ser objeto')
        iid = required_string(item.get('insight_id'), 'references.insight_id', 64)
        result.append({
            'insight_id': iid,
            'title': optional_draft_text(item.get('title'), 'references.title', 240),
            'role': optional_draft_text(item.get('role'), 'references.role', 100) or 'reference',
        })
    return result


class Elaborations:
    def __init__(self, archive):
        self.archive = archive
        self.db = archive.db
        with archive.lock:
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS elaborations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                why_matters TEXT NOT NULL DEFAULT '',
                genesis TEXT NOT NULL DEFAULT '',
                limitations TEXT NOT NULL DEFAULT '',
                excerpts_json TEXT NOT NULL DEFAULT '[]',
                references_json TEXT NOT NULL DEFAULT '[]',
                target_insight_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS elaborations_updated ON elaborations(updated_at DESC);
            ''')

    @staticmethod
    def _hydrate(row):
        item = dict(row)
        item['excerpts'] = json.loads(item.pop('excerpts_json'))
        item['references'] = json.loads(item.pop('references_json'))
        return item

    def list(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('limit inválido')
        with self.archive.lock:
            rows = self.db.execute(
                'SELECT * FROM elaborations ORDER BY updated_at DESC, rowid DESC LIMIT ?', (limit,)
            ).fetchall()
            return [self._hydrate(row) for row in rows]

    def get(self, eid):
        with self.archive.lock:
            row = self.db.execute('SELECT * FROM elaborations WHERE id=?', (eid,)).fetchone()
            if row is None:
                raise NotFound('Elaboração não encontrada')
            return self._hydrate(row)

    def save(self, data):
        if not isinstance(data, dict):
            raise ValueError('Esperado objeto JSON')
        raw_id = data.get('id')
        eid = required_string(raw_id, 'id', 64) if raw_id else None
        title = optional_draft_text(data.get('title'), 'title', 240)
        notes = optional_draft_text(data.get('notes'), 'notes', 50_000)
        why_matters = optional_draft_text(data.get('why_matters'), 'why_matters', 4_000)
        genesis = optional_draft_text(data.get('genesis'), 'genesis', 10_000)
        limitations = optional_draft_text(data.get('limitations'), 'limitations', 10_000)
        excerpts = _normalize_excerpts(data.get('excerpts'))
        references = _normalize_references(data.get('references'))
        raw_target = data.get('target_insight_id')
        target = required_string(raw_target, 'target_insight_id', 64) if raw_target else None
        now = stamp()
        with self.archive.transaction():
            if eid:
                existing = self.db.execute('SELECT id FROM elaborations WHERE id=?', (eid,)).fetchone()
                if existing is None:
                    raise NotFound('Elaboração não encontrada')
                self.db.execute(
                    '''UPDATE elaborations SET title=?, notes=?, why_matters=?, genesis=?, limitations=?,
                       excerpts_json=?, references_json=?, target_insight_id=?, updated_at=? WHERE id=?''',
                    (title, notes, why_matters, genesis, limitations,
                     canonical(excerpts), canonical(references), target, now, eid),
                )
                created = False
            else:
                eid = uuid.uuid4().hex
                self.db.execute(
                    'INSERT INTO elaborations VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (eid, title, notes, why_matters, genesis, limitations,
                     canonical(excerpts), canonical(references), target, now, now),
                )
                created = True
            return self.get(eid), created

    def delete(self, eid):
        with self.archive.transaction():
            cur = self.db.execute('DELETE FROM elaborations WHERE id=?', (eid,))
            if cur.rowcount == 0:
                raise NotFound('Elaboração não encontrada')
            return {'deleted': True, 'id': eid}
