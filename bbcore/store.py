"""Núcleo persistente: SQLite, FTS5, fontes literais e versões imutáveis."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

MAX_SOURCE_BYTES = 256_000
MAX_SOURCES = 16
MAX_TEXT = 20_000
VALID_SHARING = {"PRIVATE", "SCOPED"}
VALID_STATUS = {"INFERRED_CANDIDATE", "REPORTED", "DISPUTED", "WITHDRAWN"}


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def required_string(value, name, length=MAX_TEXT, *, preserve=False):
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > length:
        raise ValueError(f"{name}: texto obrigatório (limite de {length} bytes)")
    return value if preserve else value.strip()


def object_field(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name}: esperado objeto JSON")
    if len(canonical(value).encode("utf-8")) > 30_000:
        raise ValueError(f"{name}: acima de 30000 bytes")
    return value


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class Archive:
    def __init__(self, path):
        path = Path(path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA secure_delete=ON")
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY, body TEXT NOT NULL, sha256 TEXT NOT NULL,
                origin TEXT NOT NULL, author TEXT, coverage TEXT NOT NULL,
                recorded_at TEXT NOT NULL, sharing TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS insights (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, claim TEXT NOT NULL,
                status TEXT NOT NULL, genesis TEXT NOT NULL, limitations TEXT NOT NULL,
                context TEXT NOT NULL, sharing TEXT NOT NULL,
                created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS insight_sources (
                insight_id TEXT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES sources(id),
                quote TEXT NOT NULL, start_byte INTEGER NOT NULL, end_byte INTEGER NOT NULL,
                role TEXT NOT NULL, PRIMARY KEY (insight_id,source_id,start_byte,end_byte,role)
            );
            CREATE TABLE IF NOT EXISTS revisions (
                id TEXT PRIMARY KEY, insight_id TEXT NOT NULL REFERENCES insights(id),
                version INTEGER NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL,
                at TEXT NOT NULL, UNIQUE(insight_id,version)
            );
            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY, left_id TEXT NOT NULL REFERENCES insights(id),
                right_id TEXT NOT NULL REFERENCES insights(id),
                rationale TEXT NOT NULL, counterpoint TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL,
                CHECK (left_id != right_id)
            );
            CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY, signature TEXT NOT NULL, response TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS insights_fts USING fts5(
                insight_id UNINDEXED, title, claim, tokenize='unicode61 remove_diacritics 2'
            );
            ''')

        from .documents import Documents
        self.documents = Documents(self)
        from .events import Events
        self.events = Events(self)
        from .elaborations import Elaborations
        self.elaborations = Elaborations(self)

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def _one(self, sql, args):
        row = self.db.execute(sql, args).fetchone()
        if row is None:
            raise NotFound("Registro não encontrado")
        return dict(row)

    def capture(self, data):
        if not isinstance(data, dict):
            raise ValueError("Esperado objeto JSON")
        rid = required_string(data.get("request_id"), "request_id", 128)
        # UUID é obrigatório para impedir chaves idempotentes ambíguas.
        try:
            uuid.UUID(rid)
        except (ValueError, AttributeError):
            raise ValueError("request_id deve ser UUID") from None
        title = required_string(data.get("title"), "title", 240)
        claim = required_string(data.get("claim"), "claim", 4000)
        rationale = required_string(data.get("why_matters"), "why_matters", 4000)
        genesis = object_field(data.get("genesis"), "genesis")
        context = object_field(data.get("context"), "context")
        limitations = required_string(data.get("limitations"), "limitations", 10000)
        status = data.get("status", "INFERRED_CANDIDATE")
        sharing = data.get("sharing", "PRIVATE")
        if status not in VALID_STATUS or sharing not in VALID_SHARING:
            raise ValueError("Estado ou compartilhamento inválido")
        excerpts = data.get("sources", [])
        if not isinstance(excerpts, list) or not 1 <= len(excerpts) <= MAX_SOURCES:
            raise ValueError(f"sources: de 1 a {MAX_SOURCES} excertos obrigatórios")
        normalized = []
        for index, item in enumerate(excerpts):
            if not isinstance(item, dict):
                raise ValueError("Fonte deve ser objeto")
            body = required_string(item.get("text"), f"sources[{index}].text", MAX_SOURCE_BYTES, preserve=True)
            origin = required_string(item.get("origin"), "origin", 500)
            coverage = item.get("coverage")
            if coverage not in {"LITERAL_EXCERPT", "USER_SUPPLIED_FULL", "SECONDARY_REPORT"}:
                raise ValueError("coverage deve indicar a natureza do contexto")
            quote = required_string(item.get("quote"), "quote", 20000, preserve=True)
            encoded = body.encode("utf-8")
            match = quote.encode("utf-8")
            if encoded.count(match) != 1:
                raise ValueError("Citação literal deve ocorrer uma única vez na fonte")
            start = encoded.find(match)
            author = item.get("author")
            if author is not None and (not isinstance(author, str) or len(author) > 300):
                raise ValueError("author inválido")
            normalized.append({"text": body, "origin": origin, "coverage": coverage,
                               "author": author, "quote": quote, "start": start,
                               "end": start + len(match),
                               "role": required_string(item.get("role"), "role", 100)})
        signature = digest(canonical(data))
        with self.transaction():
            existing = self.db.execute("SELECT signature,response FROM requests WHERE request_id=?", (rid,)).fetchone()
            if existing:
                if existing["signature"] != signature:
                    raise Conflict("request_id já utilizado com conteúdo diferente")
                return json.loads(existing["response"])
            iid = uuid.uuid4().hex
            now = stamp()
            self.db.execute("INSERT INTO insights VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (iid, title, claim, status, canonical(genesis), limitations,
                             canonical({**context, "why_matters": rationale}), sharing, now, 1))
            links = []
            for item in normalized:
                # Cada ocorrência mantém sua identidade; hashes iguais não significam fonte independente.
                sid = uuid.uuid4().hex
                sha = digest(item["text"])
                self.db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",
                                (sid, item["text"], sha, item["origin"], item["author"],
                                 item["coverage"], now, sharing))
                self.db.execute("INSERT INTO insight_sources VALUES(?,?,?,?,?,?)",
                                (iid, sid, item["quote"], item["start"], item["end"], item["role"]))
                links.append({"source_id": sid, "sha256": sha, "coverage": item["coverage"],
                              "start_byte": item["start"], "end_byte": item["end"]})
            self.db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?)",
                            (uuid.uuid4().hex, iid, 1, "CAPTURED", canonical({"request_id": rid}), now))
            self.db.execute("INSERT INTO insights_fts(insight_id,title,claim) VALUES(?,?,?)", (iid,title,claim))
            self.events.registered(iid, rid)
            result = {"id": iid, "version": 1, "status": status,
                      "sharing": sharing, "sources": links,
                      "limitation": "Autoria e completude externa não autenticadas; sem homologação científica"}
            self.db.execute("INSERT INTO requests VALUES(?,?,?)", (rid,signature,canonical(result)))
            return result

    def _get(self, iid):
        obj = self._one("SELECT * FROM insights WHERE id=?", (iid,))
        obj["genesis"] = json.loads(obj["genesis"])
        obj["context"] = json.loads(obj["context"])
        return obj

    def get(self, iid):
        with self.lock:
            obj = self._get(iid)
            obj["source_count"] = self.db.execute("SELECT count(*) FROM insight_sources WHERE insight_id=?",(iid,)).fetchone()[0]
            obj["source_count"] += self.db.execute('SELECT count(*) FROM document_anchors WHERE insight_id=?', (iid,)).fetchone()[0]
            elaboration = self.db.execute('SELECT * FROM record_elaborations WHERE insight_id=?', (iid,)).fetchone()
            if elaboration:
                obj['elaboration'] = dict(elaboration)
                obj['revised_by'] = [r['insight_id'] for r in self.db.execute('SELECT insight_id FROM record_elaborations WHERE supersedes_id=?', (iid,))]
            obj["relations"] = [dict(r) for r in self.db.execute(
                "SELECT * FROM relations WHERE left_id=? OR right_id=? ORDER BY created_at DESC", (iid,iid))]
            return obj

    def context(self, iid):
        with self.lock:
            obj = self.get(iid)
            obj["sources"] = []
            for row in self.db.execute('''SELECT s.*,l.quote,l.start_byte,l.end_byte,l.role
                 FROM sources s JOIN insight_sources l ON s.id=l.source_id
                 WHERE l.insight_id=? ORDER BY s.recorded_at,s.id''', (iid,)):
                item = dict(row)
                b = item["body"].encode("utf-8")
                if digest(item["body"]) != item["sha256"] or b[item["start_byte"]:item["end_byte"]] != item["quote"].encode("utf-8"):
                    raise Conflict("Falha de integridade de fonte ou âncora")
                obj["sources"].append(item)
            obj['sources'].extend(self.documents.sources_for(iid))
            obj['trajectory'] = self.events.trajectory(iid)
            obj["history"] = [dict(r) for r in self.db.execute(
                "SELECT version,event,payload,at FROM revisions WHERE insight_id=? ORDER BY version", (iid,))]
            obj["integrity"] = "VERIFIED_LOCAL_BYTES"
            obj["epistemic_warning"] = "Integridade literal não comprova autoria, causalidade ou validade científica"
            return obj

    def search(self, query, limit=20):
        query = required_string(query, "query", 500)
        if not isinstance(limit,int) or not 1 <= limit <= 50:
            raise ValueError("limit inválido")
        # Expressões literais via aspas para evitar operadores inesperados FTS.
        terms = [x.replace('"','') for x in query.split() if x.replace('"','')]
        if not terms:
            return []
        expression = " OR ".join('"' + t + '"' for t in terms[:12])
        with self.lock:
            rows = self.db.execute('''SELECT i.id,i.title,i.claim,i.status,i.sharing,i.created_at,e.kind,e.work_state,
                  bm25(insights_fts) AS relevance FROM insights_fts
                  JOIN insights i ON i.id=insights_fts.insight_id
                  LEFT JOIN record_elaborations e ON e.insight_id=i.id
                  WHERE insights_fts MATCH ? ORDER BY relevance LIMIT ?''', (expression, limit))
            return [dict(r) for r in rows]

    def list(self, limit=30):
        if not isinstance(limit,int) or not 1 <= limit <= 100:
            raise ValueError("limit inválido")
        with self.lock:
            return [dict(r) for r in self.db.execute(
                "SELECT i.id,i.title,i.claim,i.status,i.sharing,i.created_at,e.kind,e.work_state FROM insights i LEFT JOIN record_elaborations e ON e.insight_id=i.id ORDER BY i.created_at DESC,i.rowid DESC LIMIT ?",(limit,))]

    def relate(self, data):
        if not isinstance(data,dict):
            raise ValueError("Esperado objeto JSON")
        rid = required_string(data.get("request_id"), "request_id", 128)
        try: uuid.UUID(rid)
        except ValueError: raise ValueError("request_id deve ser UUID") from None
        left = required_string(data.get("left_id"), "left_id", 64)
        right = required_string(data.get("right_id"), "right_id", 64)
        if left == right:
            raise ValueError("Relação requer dois insights distintos")
        rationale = required_string(data.get("rationale"), "rationale", 10000)
        counterpoint = required_string(data.get("counterpoint"), "counterpoint", 10000)
        signature = digest(canonical(data))
        with self.transaction():
            existing = self.db.execute("SELECT signature,response FROM requests WHERE request_id=?",(rid,)).fetchone()
            if existing:
                if existing["signature"] != signature: raise Conflict("request_id já usado")
                return json.loads(existing["response"])
            actor = data.get('responsible')
            if not isinstance(actor, dict) or set(actor) != {'id', 'name'}:
                raise ValueError('Novas propostas exigem responsible com id e name declarados')
            actor = {key: required_string(actor[key], 'responsible.'+key, 240) for key in ('id', 'name')}
            origin = required_string(data.get('origin'), 'origin', 4000)
            evidence = data.get('evidence', [])
            self.events.references(evidence)
            missing = data.get('missing', [])
            if not isinstance(missing, list) or len(missing) > 32:
                raise ValueError('missing deve ser lista de até 32 lacunas')
            missing = [required_string(item, 'missing', 500) for item in missing]
            self._get(left); self._get(right)
            new_id = uuid.uuid4().hex
            self.db.execute("INSERT INTO relations VALUES(?,?,?,?,?,?,?)",
                            (new_id,left,right,rationale,counterpoint,"INFERRED_CANDIDATE",stamp()))
            self.events.relation_proposed(new_id, actor, origin, evidence, missing, rid)
            result = {"id":new_id,"status":"INFERRED_CANDIDATE", "left_id":left,"right_id":right,
                      "limitation":"Semelhança não comprova causalidade ou influência histórica"}
            self.db.execute("INSERT INTO requests VALUES(?,?,?)",(rid,signature,canonical(result)))
            return result

    def verify(self):
        with self.lock:
            check = self.db.execute("PRAGMA quick_check").fetchone()[0]
            bad = 0
            total = 0
            for r in self.db.execute("SELECT body,sha256 FROM sources"):
                total += 1
                bad += digest(r["body"]) != r["sha256"]
            documents = self.documents.verify()
            events = self.events.verify()
            return {"sqlite":check,"sources_checked":total,"hash_mismatches":bad, **documents, **events,
                    "integrity": "VERIFIED" if check=="ok" and not bad and not documents['document_hash_mismatches'] and not documents['document_anchor_failures'] and events['event_integrity']=='VERIFIED' else "FAILED"}
