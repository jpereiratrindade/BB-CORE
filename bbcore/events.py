"""BB-EVENT-1: diário append-only; ordem de armazenamento não é influência intelectual."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime

from .store import Conflict, NotFound, digest, required_string, stamp, valid_origin_url

ZERO_HASH = '0' * 64
MODES = {'OBSERVED', 'REPORTED', 'PROPOSED'}
PUBLIC_TYPES = {'OCCURRENCE_RECORDED', 'EVIDENCE_REFERENCED', 'CRITIQUE_RECORDED',
                'INTERPRETATION_PROPOSED', 'FORMULATION_REVISED', 'PROVENANCE_SUPPLEMENTED',
                'RELATION_RECOGNIZED', 'RELATION_CONTESTED'}
INTERNAL_TYPES = {'INSIGHT_REGISTERED', 'REVISION_REFERENCE_RECORDED', 'RELATION_PROPOSED'}
LINK_TYPES = {'RESPONDS_TO', 'MOTIVATED_BY', 'CORRECTS', 'CONTESTS'}


def encoded(value):
    # Contrato local Python JSON: UTF-8, chaves ordenadas, sem NaN/Infinity; não é RFC 8785.
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    return digest(encoded(value))


def occurred(value):
    if value is None:
        return None
    value = required_string(value, 'occurred_at', 64)
    if len(value) == 10:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('Data de acontecimento inválida')
    else:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('Horário do acontecimento exige fuso explícito; use null se desconhecido')
    return value


class Events:
    def __init__(self, archive):
        self.archive, self.db = archive, archive.db
        with archive.lock:
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS intellectual_events (
                seq INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE,
                insight_id TEXT NOT NULL REFERENCES insights(id),
                related_insight_id TEXT REFERENCES insights(id),
                payload TEXT NOT NULL, event_hash TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS intellectual_event_subject ON intellectual_events(insight_id,seq);
            CREATE INDEX IF NOT EXISTS intellectual_event_related ON intellectual_events(related_insight_id,seq);
            CREATE TABLE IF NOT EXISTS event_log_head (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), journal_id TEXT NOT NULL,
                last_seq INTEGER NOT NULL, last_hash TEXT NOT NULL, established_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS intellectual_events_no_update BEFORE UPDATE ON intellectual_events
                BEGIN SELECT RAISE(ABORT,'Eventos são append-only'); END;
            CREATE TRIGGER IF NOT EXISTS intellectual_events_no_delete BEFORE DELETE ON intellectual_events
                BEGIN SELECT RAISE(ABORT,'Eventos são append-only'); END;
            CREATE TRIGGER IF NOT EXISTS event_log_head_no_delete BEFORE DELETE ON event_log_head
                BEGIN SELECT RAISE(ABORT,'Cabeçalho da cadeia não pode ser removido'); END;
            ''')
        with archive.transaction():
            if not self.db.execute('SELECT 1 FROM event_log_head').fetchone():
                if self.db.execute('SELECT 1 FROM intellectual_events LIMIT 1').fetchone():
                    raise Conflict('Diário existente sem cabeçalho; restaure backup, não reinicialize')
                self.db.execute('INSERT INTO event_log_head VALUES(1,?,?,?,?)', (uuid.uuid4().hex, 0, ZERO_HASH, stamp()))

    @contextmanager
    def snapshot(self):
        """Cabeçalho, eventos e referências são lidos na mesma fotografia SQLite."""
        with self.archive.lock:
            nested = self.db.in_transaction
            if not nested:
                self.db.execute('BEGIN')
            try:
                yield
                if not nested:
                    self.db.execute('COMMIT')
            except BaseException:
                if not nested:
                    self.db.execute('ROLLBACK')
                raise

    def _record(self, iid):
        record = self.archive._get(iid)
        row = self.db.execute('SELECT * FROM record_elaborations WHERE insight_id=?', (iid,)).fetchone()
        if row:
            record['elaboration'] = dict(row)
        return record

    def _resolve(self, kind, identifier):
        if kind == 'insight':
            return self._record(identifier)
        if kind == 'source':
            item = self.archive._one('SELECT * FROM sources WHERE id=?', (identifier,))
            body = item.pop('body')
            if digest(body) != item['sha256']:
                raise Conflict('Fonte referenciada com hash divergente')
            item['anchors'] = [dict(row) for row in self.db.execute(
                'SELECT * FROM insight_sources WHERE source_id=? ORDER BY insight_id,start_byte,end_byte,role', (identifier,))]
            for anchor in item['anchors']:
                if (not 0 <= anchor['start_byte'] < anchor['end_byte'] <= len(body.encode())
                        or body.encode()[anchor['start_byte']:anchor['end_byte']] != anchor['quote'].encode()):
                    raise Conflict('Âncora da fonte referenciada com bytes divergentes')
            return item
        if kind == 'document_version':
            item = self.archive._one('''SELECT v.*,d.external_id FROM document_versions v
                JOIN documents d ON d.id=v.document_id WHERE v.id=?''', (identifier,))
            self.archive.documents.original(version_id=identifier)
            return item
        if kind == 'receipt':
            item = self.archive._one('SELECT * FROM document_receipts WHERE id=?', (identifier,))
            self.archive.documents.original(receipt_id=identifier)
            return item
        if kind == 'anchor':
            item = self.archive._one('SELECT * FROM document_anchors WHERE id=?', (identifier,))
            for source in self.archive.documents.sources_for(item['insight_id']):
                if source['id'] == identifier:
                    return {**item, 'document_sha256': source['sha256'],
                            'version': self._resolve('document_version', item['version_id']),
                            'receipt': self._resolve('receipt', item['receipt_id'])}
            raise Conflict('Âncora não recuperável')
        if kind == 'relation':
            return self.archive._one('SELECT * FROM relations WHERE id=?', (identifier,))
        if kind == 'event':
            item = self.archive._one('SELECT id,event_hash,seq FROM intellectual_events WHERE id=?', (identifier,))
            return item
        raise ValueError('Tipo de referência desconhecido')

    def references(self, evidence):
        if not isinstance(evidence, list) or len(evidence) > 32:
            raise ValueError('evidence deve ser uma lista de até 32 referências')
        result = []
        for ref in evidence:
            if not isinstance(ref, dict) or set(ref) != {'kind', 'id', 'role'}:
                raise ValueError('Referência exige kind, id e role')
            kind = required_string(ref['kind'], 'evidence.kind', 40)
            identifier = required_string(ref['id'], 'evidence.id', 128)
            role = required_string(ref['role'], 'evidence.role', 100)
            snapshot = self._resolve(kind, identifier)
            result.append({'kind': kind, 'id': identifier, 'role': role,
                           'snapshot': snapshot, 'fingerprint': fingerprint(snapshot)})
        return result

    def _baseline(self, iid, nature):
        record = self._record(iid)
        refs = [{'kind': 'insight', 'id': iid, 'role': 'initial_record'}]
        refs.extend({'kind': 'source', 'id': r['source_id'], 'role': r['role']}
                    for r in self.db.execute('SELECT source_id,role FROM insight_sources WHERE insight_id=?', (iid,)))
        refs.extend({'kind': 'anchor', 'id': r['id'], 'role': r['role']}
                    for r in self.db.execute('SELECT id,role FROM document_anchors WHERE insight_id=?', (iid,)))
        return {'nature': nature, 'record': record, 'evidence': self.references(refs)}

    @staticmethod
    def verify_bundle(bundle, checkpoint=None):
        """Verificação portátil da cadeia exportada; não revalida os arquivos de evidência."""
        try:
            if bundle['schema'] != 'BB-EVENT-1':
                raise Conflict('Esquema de diário desconhecido')
            head, events = bundle['head'], bundle['events']
            previous = ZERO_HASH
            seen = set()
            known_hashes = {}
            baselined = set()
            for index, event in enumerate(events, 1):
                body = {key: value for key, value in event.items() if key != 'event_hash'}
                if (body['schema'] != 'BB-EVENT-1' or type(body['seq']) is not int or body['seq'] != index
                        or body['journal_id'] != head['journal_id'] or body['previous_hash'] != previous
                        or body['id'] in seen or fingerprint(body) != event['event_hash']):
                    raise Conflict('Falha de integridade na cadeia de eventos')
                if body['event_type'] not in PUBLIC_TYPES | INTERNAL_TYPES or body['mode'] not in MODES:
                    raise Conflict('Contrato de evento desconhecido')
                subjects = {body['insight_id']}
                if body['related_insight_id'] is not None:
                    subjects.add(body['related_insight_id'])
                if set(body['baselines']) != subjects - baselined:
                    raise Conflict('Baseline ausente, repetida ou atribuída a outro insight')
                for iid, baseline in body['baselines'].items():
                    if baseline['record']['id'] != iid or baseline['nature'] not in {'CREATION_OBSERVED', 'EXISTING_RECORD_AT_FIRST_EVENT'}:
                        raise Conflict('Identidade da baseline divergente')
                    if not any(ref['kind']=='insight' and ref['id']==iid and ref['snapshot']==baseline['record']
                               for ref in baseline['evidence']):
                        raise Conflict('Baseline não corresponde ao registro referenciado')
                for link in body['prior_events']:
                    if (link['relationship'] not in LINK_TYPES or not link['basis'] or not body['evidence']
                            or known_hashes.get(link['event_id']) != link['event_hash']):
                        raise Conflict('Vínculo com evento anterior não verificável')
                for ref in body['evidence']:
                    if fingerprint(ref['snapshot']) != ref['fingerprint']:
                        raise Conflict('Snapshot de evidência divergente')
                for baseline in body['baselines'].values():
                    for ref in baseline['evidence']:
                        if fingerprint(ref['snapshot']) != ref['fingerprint']:
                            raise Conflict('Snapshot de baseline divergente')
                seen.add(body['id'])
                known_hashes[body['id']] = event['event_hash']
                baselined.update(subjects)
                previous = event['event_hash']
            if type(head['last_seq']) is not int or head['last_seq'] != len(events) or head['last_hash'] != previous:
                raise Conflict('Cabeçalho divergente ou diário truncado')
            if checkpoint is not None:
                seq = checkpoint['last_seq']
                if (checkpoint['schema'] != 'BB-EVENT-1' or type(seq) is not int or seq < 0
                        or checkpoint['journal_id'] != head['journal_id'] or seq > len(events)
                        or checkpoint['last_hash'] != (events[seq-1]['event_hash'] if seq else ZERO_HASH)):
                    raise Conflict('Diário incompatível com o checkpoint de confiança')
            return {'integrity': 'VERIFIED', 'events_checked': len(events), 'head_hash': previous,
                    'checkpoint_checked': checkpoint is not None}
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
            raise Conflict('Estrutura do diário inválida') from error

    def _bundle(self):
        try:
            head = self.archive._one('SELECT * FROM event_log_head WHERE singleton=1', ())
        except NotFound as error:
            raise Conflict('Cabeçalho da cadeia ausente') from error
        events = []
        for row in self.db.execute('SELECT * FROM intellectual_events ORDER BY seq'):
            try:
                body = json.loads(row['payload'])
                if ('event_hash' in body or encoded(body) != row['payload'] or body['seq'] != row['seq'] or body['id'] != row['id']
                        or body['insight_id'] != row['insight_id'] or body['related_insight_id'] != row['related_insight_id']):
                    raise Conflict('Índice ou representação do evento divergente')
                events.append({**body, 'event_hash': row['event_hash']})
            except (ValueError, TypeError, KeyError) as error:
                raise Conflict('Evento ilegível') from error
        return {'schema': 'BB-EVENT-1', 'head': head, 'events': events}

    def _verified(self, check_evidence=True):
        bundle = self._bundle()
        self.verify_bundle(bundle)
        if check_evidence:
            for event in bundle['events']:
                refs = list(event['evidence'])
                for baseline in event['baselines'].values():
                    refs.extend(baseline['evidence'])
                for ref in refs:
                    try:
                        snapshot = self._resolve(ref['kind'], ref['id'])
                    except (NotFound, ValueError, TypeError, AttributeError) as error:
                        raise Conflict('Evidência registrada não está mais disponível') from error
                    if fingerprint(snapshot) != ref['fingerprint']:
                        raise Conflict('Evidência não corresponde ao snapshot preservado no evento')
        return bundle

    def export(self):
        with self.snapshot():
            return self._verified()

    def checkpoint(self):
        with self.snapshot():
            bundle = self._verified()
            return {'schema': 'BB-EVENT-1', **{key: bundle['head'][key] for key in ('journal_id', 'last_seq', 'last_hash')},
                    'exported_at': stamp()}

    def verify(self):
        with self.snapshot():
            try:
                result = self.verify_bundle(self._verified())
                return {'event_integrity': result['integrity'], 'events_checked': result['events_checked']}
            except (Conflict, sqlite3.DatabaseError) as error:
                return {'event_integrity': 'FAILED', 'event_error': str(error)}

    def _append(self, *, insight_id, event_type, mode, content, origin, responsible=None,
                occurred_at=None, evidence=None, prior_events=None, missing=None, limitations,
                related_insight_id=None, request_id=None):
        # Chamador possui BEGIN IMMEDIATE: gravação do evento e do domínio é atômica.
        bundle = self._verified()
        head = bundle['head']
        baselines = {}
        for iid in dict.fromkeys(i for i in (insight_id, related_insight_id) if i):
            self.archive._get(iid)
            if not any(iid in event['baselines'] for event in bundle['events']):
                nature = 'CREATION_OBSERVED' if event_type == 'INSIGHT_REGISTERED' and iid == insight_id else 'EXISTING_RECORD_AT_FIRST_EVENT'
                baselines[iid] = self._baseline(iid, nature)
        now = stamp()
        absent = list(missing or [])
        if occurred_at is None and 'occurred_at' not in absent:
            absent.append('occurred_at')
        if responsible is None and 'responsible' not in absent:
            absent.append('responsible')
        if origin is None and 'origin' not in absent:
            absent.append('origin')
        refs = self.references(evidence or [])
        if not refs and 'event_evidence' not in absent:
            absent.append('event_evidence')
        body = {'schema': 'BB-EVENT-1', 'journal_id': head['journal_id'], 'seq': head['last_seq']+1,
                'id': uuid.uuid4().hex, 'insight_id': insight_id, 'related_insight_id': related_insight_id,
                'event_type': event_type, 'mode': mode, 'occurred_at': occurred_at, 'recorded_at': now,
                'origin': origin, 'responsible': responsible, 'content': content, 'evidence': refs,
                'prior_events': prior_events or [], 'missing': absent, 'limitations': limitations,
                'baselines': baselines, 'previous_hash': head['last_hash'], 'request_id': request_id}
        payload = encoded(body)
        if len(payload.encode()) > 500_000:
            raise ValueError('Evento excede 500000 bytes')
        event_hash = digest(payload)
        self.db.execute('INSERT INTO intellectual_events VALUES(?,?,?,?,?,?)',
                        (body['seq'], body['id'], insight_id, related_insight_id, payload, event_hash))
        self.db.execute('UPDATE event_log_head SET last_seq=?,last_hash=? WHERE singleton=1', (body['seq'], event_hash))
        return {**body, 'event_hash': event_hash}

    def registered(self, iid, request_id):
        return self._append(insight_id=iid, event_type='INSIGHT_REGISTERED', mode='OBSERVED',
                            content={'summary': 'Gravação inicial deste registro observada pelo serviço.'},
                            origin='BB-CORE: gravação transacional local', responsible={'id': 'bb-core:service', 'name': 'BB-CORE'},
                            occurred_at=stamp(), request_id=request_id,
                            evidence=[{'kind': 'insight', 'id': iid, 'role': 'record_written'}],
                            limitations='Observação da gravação, não da gênese intelectual, autoria ou validade científica.')

    def revision_reference(self, old_id, new_id, actor, request_id):
        return self._append(insight_id=old_id, related_insight_id=new_id,
                            event_type='REVISION_REFERENCE_RECORDED', mode='OBSERVED',
                            content={'summary': 'Novo registro vinculado explicitamente como revisão do anterior.', 'new_record_id': new_id},
                            origin='BB-CORE: vínculo solicitado na captura documental',
                            responsible={'id': actor, 'name': actor}, occurred_at=stamp(), request_id=request_id,
                            evidence=[{'kind': 'insight', 'id': new_id, 'role': 'explicit_revision_reference'}],
                            limitations='Vínculo declarado pelo operador. Não demonstra influência causal nem preenche história anterior.')

    def append(self, data):
        if not isinstance(data, dict):
            raise ValueError('Esperado objeto JSON')
        iid = required_string(data.get('insight_id'), 'insight_id', 64)
        nature, mode = data.get('event_type'), data.get('mode')
        if not isinstance(nature, str) or nature not in PUBLIC_TYPES or not isinstance(mode, str) or mode not in MODES:
            raise ValueError('Natureza ou modo do acontecimento inválido')
        if data.get('confirmed') is not True:
            raise ValueError('Confirmação explícita obrigatória')
        content = data.get('content')
        if not isinstance(content, dict) or len(encoded(content).encode()) > 30000:
            raise ValueError('content deve ser objeto JSON de até 30000 bytes')
        required_string(content.get('summary'), 'content.summary', 4000)
        origin = data.get('origin')
        if origin is not None:
            origin = required_string(origin, 'origin', 4000)
        limitations = required_string(data.get('limitations'), 'limitations', 10000)
        moment = occurred(data.get('occurred_at'))
        actor = data.get('responsible')
        if actor is not None:
            if not isinstance(actor, dict) or set(actor) != {'id', 'name'}:
                raise ValueError('responsible exige id e name declarados, ou null')
            actor = {'id': required_string(actor['id'], 'responsible.id', 240),
                     'name': required_string(actor['name'], 'responsible.name', 240)}
        missing = data.get('missing', [])
        if not isinstance(missing, list) or len(missing) > 32:
            raise ValueError('missing deve ser lista de até 32 lacunas')
        missing = [required_string(item, 'missing', 500) for item in missing]
        prior = data.get('prior_events', [])
        if not isinstance(prior, list) or len(prior) > 16:
            raise ValueError('prior_events deve ser lista de até 16 vínculos explícitos')
        if nature == 'INTERPRETATION_PROPOSED' and mode != 'PROPOSED':
            raise ValueError('Interpretação proposta exige modo PROPOSED')
        if nature == 'FORMULATION_REVISED':
            if mode != 'OBSERVED' or actor is None:
                raise ValueError('Registrar revisão exige responsável e modo OBSERVED (ato de formular)')
            changes = content.get('changes')
            if not isinstance(changes, dict) or not changes or not set(changes) <= {'title', 'claim', 'limitations'}:
                raise ValueError('Revisão exige changes com title, claim e/ou limitations')
            for field, value in changes.items():
                required_string(value, 'changes.'+field, {'title': 240, 'claim': 4000, 'limitations': 10000}[field])
        if nature == 'PROVENANCE_SUPPLEMENTED':
            if actor is None or moment is None:
                raise ValueError('Complementação de proveniência exige responsável e data explícitos')
            allowed_keys = {'summary', 'origin_reference', 'origin_kind', 'provenance_gaps'}
            unknown_keys = set(content) - allowed_keys
            if unknown_keys:
                raise ValueError(f'Complementação de proveniência não aceita campos: {", ".join(sorted(unknown_keys))}')
            normalized_content = {
                'summary': required_string(content.get('summary'), 'content.summary', 4000),
                'origin_reference': required_string(content.get('origin_reference'), 'content.origin_reference', 500),
            }
            if content.get('origin_kind') is not None:
                normalized_content['origin_kind'] = required_string(content.get('origin_kind'), 'content.origin_kind', 120)
            if content.get('provenance_gaps') is not None:
                gaps = content.get('provenance_gaps')
                if not isinstance(gaps, list) or len(gaps) > 32:
                    raise ValueError('content.provenance_gaps deve ser lista de até 32 lacunas')
                normalized_content['provenance_gaps'] = [required_string(g, 'content.provenance_gaps', 500) for g in gaps]
            content = normalized_content
        expected_point = data.get('expected_trajectory_point')
        ack_divergence = data.get('acknowledge_divergence') is True
        if expected_point is not None:
            if not isinstance(expected_point, dict):
                raise ValueError('expected_trajectory_point deve ser objeto JSON')
            exp_count = expected_point.get('record_event_count')
            if isinstance(exp_count, bool) or not isinstance(exp_count, int) or exp_count < 0:
                raise ValueError('expected_trajectory_point.record_event_count deve ser inteiro >= 0')
            exp_last_id = expected_point.get('last_record_event_id')
            exp_last_hash = expected_point.get('last_record_event_hash')
            if exp_count == 0 and (exp_last_id is not None or exp_last_hash is not None):
                raise ValueError('expected_trajectory_point com 0 eventos não deve informar last_record_event_id/hash')
            if exp_count > 0:
                required_string(exp_last_id, 'expected_trajectory_point.last_record_event_id', 64)
                required_string(exp_last_hash, 'expected_trajectory_point.last_record_event_hash', 64)
        with self.archive.transaction():
            rid, signature, retry = self.archive.documents._retry(data, 'intellectual_event')
            if retry is not None:
                self._verified()
                return retry
            self.archive._get(iid)
            state_check = 'NOT_PROVIDED'
            if expected_point is not None:
                bundle_now = self._verified()
                rec_events = [e for e in bundle_now['events'] if iid in (e['insight_id'], e['related_insight_id'])]
                cur_count = len(rec_events)
                cur_point = {
                    'record_event_count': cur_count,
                    'last_record_event_id': rec_events[-1]['id'] if rec_events else None,
                    'last_record_event_hash': rec_events[-1]['event_hash'] if rec_events else None,
                }
                exp_count = expected_point['record_event_count']
                exp_id = expected_point.get('last_record_event_id')
                exp_hash = expected_point.get('last_record_event_hash')
                if exp_count == cur_count and exp_id == cur_point['last_record_event_id'] and exp_hash == cur_point['last_record_event_hash']:
                    state_check = 'MATCHED'
                elif exp_count < cur_count and (exp_count == 0 or (
                    rec_events[exp_count - 1]['id'] == exp_id and rec_events[exp_count - 1]['event_hash'] == exp_hash
                )):
                    if not ack_divergence:
                        subsequent = [
                            {
                                'id': e['id'],
                                'seq': e['seq'],
                                'event_type': e['event_type'],
                                'occurred_at': e.get('occurred_at'),
                                'recorded_at': e['recorded_at'],
                                'responsible': e.get('responsible'),
                                'summary': (e.get('content') or {}).get('summary'),
                            }
                            for e in rec_events[exp_count:]
                        ]
                        raise Conflict(
                            'Alterações posteriores no registro desde o ponto de partida recuperado; examine antes de registrar.',
                            details={
                                'status': 'POSTERIOR_CHANGES',
                                'expected_trajectory_point': expected_point,
                                'current_trajectory_point': cur_point,
                                'subsequent_events': subsequent,
                            },
                        )
                    state_check = 'DIVERGENT_ACKNOWLEDGED'
                else:
                    raise Conflict(
                        'Conflito no ponto de trajetória informado (histórico local incompatível); requer exame humano.',
                        details={
                            'status': 'TRAJECTORY_CONFLICT',
                            'expected_trajectory_point': expected_point,
                            'current_trajectory_point': cur_point,
                        },
                    )
            related = None
            refs = data.get('evidence', [])
            resolved = self.references(refs)
            if nature == 'EVIDENCE_REFERENCED' and not resolved:
                raise ValueError('Referência de evidência exige evidence')
            if nature in {'RELATION_RECOGNIZED', 'RELATION_CONTESTED'}:
                if actor is None or moment is None or not resolved:
                    raise ValueError('Reconhecimento/contestação exige sujeito, data e evidências')
                if mode not in {'OBSERVED', 'REPORTED'}:
                    raise ValueError('Reconhecimento/contestação é atribuição observada ou relatada')
                required_string(content.get('scope'), 'content.scope', 4000)
                relation = self.archive._one('SELECT * FROM relations WHERE id=?',
                                            (required_string(content.get('relation_id'), 'content.relation_id', 64),))
                if iid not in (relation['left_id'], relation['right_id']):
                    raise ValueError('Relação não pertence ao insight indicado')
                related = relation['right_id'] if relation['left_id'] == iid else relation['left_id']
                refs = [*refs, {'kind': 'relation', 'id': relation['id'], 'role': 'relation_under_examination'}]
            normalized_prior = []
            for link in prior:
                if not isinstance(link, dict) or link.get('relationship') not in LINK_TYPES:
                    raise ValueError('Vínculo anterior exige relationship explícita')
                event_id = required_string(link.get('event_id'), 'prior_events.event_id', 64)
                previous = self.archive._one('SELECT id,event_hash FROM intellectual_events WHERE id=?', (event_id,))
                basis = required_string(link.get('basis'), 'prior_events.basis', 4000)
                if not resolved:
                    raise ValueError('Vínculo intelectual anterior exige evidência e fundamento declarados')
                normalized_prior.append({'event_id': event_id, 'event_hash': previous['event_hash'],
                                         'relationship': link['relationship'], 'basis': basis})
            event = self._append(insight_id=iid, related_insight_id=related, event_type=nature, mode=mode,
                                 content=content, origin=origin, responsible=actor, occurred_at=moment,
                                 evidence=refs, prior_events=normalized_prior, missing=missing,
                                 limitations=limitations, request_id=rid)
            return self.archive.documents._remember(rid, signature, {**event, 'state_check': state_check})

    def relation_proposed(self, relation_id, actor, origin, evidence, missing, request_id):
        relation = self.archive._one('SELECT * FROM relations WHERE id=?', (relation_id,))
        return self._append(insight_id=relation['left_id'], related_insight_id=relation['right_id'],
                            event_type='RELATION_PROPOSED', mode='PROPOSED',
                            content={'summary': relation['rationale'], 'scope': 'Proposta candidata entre os dois registros',
                                     'counterpoint': relation['counterpoint'], 'relation_id': relation_id},
                            origin=origin, responsible=actor, evidence=evidence,
                            missing=missing, request_id=request_id,
                            limitations='Relação proposta pelo sujeito declarado; sem reconhecimento científico automático.')

    @staticmethod
    def _provenance_projection(record, supplements):
        """Projeta referências de origem sem substituir o contexto inicial nem dar precedência à mais recente."""
        orig_ctx = (record or {}).get('context') or {}
        orig_sc = orig_ctx.get('source_context') if isinstance(orig_ctx.get('source_context'), dict) else {}
        orig_ref = orig_sc.get('origin_reference') or orig_ctx.get('origin_reference')
        orig_url = valid_origin_url(orig_ref)

        by_url = {}
        if orig_url:
            by_url[orig_url] = {
                'url': orig_url,
                'sources': [{
                    'source': 'ORIGINAL_CONTEXT',
                    'origin_kind': orig_sc.get('origin_kind'),
                }],
            }
        for sup in supplements:
            if sup['origin_url']:
                entry = by_url.setdefault(sup['origin_url'], {'url': sup['origin_url'], 'sources': []})
                entry['sources'].append({
                    'source': 'PROVENANCE_SUPPLEMENTED',
                    'event_id': sup['event_id'],
                    'occurred_at': sup['occurred_at'],
                    'recorded_at': sup['recorded_at'],
                    'responsible': sup['responsible'],
                    'origin_kind': sup['origin_kind'],
                    'summary': sup['summary'],
                })

        distinct_urls = list(by_url.values())
        if not distinct_urls:
            origin_status = 'NONE'
            effective_origin_url = None
        elif len(distinct_urls) == 1:
            origin_status = 'SINGLE'
            effective_origin_url = distinct_urls[0]['url']
        else:
            origin_status = 'DIVERGENT'
            effective_origin_url = None

        return {
            'original_origin_reference': orig_ref,
            'original_origin_url': orig_url,
            'origin_status': origin_status,
            'effective_origin_url': effective_origin_url,
            'origin_urls': distinct_urls,
            'supplements': supplements,
            'supplement_count': len(supplements),
        }

    @staticmethod
    def replay_bundle(bundle, insight_id, checkpoint=None):
        verification = Events.verify_bundle(bundle, checkpoint)
        events = [event for event in bundle['events'] if insight_id in (event['insight_id'], event['related_insight_id'])]
        baseline = next((event['baselines'][insight_id] for event in events if insight_id in event['baselines']), None)
        if events and baseline is None:
            raise Conflict('Trajetória sem baseline explícita')
        state = json.loads(encoded(baseline['record'])) if baseline else None
        formulations, relations, supplements = [], [], []
        for event in events:
            if event['event_type'] == 'FORMULATION_REVISED' and event['insight_id'] == insight_id:
                state.update(event['content']['changes'])
                formulations.append({'event_id': event['id'], 'state': json.loads(encoded(state))})
            if event['event_type'] == 'PROVENANCE_SUPPLEMENTED' and event['insight_id'] == insight_id:
                ev_content = event.get('content') or {}
                ev_ref = ev_content.get('origin_reference')
                supplements.append({
                    'event_id': event['id'],
                    'occurred_at': event.get('occurred_at'),
                    'recorded_at': event.get('recorded_at'),
                    'responsible': event.get('responsible'),
                    'mode': event.get('mode'),
                    'summary': ev_content.get('summary'),
                    'origin_reference': ev_ref,
                    'origin_url': valid_origin_url(ev_ref),
                    'origin_kind': ev_content.get('origin_kind'),
                    'provenance_gaps': ev_content.get('provenance_gaps', []),
                    'origin': event.get('origin'),
                    'limitations': event.get('limitations'),
                })
            if event['event_type'].startswith('RELATION_'):
                relations.append(event)
        provenance = Events._provenance_projection(baseline['record'] if baseline else None, supplements)
        trajectory_point = {
            'record_event_count': len(events),
            'last_record_event_id': events[-1]['id'] if events else None,
            'last_record_event_hash': events[-1]['event_hash'] if events else None,
            'formulation_revision_count': len(formulations),
        }
        return {'insight_id': insight_id, 'events': events, 'event_count': len(events), 'baseline': baseline,
                'current_state': state, 'formulations': formulations, 'relation_attributions': relations,
                'formulation_revision_count': len(formulations),
                'trajectory_point': trajectory_point,
                'provenance': provenance,
                'chain_integrity': verification['integrity'], 'evidence_integrity': 'NOT_RECHECKED_OFFLINE',
                'order': 'RECORDING_ORDER_NOT_CAUSAL',
                'limitation': 'Integridade não comprova veracidade, autoria ou influência intelectual.'}

    def trajectory(self, insight_id):
        with self.snapshot():
            bundle = self._verified()
            original = self.archive._get(insight_id)
            result = self.replay_bundle(bundle, insight_id)
            result['evidence_integrity'] = 'VERIFIED_LOCAL_REFERENCES'
            if not result['events']:
                result['current_state'] = original
                result['provenance'] = self._provenance_projection(original, [])
                result['absence_notice'] = 'Nenhum acontecimento registrado neste diário. Não se presume evolução, relação ou ausência de acontecimentos externos.'
            return result
