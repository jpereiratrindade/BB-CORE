"""Documentos imutáveis, recebimentos e elaboração humana ancorada em bytes UTF-8."""
import base64
import binascii
import hashlib
import json
import uuid
from datetime import date
from pathlib import PurePath

from .store import Conflict, canonical, digest, object_field, required_string, stamp

MAX_DOCUMENT_BYTES = 256_000
KINDS = {
    'CONCEPTUAL_FINDING': {'PROPOSED'},
    'METHODOLOGICAL_DECISION': {'PROPOSED', 'ADOPTED'},
    'OPEN_QUESTION': {'OPEN'},
    'EMPIRICAL_REPORT': {'REPORTED'},
}


def uid():
    return uuid.uuid4().hex


def optional_text(value, name, limit):
    return None if value is None or value == '' else required_string(value, name, limit)


class Documents:
    def __init__(self, archive):
        self.archive = archive
        self.db = archive.db
        with archive.lock:
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS document_contents (
                sha256 TEXT PRIMARY KEY, body BLOB NOT NULL, byte_length INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, external_id TEXT UNIQUE, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS document_versions (
                id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
                declared_version TEXT, sha256 TEXT NOT NULL REFERENCES document_contents(sha256),
                created_at TEXT NOT NULL, UNIQUE(document_id, declared_version)
            );
            CREATE TABLE IF NOT EXISTS document_receipts (
                id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES document_versions(id),
                sha256 TEXT NOT NULL REFERENCES document_contents(sha256), filename TEXT NOT NULL,
                provenance TEXT NOT NULL, declared_date TEXT, received_by TEXT NOT NULL,
                received_at TEXT NOT NULL, outcome TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE, declared_external_id TEXT, declared_version TEXT
            );
            CREATE TABLE IF NOT EXISTS record_elaborations (
                insight_id TEXT PRIMARY KEY REFERENCES insights(id), kind TEXT NOT NULL,
                work_state TEXT NOT NULL, formulation_origin TEXT NOT NULL,
                confirmed_by_declared TEXT NOT NULL, confirmed_at TEXT NOT NULL,
                supersedes_id TEXT REFERENCES insights(id)
            );
            CREATE TABLE IF NOT EXISTS document_anchors (
                id TEXT PRIMARY KEY, insight_id TEXT NOT NULL REFERENCES insights(id),
                version_id TEXT NOT NULL REFERENCES document_versions(id),
                receipt_id TEXT NOT NULL REFERENCES document_receipts(id),
                quote TEXT NOT NULL, start_byte INTEGER NOT NULL, end_byte INTEGER NOT NULL,
                role TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS imported_record_identities (
                identity_key TEXT PRIMARY KEY,
                declared_record_key TEXT UNIQUE,
                receipt_id TEXT,
                id_local TEXT,
                insight_id TEXT NOT NULL REFERENCES insights(id),
                document_external_id TEXT,
                declared_version TEXT,
                claim_sha256 TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                recognition_kind TEXT NOT NULL DEFAULT 'CONFIRMED_FROM_PARAMETRIZED',
                confirmed_by_declared TEXT,
                rationale TEXT,
                confirmed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS document_anchor_record ON document_anchors(insight_id);
            CREATE INDEX IF NOT EXISTS document_receipt_version ON document_receipts(version_id);
            ''')
            cols = {r['name'] for r in self.db.execute('PRAGMA table_info(imported_record_identities)')}
            if 'identity_key' not in cols:
                self.db.executescript('''
                ALTER TABLE imported_record_identities RENAME TO imported_record_identities_v1;
                CREATE TABLE imported_record_identities (
                    identity_key TEXT PRIMARY KEY,
                    declared_record_key TEXT UNIQUE,
                    receipt_id TEXT,
                    id_local TEXT,
                    insight_id TEXT NOT NULL REFERENCES insights(id),
                    document_external_id TEXT,
                    declared_version TEXT,
                    claim_sha256 TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    recognition_kind TEXT NOT NULL DEFAULT 'CONFIRMED_FROM_PARAMETRIZED',
                    confirmed_by_declared TEXT,
                    rationale TEXT,
                    confirmed_at TEXT NOT NULL
                );
                INSERT INTO imported_record_identities (
                    identity_key, declared_record_key, insight_id, document_external_id,
                    declared_version, claim_sha256, content_sha256, confirmed_at
                )
                SELECT declared_record_key, declared_record_key, insight_id, document_external_id,
                       declared_version, claim_sha256, content_sha256, confirmed_at
                FROM imported_record_identities_v1;
                DROP TABLE imported_record_identities_v1;
                ''')
            self.db.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS imported_record_occurrence
                ON imported_record_identities(receipt_id, id_local)
                WHERE receipt_id IS NOT NULL AND id_local IS NOT NULL
            ''')

    def _retry(self, data, operation):
        request_id = required_string(data.get('request_id'), 'request_id', 128)
        try:
            uuid.UUID(request_id)
        except ValueError:
            raise ValueError('request_id deve ser UUID') from None
        signature = digest(canonical({'operation': operation, 'data': data}))
        old = self.db.execute('SELECT signature,response FROM requests WHERE request_id=?', (request_id,)).fetchone()
        if old:
            if old['signature'] != signature:
                raise Conflict('request_id já utilizado com outro conteúdo ou operação')
            return request_id, signature, json.loads(old['response'])
        return request_id, signature, None

    def _remember(self, request_id, signature, result):
        self.db.execute('INSERT INTO requests VALUES(?,?,?)', (request_id, signature, canonical(result)))
        return result

    def ingest(self, data):
        if not isinstance(data, dict):
            raise ValueError('Esperado objeto JSON')
        filename = required_string(data.get('filename'), 'filename', 240)
        if '/' in filename or '\\' in filename or any(ord(c) < 32 for c in filename):
            raise ValueError('Nome de arquivo inválido')
        if PurePath(filename).suffix.lower() not in {'.md', '.txt'}:
            raise ValueError('Nesta etapa, apenas Markdown e TXT UTF-8')
        encoded = required_string(data.get('content_base64'), 'content_base64', 350_000)
        try:
            body = base64.b64decode(encoded, validate=True)
            text = body.decode('utf-8')
        except (ValueError, binascii.Error, UnicodeDecodeError):
            raise ValueError('Conteúdo deve ser base64 válido de texto UTF-8') from None
        if not body or len(body) > MAX_DOCUMENT_BYTES or '\x00' in text or not text.strip('\ufeff \r\n\t'):
            raise ValueError('Documento vazio, binário ou maior que 256000 bytes')
        external_id = optional_text(data.get('external_id'), 'external_id', 240)
        version = optional_text(data.get('declared_version'), 'declared_version', 120)
        provenance = required_string(data.get('provenance'), 'provenance', 4000)
        actor = required_string(data.get('received_by'), 'received_by', 240)
        declared_date = optional_text(data.get('declared_date'), 'declared_date', 10)
        if declared_date:
            date.fromisoformat(declared_date)
        if data.get('confirmed') is not True:
            raise ValueError('Confirmação explícita de recebimento obrigatória')
        sha = hashlib.sha256(body).hexdigest()
        with self.archive.transaction():
            request_id, signature, retry = self._retry(data, 'document_ingest')
            if retry is not None:
                return retry
            now = stamp()
            self.db.execute('INSERT OR IGNORE INTO document_contents VALUES(?,?,?)', (sha, body, len(body)))
            preserved = self.db.execute('SELECT body,byte_length FROM document_contents WHERE sha256=?', (sha,)).fetchone()
            if bytes(preserved['body']) != body or preserved['byte_length'] != len(body):
                raise Conflict('Conteúdo armazenado não corresponde ao hash; recebimento interrompido')
            # Identidade não declarada não é deduzida do nome do arquivo.
            if external_id:
                document = self.db.execute('SELECT id FROM documents WHERE external_id=?', (external_id,)).fetchone()
            else:
                document = self.db.execute('''SELECT d.id FROM documents d JOIN document_versions v ON v.document_id=d.id
                    WHERE d.external_id IS NULL AND v.declared_version IS ? AND v.sha256=? LIMIT 1''', (version, sha)).fetchone()
            document_id = document['id'] if document else uid()
            if not document:
                self.db.execute('INSERT INTO documents VALUES(?,?,?)', (document_id, external_id, now))
            existing = self.db.execute('SELECT * FROM document_versions WHERE document_id=? AND declared_version IS ?',
                                       (document_id, version)).fetchone()
            if existing:
                version_id = existing['id']
                outcome = 'RECEIVED_AGAIN' if existing['sha256'] == sha else 'VERSION_CONFLICT'
            else:
                version_id = uid()
                outcome = 'PRESERVED'
                self.db.execute('INSERT INTO document_versions VALUES(?,?,?,?,?)', (version_id, document_id, version, sha, now))
            receipt_id = uid()
            self.db.execute('INSERT INTO document_receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                            (receipt_id, version_id, sha, filename, provenance, declared_date, actor, now, outcome,
                             request_id, external_id, version))
            result = {'document_id': document_id, 'version_id': version_id, 'receipt_id': receipt_id,
                      'sha256': sha, 'byte_length': len(body), 'outcome': outcome, 'received_at': now}
            if outcome == 'VERSION_CONFLICT':
                result['accepted_sha256'] = existing['sha256']
                result['message'] = 'Mesmo identificador e versão, conteúdo diferente. Recebimento preservado para revisão; versão original mantida.'
            return self._remember(request_id, signature, result)

    def original(self, version_id=None, receipt_id=None):
        with self.archive.lock:
            if receipt_id:
                row = self.archive._one('''SELECT c.* FROM document_contents c JOIN document_receipts r ON r.sha256=c.sha256
                    WHERE r.id=?''', (receipt_id,))
            else:
                row = self.archive._one('''SELECT c.* FROM document_contents c JOIN document_versions v ON v.sha256=c.sha256
                    WHERE v.id=?''', (version_id,))
            body = bytes(row['body'])
            if hashlib.sha256(body).hexdigest() != row['sha256'] or len(body) != row['byte_length']:
                raise Conflict('Falha de integridade dos bytes documentais')
            return body

    def list(self, offset=0):
        if type(offset) is not int or offset < 0:
            raise ValueError('offset inválido')
        with self.archive.lock:
            return [dict(row) for row in self.db.execute('''SELECT v.*, d.external_id,
                (SELECT count(*) FROM document_receipts r WHERE r.version_id=v.id) AS receipt_count,
                (SELECT count(*) FROM document_receipts r WHERE r.version_id=v.id AND r.outcome='VERSION_CONFLICT') AS conflict_count,
                (SELECT filename FROM document_receipts r WHERE r.version_id=v.id ORDER BY r.received_at,r.rowid LIMIT 1) AS filename
                FROM document_versions v JOIN documents d ON d.id=v.document_id
                ORDER BY v.created_at DESC,v.rowid DESC LIMIT 100 OFFSET ?''', (offset,))]

    def get(self, version_id):
        with self.archive.lock:
            item = self.archive._one('''SELECT v.*,d.external_id FROM document_versions v
                JOIN documents d ON d.id=v.document_id WHERE v.id=?''', (version_id,))
            item['text'] = self.original(version_id).decode('utf-8')
            item['receipts'] = [dict(r) for r in self.db.execute('SELECT * FROM document_receipts WHERE version_id=? ORDER BY received_at,rowid', (version_id,))]
            item['records'] = [dict(r) for r in self.db.execute('''SELECT DISTINCT i.id,i.title,e.kind,e.work_state FROM insights i
                JOIN record_elaborations e ON e.insight_id=i.id JOIN document_anchors a ON a.insight_id=i.id
                WHERE a.version_id=?''', (version_id,))]
            item['versions'] = [dict(r) for r in self.db.execute('SELECT id,declared_version,sha256,created_at FROM document_versions WHERE document_id=? ORDER BY created_at,rowid', (item['document_id'],))]
            item['integrity'] = 'VERIFIED_LOCAL_BYTES'
            return item

    def create_record(self, data):
        if not isinstance(data, dict):
            raise ValueError('Esperado objeto JSON')
        title = required_string(data.get('title'), 'title', 240)
        claim = required_string(data.get('claim'), 'claim', 4000)
        why = required_string(data.get('why_matters'), 'why_matters', 4000)
        limitations = required_string(data.get('limitations'), 'limitations', 10000)
        genesis = object_field(data.get('genesis', {}), 'genesis')
        context = object_field(data.get('context', {}), 'context')
        kind, work_state = data.get('kind'), data.get('work_state')
        if not isinstance(kind, str) or kind not in KINDS or work_state not in KINDS[kind]:
            raise ValueError('Tipo e estado de trabalho incompatíveis')
        origin = data.get('formulation_origin')
        if origin not in ('HUMAN_FORMULATION', 'DOCUMENT_EXCERPT'):
            raise ValueError('Indique formulação humana ou trecho documental; sugestões por IA fora desta etapa')
        actor = required_string(data.get('confirmed_by_declared'), 'confirmed_by_declared', 240)
        if data.get('confirmed') is not True:
            raise ValueError('Confirmação humana explícita obrigatória')
        links = data.get('anchors')
        if not isinstance(links, list) or not 1 <= len(links) <= 16:
            raise ValueError('De 1 a 16 âncoras obrigatórias')
        supersedes = optional_text(data.get('supersedes_id'), 'supersedes_id', 64)
        declared_record_key = optional_text(data.get('declared_record_key'), 'declared_record_key', 240)
        id_local = optional_text(data.get('id_local'), 'id_local', 120)
        occurrence_receipt_id = optional_text(data.get('occurrence_receipt_id'), 'occurrence_receipt_id', 64)
        content_sha256 = optional_text(data.get('content_sha256'), 'content_sha256', 64)
        with self.archive.transaction():
            request_id, signature, retry = self._retry(data, 'document_record')
            if retry is not None:
                return retry
            if declared_record_key:
                existing_identity = self.db.execute(
                    'SELECT * FROM imported_record_identities WHERE declared_record_key=?',
                    (declared_record_key,),
                ).fetchone()
                if existing_identity:
                    raise Conflict(
                        f'Registro declarado "{declared_record_key}" já confirmado como {existing_identity["insight_id"]}'
                    )
            if occurrence_receipt_id and id_local:
                existing_occ = self.db.execute(
                    'SELECT * FROM imported_record_identities WHERE receipt_id=? AND id_local=?',
                    (occurrence_receipt_id, id_local),
                ).fetchone()
                if existing_occ:
                    raise Conflict(
                        f'Ocorrência documental ({occurrence_receipt_id}, {id_local}) já confirmada como {existing_occ["insight_id"]}'
                    )
            if supersedes:
                previous = self.archive._one('SELECT * FROM record_elaborations WHERE insight_id=?', (supersedes,))
                if previous['kind'] != kind:
                    raise ValueError('Revisão deve manter o tipo do registro anterior')
            anchors = []
            for link in links:
                if not isinstance(link, dict):
                    raise ValueError('Âncora deve ser objeto')
                receipt_id = required_string(link.get('receipt_id'), 'receipt_id', 64)
                receipt = self.archive._one('SELECT * FROM document_receipts WHERE id=?', (receipt_id,))
                if receipt['outcome'] == 'VERSION_CONFLICT':
                    raise Conflict('Recebimento em conflito não pode fundamentar registro antes de resolução')
                body = self.original(receipt['version_id'])
                if hashlib.sha256(body).hexdigest() != receipt['sha256']:
                    raise Conflict('Recebimento diverge da versão documental')
                quote = required_string(link.get('quote'), 'quote', 20000, preserve=True)
                start, end = link.get('start_byte'), link.get('end_byte')
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(body):
                    raise ValueError('Offsets em bytes UTF-8 obrigatórios e dentro do documento')
                if body[start:end] != quote.encode('utf-8'):
                    raise ValueError('Trecho não corresponde aos bytes indicados')
                role = required_string(link.get('role'), 'role', 100)
                anchors.append((uid(), None, receipt['version_id'], receipt_id, quote, start, end, role))
            if origin == 'DOCUMENT_EXCERPT' and not any(anchor[4] == claim for anchor in anchors):
                raise ValueError('Formulação declarada como trecho deve coincidir com uma das âncoras')
            iid, now = uid(), stamp()
            # Estado do trabalho e estatuto epistemológico são campos distintos.
            status = 'REPORTED' if kind in ('METHODOLOGICAL_DECISION', 'EMPIRICAL_REPORT') else 'INFERRED_CANDIDATE'
            stored_context = {**context, 'why_matters': why, 'record_kind': kind,
                              'epistemic_limit': 'Confirmação humana do registro não constitui validação científica.'}
            self.db.execute('INSERT INTO insights VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (iid, title, claim, status, canonical(genesis), limitations, canonical(stored_context), 'PRIVATE', now, 1))
            self.db.execute('INSERT INTO record_elaborations VALUES(?,?,?,?,?,?,?)', (iid, kind, work_state, origin, actor, now, supersedes))
            for anchor in anchors:
                self.db.execute('INSERT INTO document_anchors VALUES(?,?,?,?,?,?,?,?)', (anchor[0], iid, *anchor[2:]))
            self.db.execute('INSERT INTO insights_fts(insight_id,title,claim) VALUES(?,?,?)', (iid, title, claim))
            self.db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?)',
                            (uid(), iid, 1, 'HUMAN_CONFIRMED', canonical({'request_id': request_id, 'kind': kind,
                             'work_state': work_state, 'confirmed_by_declared': actor, 'formulation_origin': origin,
                             'supersedes_id': supersedes}), now))
            self.archive.events.registered(iid, request_id)
            if supersedes:
                self.archive.events.revision_reference(supersedes, iid, actor, request_id)
            if declared_record_key or (occurrence_receipt_id and id_local):
                claim_sha = hashlib.sha256(claim.encode('utf-8')).hexdigest()
                identity_key = declared_record_key or f'occurrence:{occurrence_receipt_id}:{id_local}'
                self.db.execute(
                    'INSERT INTO imported_record_identities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (
                        identity_key,
                        declared_record_key,
                        occurrence_receipt_id,
                        id_local,
                        iid,
                        optional_text(context.get('external_document_id') if isinstance(context, dict) else None, 'external_document_id', 240),
                        optional_text(context.get('document_version') if isinstance(context, dict) else None, 'document_version', 120),
                        claim_sha,
                        content_sha256 or claim_sha,
                        'CONFIRMED_FROM_PARAMETRIZED',
                        actor,
                        'Confirmação explícita de candidato parametrizado',
                        now,
                    ),
                )
            return self._remember(request_id, signature, {'id': iid, 'kind': kind, 'work_state': work_state, 'status': status, 'confirmed_at': now})

    def sources_for(self, insight_id):
        sources = []
        for row in self.db.execute('''SELECT a.*,v.sha256,r.filename,r.received_at,r.received_by,r.provenance,
                r.sha256 AS receipt_sha256,r.outcome AS receipt_outcome,r.version_id AS receipt_version_id
                FROM document_anchors a JOIN document_versions v ON v.id=a.version_id
                JOIN document_receipts r ON r.id=a.receipt_id WHERE a.insight_id=?''', (insight_id,)):
            item = dict(row)
            body = self.original(item['version_id'])
            if (not 0 <= item['start_byte'] < item['end_byte'] <= len(body)
                    or item['receipt_version_id'] != item['version_id'] or item['receipt_sha256'] != item['sha256']
                    or item['receipt_outcome'] == 'VERSION_CONFLICT'
                    or body[item['start_byte']:item['end_byte']] != item['quote'].encode('utf-8')):
                raise Conflict('Falha de integridade da âncora documental')
            sources.append({**item, 'body': body.decode('utf-8'), 'origin': item['filename'],
                            'author': None, 'coverage': 'USER_SUPPLIED_FULL', 'recorded_at': item['received_at']})
        return sources

    def verify(self):
        total = bad = anchor_bad = 0
        for row in self.db.execute('SELECT * FROM document_contents'):
            total += 1
            body = bytes(row['body'])
            bad += hashlib.sha256(body).hexdigest() != row['sha256'] or len(body) != row['byte_length']
        for row in self.db.execute('SELECT DISTINCT insight_id FROM document_anchors'):
            try:
                self.sources_for(row['insight_id'])
            except Conflict:
                anchor_bad += 1
        return {'document_contents_checked': total, 'document_hash_mismatches': bad, 'document_anchor_failures': anchor_bad}

    def inspect_parametrized(self, *, version_id=None, receipt_id=None, content_base64=None):
        from .parametrized import ParametrizedError, parse_parametrized_markdown

        if receipt_id is not None:
            raw_bytes = self.original(receipt_id=receipt_id)
        elif version_id is not None:
            raw_bytes = self.original(version_id=version_id)
        else:
            encoded = required_string(content_base64, 'content_base64', 350_000)
            try:
                raw_bytes = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                raise ValueError('Conteúdo deve ser base64 válido') from None

        try:
            parsed = parse_parametrized_markdown(raw_bytes)
        except ParametrizedError as err:
            return {'is_parametrized': False, 'error': str(err)}

        ext_doc_id = parsed['document'].get('external_id')
        with self.archive.lock:
            target_receipt_id = receipt_id
            if target_receipt_id is None and version_id is not None:
                row = self.db.execute(
                    "SELECT id FROM document_receipts WHERE version_id=? AND outcome!='VERSION_CONFLICT' ORDER BY received_at,rowid LIMIT 1",
                    (version_id,),
                ).fetchone()
                if row:
                    target_receipt_id = row['id']
            legacy_rows = []
            if ext_doc_id:
                legacy_rows = self.db.execute(
                    """SELECT id, title, claim FROM insights
                       WHERE json_extract(context, '$.external_document_id')=?
                         AND id NOT IN (SELECT insight_id FROM imported_record_identities)""",
                    (ext_doc_id,),
                ).fetchall()
            for rec in parsed['records']:
                key = rec.get('external_record_id')
                existing = None
                if key:
                    existing = self.db.execute(
                        'SELECT * FROM imported_record_identities WHERE declared_record_key=?',
                        (key,),
                    ).fetchone()
                if existing is None and target_receipt_id:
                    existing = self.db.execute(
                        'SELECT * FROM imported_record_identities WHERE receipt_id=? AND id_local=?',
                        (target_receipt_id, rec['id_local']),
                    ).fetchone()
                if existing:
                    if existing['claim_sha256'] != rec['claim_sha256']:
                        rec['archive_status'] = 'FORMULATION_DIVERGENCE'
                    elif existing['content_sha256'] != rec['content_sha256']:
                        rec['archive_status'] = 'CONTEXT_DIVERGENCE'
                    else:
                        rec['archive_status'] = 'ALREADY_CONFIRMED'
                    rec['existing_insight_id'] = existing['insight_id']
                    rec['existing_claim_sha256'] = existing['claim_sha256']
                    rec['recognition_kind'] = existing['recognition_kind']
                elif legacy_rows:
                    rec['archive_status'] = 'LEGACY_MATCH_CANDIDATE'
                    rec['legacy_matches'] = [
                        {
                            'insight_id': row['id'],
                            'title': row['title'],
                            'claim_matches': row['claim'] == rec['claim'],
                        }
                        for row in legacy_rows
                    ]
                else:
                    rec['archive_status'] = 'NEW_CANDIDATE'
        return {
            'is_parametrized': True,
            'hash_coverage': {
                'claim_sha256': 'Cobre exclusivamente o texto da formulação (claim).',
                'content_sha256': (
                    'Cobre kind, work_state, title, claim, why_matters, limitations, genesis, '
                    'context, evidence, open_questions, formulation_origin, attribution, '
                    'declared_relations e supersedes_id.'
                ),
            },
            **parsed,
        }

    def confirm_parametrized_record(self, data):
        """Confirma registro diretamente a partir da interpretação autoritativa no servidor."""
        from .parametrized import ParametrizedError, parse_parametrized_markdown

        if not isinstance(data, dict):
            raise ValueError('Esperado objeto JSON')
        receipt_id = required_string(data.get('receipt_id'), 'receipt_id', 64)
        id_local = required_string(data.get('id_local'), 'id_local', 120)
        actor = required_string(data.get('confirmed_by_declared'), 'confirmed_by_declared', 240)
        if data.get('confirmed') is not True:
            raise ValueError('Confirmação humana explícita obrigatória')
        request_id = required_string(data.get('request_id'), 'request_id', 128)

        with self.archive.lock:
            receipt = self.archive._one('SELECT * FROM document_receipts WHERE id=?', (receipt_id,))
            if receipt['outcome'] == 'VERSION_CONFLICT':
                raise Conflict('Recebimento em conflito não pode fundamentar confirmação antes de resolução')
            raw_bytes = self.original(receipt_id=receipt_id)

        try:
            parsed = parse_parametrized_markdown(raw_bytes)
        except ParametrizedError as err:
            raise ValueError(f'Documento não é Markdown parametrizado válido: {err}') from None

        rec = next((item for item in parsed['records'] if item['id_local'] == id_local), None)
        if rec is None:
            raise NotFound(f'Registro candidato "{id_local}" não encontrado no documento')

        doc_meta = parsed['document']
        missing = list(rec['context'].get('missing', []))
        for gap in parsed.get('provenance_gaps', []):
            if gap not in missing:
                missing.append(gap)
        stored_context = {
            **rec['context'],
            'missing': missing,
            'external_document_id': doc_meta.get('external_id') or receipt.get('declared_external_id'),
            'document_version': doc_meta.get('version') or receipt.get('declared_version'),
            'source_context': doc_meta.get('source_context'),
            'attribution': rec.get('attribution'),
            'declared_evidence': rec.get('evidence', []),
            'open_questions': rec.get('open_questions', []),
            'pending_declared_relations': rec.get('declared_relations', []),
        }

        anchors = [
            {
                'receipt_id': receipt_id,
                'quote': a['quote'],
                'start_byte': a['start_byte'],
                'end_byte': a['end_byte'],
                'role': a['role'],
            }
            for a in rec['anchors']
        ]
        if not anchors:
            raise ValueError('Registro parametrizado sem âncora literal verificável no corpo')

        return self.create_record({
            'request_id': request_id,
            'title': rec['title'],
            'claim': rec['claim'],
            'why_matters': rec['why_matters'],
            'genesis': rec['genesis'],
            'limitations': rec['limitations'],
            'kind': rec['kind'],
            'work_state': rec['work_state'],
            'formulation_origin': rec['formulation_origin'],
            'confirmed_by_declared': actor,
            'confirmed': True,
            'supersedes_id': rec.get('supersedes_id'),
            'declared_record_key': rec.get('external_record_id'),
            'id_local': id_local,
            'occurrence_receipt_id': receipt_id,
            'content_sha256': rec['content_sha256'],
            'context': stored_context,
            'anchors': anchors,
        })

    def link_legacy_record(self, data):
        """Vincula explicitamente um candidato parametrizado a um insight legado já existente."""
        from .parametrized import ParametrizedError, compute_content_sha256, parse_parametrized_markdown

        if not isinstance(data, dict):
            raise ValueError('Esperado objeto JSON')
        receipt_id = required_string(data.get('receipt_id'), 'receipt_id', 64)
        id_local = required_string(data.get('id_local'), 'id_local', 120)
        insight_id = required_string(data.get('insight_id'), 'insight_id', 64)
        actor = required_string(data.get('confirmed_by_declared'), 'confirmed_by_declared', 240)
        rationale = optional_text(data.get('rationale'), 'rationale', 2000) or 'Reconhecimento explícito de identidade com registro legado existente'
        if data.get('confirmed') is not True:
            raise ValueError('Confirmação humana explícita obrigatória')

        with self.archive.transaction():
            request_id, signature, retry = self._retry(data, 'link_legacy_record')
            if retry is not None:
                return retry
            receipt = self.archive._one('SELECT * FROM document_receipts WHERE id=?', (receipt_id,))
            if receipt['outcome'] == 'VERSION_CONFLICT':
                raise Conflict('Recebimento em conflito não pode vincular identidade')
            raw_bytes = self.original(receipt_id=receipt_id)
            try:
                parsed = parse_parametrized_markdown(raw_bytes)
            except ParametrizedError as err:
                raise ValueError(f'Documento inválido: {err}') from None

            rec = next((item for item in parsed['records'] if item['id_local'] == id_local), None)
            if rec is None:
                raise NotFound(f'Registro candidato "{id_local}" não encontrado')
            key = rec.get('external_record_id')
            if not key:
                raise ValueError('Candidato sem identidade declarada (external_record_id)')
            if self.db.execute('SELECT 1 FROM imported_record_identities WHERE declared_record_key=?', (key,)).fetchone():
                raise Conflict(f'Identidade declarada "{key}" já vinculada')

            insight = self.archive._get(insight_id)
            elab = self.db.execute('SELECT * FROM record_elaborations WHERE insight_id=?', (insight_id,)).fetchone()
            ext_doc_id = parsed['document'].get('external_id')
            if ext_doc_id and insight['context'].get('external_document_id') != ext_doc_id:
                raise Conflict('Insight legado não pertence ao mesmo external_document_id declarado')

            now = stamp()
            legacy_claim_sha = hashlib.sha256(insight['claim'].encode('utf-8')).hexdigest()
            legacy_ctx = {
                k: v for k, v in insight['context'].items()
                if k in ('scope', 'external_references', 'missing')
            }
            legacy_content_sha = compute_content_sha256(
                kind=elab['kind'] if elab else insight['context'].get('record_kind'),
                work_state=elab['work_state'] if elab else insight['status'],
                title=insight['title'],
                claim=insight['claim'],
                why_matters=insight['context'].get('why_matters', ''),
                limitations=insight['limitations'],
                genesis=insight['genesis'],
                context=legacy_ctx,
                evidence=insight['context'].get('declared_evidence', []),
                open_questions=insight['context'].get('open_questions', []),
                formulation_origin=elab['formulation_origin'] if elab else None,
                attribution=insight['context'].get('attribution'),
                declared_relations=insight['context'].get('pending_declared_relations', []),
                supersedes_id=elab['supersedes_id'] if elab else None,
            )
            self.db.execute(
                'INSERT INTO imported_record_identities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    key,
                    key,
                    receipt_id,
                    id_local,
                    insight_id,
                    ext_doc_id,
                    parsed['document'].get('version'),
                    legacy_claim_sha,
                    legacy_content_sha,
                    'LEGACY_IDENTITY_LINKED',
                    actor,
                    rationale,
                    now,
                ),
            )
            return self._remember(request_id, signature, {
                'linked': True,
                'recognition_kind': 'LEGACY_IDENTITY_LINKED',
                'declared_record_key': key,
                'insight_id': insight_id,
                'receipt_id': receipt_id,
                'confirmed_by_declared': actor,
                'rationale': rationale,
                'claim_matches': insight['claim'] == rec['claim'],
                'content_matches': legacy_content_sha == rec['content_sha256'],
                'linked_at': now,
            })
