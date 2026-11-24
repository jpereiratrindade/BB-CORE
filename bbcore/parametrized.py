"""Interpretador determinístico de Markdown parametrizado (BB-CORE-ESP-ING-001 v0.2.0).

Opera de forma independente do banco operacional: preserva os bytes originais,
carrega YAML Front Matter com PyYAML em modo estrito e extrai seções com
âncoras exatas em bytes UTF-8, sem criar registros automaticamente nem executar
instruções contidas no documento.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date

import yaml

from .documents import KINDS, MAX_DOCUMENT_BYTES

SCHEMA_VERSION = 'BB-CORE-ING-0.2.0'
MAX_FRONTMATTER_BYTES = 64_000
MAX_RECORDS = 32
MAX_YAML_DEPTH = 8
MAX_YAML_NODES = 1_000
VALID_FORMULATION_ORIGINS = {'DOCUMENT_EXCERPT', 'HUMAN_FORMULATION'}

TOP_KEYS = {'schema', 'document', 'records'}
DOC_KEYS = {'external_id', 'version', 'declared_date', 'source_context', 'provenance'}
SOURCE_CONTEXT_KEYS = {'origin_kind', 'origin_reference', 'transcript_included', 'provenance_gaps'}
RECORD_KEYS = {
    'id_local', 'external_record_id', 'kind', 'work_state', 'title',
    'formulation_origin', 'claim_section', 'claim',
    'why_matters_section', 'why_matters',
    'limitations_section', 'limitations',
    'genesis_section', 'genesis',
    'context', 'attribution', 'evidence',
    'open_questions', 'declared_relations', 'supersedes_id',
}
ATTRIBUTION_KEYS = {'declared_author', 'declared_role', 'external_tool', 'ai_assisted', 'verified'}
CONTEXT_KEYS = {'scope', 'external_references', 'missing'}


class ParametrizedError(ValueError):
    """Erro explícito de validação estrutural ou semântica do contrato."""


class _StrictSafeLoader(yaml.SafeLoader):
    """SafeLoader estrito: sem chaves duplicadas, sem aliases e com limites."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ParametrizedError('Aliases/âncoras YAML (&/*) não são permitidos')
        node = super().compose_node(parent, index)
        if getattr(self, 'anchors', None):
            raise ParametrizedError('Aliases/âncoras YAML (&/*) não são permitidos')
        return node


# Desabilita coerção automática de datas para manter strings determinísticas.
_StrictSafeLoader.yaml_implicit_resolvers = {
    first_char: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != 'tag:yaml.org,2002:timestamp'
    ]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ParametrizedError('Chaves YAML devem ser texto')
        if key in mapping:
            raise ParametrizedError(f'Chave YAML duplicada: {key}')
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _check_yaml_node_limits(node, depth=0, counter=None):
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_YAML_NODES:
        raise ParametrizedError(f'Cabeçalho YAML excede limite de {MAX_YAML_NODES} nós')
    if depth > MAX_YAML_DEPTH:
        raise ParametrizedError(f'Cabeçalho YAML excede profundidade máxima de {MAX_YAML_DEPTH} níveis')
    if isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _check_yaml_node_limits(item, depth + 1, counter)
    elif isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            _check_yaml_node_limits(k, depth + 1, counter)
            _check_yaml_node_limits(v, depth + 1, counter)


def _load_strict_yaml(yaml_text: str):
    loader = _StrictSafeLoader(yaml_text)
    try:
        node = loader.get_single_node()
        if node is None:
            raise ParametrizedError('Cabeçalho YAML Front Matter vazio')
        _check_yaml_node_limits(node)
        data = loader.construct_document(node)
        _reject_non_finite(data)
        return data
    except yaml.YAMLError as err:
        raise ParametrizedError(f'YAML Front Matter inválido: {err}') from None
    finally:
        loader.dispose()


def _reject_non_finite(value):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ParametrizedError('Valores numéricos não finitos (NaN/Infinity) não são permitidos')
    if isinstance(value, list):
        for item in value:
            _reject_non_finite(item)
    elif isinstance(value, dict):
        for item in value.values():
            _reject_non_finite(item)


def _reject_unknown_keys(mapping: dict, allowed: set[str], where: str):
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ParametrizedError(f'{where}: campo(s) desconhecido(s): {", ".join(unknown)}')


def _opt_str(value, name: str, limit: int):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > limit:
        raise ParametrizedError(f'{name}: esperado texto não vazio até {limit} bytes')
    return value.strip()


def _req_str(value, name: str, limit: int):
    if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > limit:
        raise ParametrizedError(f'{name}: texto obrigatório (até {limit} bytes)')
    return value.strip()


def _opt_str_list(value, name: str, max_items: int = 32, max_item_bytes: int = 500):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > max_items:
        raise ParametrizedError(f'{name}: esperada lista de até {max_items} itens')
    return [_req_str(item, f'{name}[]', max_item_bytes) for item in value]


def _split_front_matter(raw_bytes: bytes) -> tuple[str, int]:
    """Separa Front Matter YAML e retorna (yaml_text, body_start_byte_offset)."""
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise ParametrizedError('Documento deve ser fornecido em bytes')
    raw_bytes = bytes(raw_bytes)
    if not raw_bytes or len(raw_bytes) > MAX_DOCUMENT_BYTES:
        raise ParametrizedError(f'Documento vazio ou acima de {MAX_DOCUMENT_BYTES} bytes')
    try:
        full_text = raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        raise ParametrizedError('Documento deve ser UTF-8 válido') from None
    if '\x00' in full_text or not full_text.strip('\ufeff \r\n\t'):
        raise ParametrizedError('Documento binário ou vazio')

    offset = 3 if raw_bytes.startswith(b'\xef\xbb\xbf') else 0
    if raw_bytes[offset:offset + 4] == b'---\n':
        fm_start = offset + 4
    elif raw_bytes[offset:offset + 5] == b'---\r\n':
        fm_start = offset + 5
    else:
        raise ParametrizedError('Documento deve iniciar com cabeçalho YAML Front Matter (---)')

    pos = fm_start
    n = len(raw_bytes)
    while pos < n:
        nl = raw_bytes.find(b'\n', pos)
        line_end = nl if nl != -1 else n
        line = raw_bytes[pos:line_end].rstrip(b'\r')
        if line == b'---':
            fm_bytes = raw_bytes[fm_start:pos]
            if len(fm_bytes) > MAX_FRONTMATTER_BYTES:
                raise ParametrizedError(f'Cabeçalho YAML excede {MAX_FRONTMATTER_BYTES} bytes')
            body_start = line_end + 1 if nl != -1 else n
            return fm_bytes.decode('utf-8'), body_start
        if nl == -1:
            break
        pos = nl + 1

    raise ParametrizedError('Fechamento do cabeçalho YAML Front Matter (---) não encontrado')


def _index_sections(raw_bytes: bytes, body_start: int) -> dict[str, list[tuple[int, int]]]:
    """Mapeia cabeçalhos `## Nome` para lista de (start_byte, end_byte) do conteúdo."""
    headings: list[tuple[str, int, int]] = []
    pos = body_start
    n = len(raw_bytes)
    in_fence = False
    fence_char = b''

    while pos < n:
        nl = raw_bytes.find(b'\n', pos)
        line_end = nl if nl != -1 else n
        line_no_cr = raw_bytes[pos:line_end].rstrip(b'\r')
        stripped = line_no_cr.lstrip(b' ')
        if stripped.startswith(b'```') or stripped.startswith(b'~~~'):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_char = marker
            elif fence_char == marker:
                in_fence = False
                fence_char = b''
        elif not in_fence and line_no_cr.startswith(b'## '):
            heading = line_no_cr[3:].decode('utf-8').strip()
            content_after = line_end + 1 if nl != -1 else n
            headings.append((heading, pos, content_after))
        if nl == -1:
            break
        pos = nl + 1

    sections: dict[str, list[tuple[int, int]]] = {}
    for idx, (name, _h_start, content_start) in enumerate(headings):
        raw_end = headings[idx + 1][1] if idx + 1 < len(headings) else n
        # Aparar linhas em branco nas bordas mantendo offsets UTF-8 exatos.
        s = content_start
        while s < raw_end:
            nl = raw_bytes.find(b'\n', s, raw_end)
            le = nl if nl != -1 else raw_end
            if raw_bytes[s:le].strip(b' \t\r'):
                break
            s = le + 1 if nl != -1 else raw_end
        e = raw_end
        while e > s:
            prev_nl = raw_bytes.rfind(b'\n', s, e - 1)
            line_s = prev_nl + 1 if prev_nl != -1 else s
            chunk = raw_bytes[line_s:e].rstrip(b'\r\n')
            if chunk.strip(b' \t'):
                e = line_s + len(chunk)
                break
            e = prev_nl if prev_nl != -1 else s
        sections.setdefault(name, []).append((s, e))
    return sections


def _resolve_section(raw_bytes: bytes, sections: dict, section_name: str, field_name: str, limit: int):
    matches = sections.get(section_name)
    if not matches:
        raise ParametrizedError(f'{field_name}: seção "## {section_name}" não encontrada no corpo Markdown')
    if len(matches) > 1:
        raise ParametrizedError(f'{field_name}: seção "## {section_name}" ambígua ({len(matches)} ocorrências)')
    start_b, end_b = matches[0]
    if end_b <= start_b:
        raise ParametrizedError(f'{field_name}: seção "## {section_name}" está vazia')
    if end_b - start_b > limit:
        raise ParametrizedError(f'{field_name}: seção excede {limit} bytes')
    text = raw_bytes[start_b:end_b].decode('utf-8')
    return text, {'quote': text, 'start_byte': start_b, 'end_byte': end_b}


def _resolve_text_or_section(raw_bytes, sections, rec, field: str, section_field: str, limit: int, *, required: bool, role: str):
    sec_name = rec.get(section_field)
    direct = rec.get(field)
    if sec_name is not None:
        sec_name = _req_str(sec_name, section_field, 240)
        text, anchor = _resolve_section(raw_bytes, sections, sec_name, section_field, limit)
        if direct is not None:
            direct_val = _req_str(direct, field, limit)
            return direct_val, {**anchor, 'role': role}
        return text, {**anchor, 'role': role}
    if direct is not None:
        return _req_str(direct, field, limit), None
    if required:
        raise ParametrizedError(f'Informe {section_field} ou {field}')
    return None, None


def _validate_document_meta(doc: dict) -> dict:
    if not isinstance(doc, dict):
        raise ParametrizedError('document: esperado objeto YAML')
    _reject_unknown_keys(doc, DOC_KEYS, 'document')
    declared_date = doc.get('declared_date')
    if declared_date is not None:
        if not isinstance(declared_date, str) or len(declared_date) != 10:
            raise ParametrizedError('document.declared_date: esperado YYYY-MM-DD ou null')
        try:
            date.fromisoformat(declared_date)
        except ValueError:
            raise ParametrizedError('document.declared_date: data inválida') from None

    sc_raw = doc.get('source_context')
    source_context = None
    if sc_raw is not None:
        if not isinstance(sc_raw, dict):
            raise ParametrizedError('document.source_context: esperado objeto')
        _reject_unknown_keys(sc_raw, SOURCE_CONTEXT_KEYS, 'document.source_context')
        transcript = sc_raw.get('transcript_included')
        if transcript is not None and not isinstance(transcript, bool) and transcript != 'PARTIAL':
            raise ParametrizedError('document.source_context.transcript_included: esperado booleano, "PARTIAL" ou null')
        source_context = {
            'origin_kind': _opt_str(sc_raw.get('origin_kind'), 'source_context.origin_kind', 120),
            'origin_reference': _opt_str(sc_raw.get('origin_reference'), 'source_context.origin_reference', 500),
            'transcript_included': transcript,
            'provenance_gaps': _opt_str_list(sc_raw.get('provenance_gaps'), 'source_context.provenance_gaps'),
        }

    return {
        'external_id': _opt_str(doc.get('external_id'), 'document.external_id', 240),
        'version': _opt_str(doc.get('version'), 'document.version', 120),
        'declared_date': declared_date,
        'provenance': _opt_str(doc.get('provenance'), 'document.provenance', 4_000),
        'source_context': source_context,
    }


def _validate_record(rec: dict, index: int, doc_meta: dict, raw_bytes: bytes, sections: dict, seen_ids: set[str]) -> dict:
    prefix = f'records[{index}]'
    if not isinstance(rec, dict):
        raise ParametrizedError(f'{prefix}: esperado objeto')
    _reject_unknown_keys(rec, RECORD_KEYS, prefix)

    id_local = _req_str(rec.get('id_local'), f'{prefix}.id_local', 120)
    if id_local in seen_ids:
        raise ParametrizedError(f'{prefix}.id_local duplicado no documento: {id_local}')
    seen_ids.add(id_local)

    ext_rec_id = _opt_str(rec.get('external_record_id'), f'{prefix}.external_record_id', 240)
    if ext_rec_id is None and doc_meta['external_id']:
        ext_rec_id = f"{doc_meta['external_id']}:{id_local}"

    kind = rec.get('kind')
    work_state = rec.get('work_state')
    if not isinstance(kind, str) or kind not in KINDS or not isinstance(work_state, str) or work_state not in KINDS[kind]:
        raise ParametrizedError(f'{prefix}: kind e work_state incompatíveis')

    title = _req_str(rec.get('title'), f'{prefix}.title', 240)
    origin = rec.get('formulation_origin')
    if origin not in VALID_FORMULATION_ORIGINS:
        raise ParametrizedError(f'{prefix}.formulation_origin inválido')

    claim, claim_anchor = _resolve_text_or_section(
        raw_bytes, sections, rec, 'claim', 'claim_section', 4_000, required=True, role='primary_claim'
    )
    if origin == 'DOCUMENT_EXCERPT' and claim_anchor is None:
        raise ParametrizedError(f'{prefix}: DOCUMENT_EXCERPT exige claim_section ancorada no corpo')

    why_matters, why_anchor = _resolve_text_or_section(
        raw_bytes, sections, rec, 'why_matters', 'why_matters_section', 4_000, required=True, role='why_matters'
    )
    limitations, lim_anchor = _resolve_text_or_section(
        raw_bytes, sections, rec, 'limitations', 'limitations_section', 10_000, required=True, role='limitations'
    )
    genesis_val, gen_anchor = _resolve_text_or_section(
        raw_bytes, sections, rec, 'genesis', 'genesis_section', 10_000, required=False, role='genesis'
    )

    anchors = [a for a in (claim_anchor, gen_anchor, why_anchor, lim_anchor) if a is not None]

    attr_raw = rec.get('attribution')
    attribution = None
    if attr_raw is not None:
        if not isinstance(attr_raw, dict):
            raise ParametrizedError(f'{prefix}.attribution: esperado objeto')
        _reject_unknown_keys(attr_raw, ATTRIBUTION_KEYS, f'{prefix}.attribution')
        verified = attr_raw.get('verified', False)
        ai_assisted = attr_raw.get('ai_assisted', False)
        if not isinstance(verified, bool) or not isinstance(ai_assisted, bool):
            raise ParametrizedError(f'{prefix}.attribution: verified e ai_assisted devem ser booleanos')
        attribution = {
            'declared_author': _opt_str(attr_raw.get('declared_author'), 'attribution.declared_author', 240),
            'declared_role': _opt_str(attr_raw.get('declared_role'), 'attribution.declared_role', 240),
            'external_tool': _opt_str(attr_raw.get('external_tool'), 'attribution.external_tool', 240),
            'ai_assisted': ai_assisted,
            'verified': verified,
        }

    ctx_raw = rec.get('context')
    context = {}
    if ctx_raw is not None:
        if not isinstance(ctx_raw, dict):
            raise ParametrizedError(f'{prefix}.context: esperado objeto')
        _reject_unknown_keys(ctx_raw, CONTEXT_KEYS, f'{prefix}.context')
        if ctx_raw.get('scope') is not None:
            context['scope'] = _req_str(ctx_raw['scope'], f'{prefix}.context.scope', 1_000)
        if ctx_raw.get('external_references') is not None:
            context['external_references'] = _opt_str_list(ctx_raw['external_references'], f'{prefix}.context.external_references')
        if ctx_raw.get('missing') is not None:
            context['missing'] = _opt_str_list(ctx_raw['missing'], f'{prefix}.context.missing')

    evidence = rec.get('evidence', [])
    if not isinstance(evidence, list) or len(evidence) > 32:
        raise ParametrizedError(f'{prefix}.evidence: esperada lista de até 32 itens')
    declared_relations = rec.get('declared_relations', [])
    if not isinstance(declared_relations, list) or len(declared_relations) > 32:
        raise ParametrizedError(f'{prefix}.declared_relations: esperada lista de até 32 itens')

    genesis_obj = {'summary': genesis_val} if genesis_val is not None else {}
    open_q = _opt_str_list(rec.get('open_questions'), f'{prefix}.open_questions')
    supersedes_val = _opt_str(rec.get('supersedes_id'), f'{prefix}.supersedes_id', 64)
    claim_sha256 = hashlib.sha256(claim.encode('utf-8')).hexdigest()
    content_sha256 = compute_content_sha256(
        kind=kind, work_state=work_state, title=title, claim=claim,
        why_matters=why_matters, limitations=limitations, genesis=genesis_obj,
        context=context, evidence=evidence, open_questions=open_q,
        formulation_origin=origin, attribution=attribution,
        declared_relations=declared_relations, supersedes_id=supersedes_val,
    )

    return {
        'id_local': id_local,
        'external_record_id': ext_rec_id,
        'kind': kind,
        'work_state': work_state,
        'title': title,
        'formulation_origin': origin,
        'claim': claim,
        'claim_sha256': claim_sha256,
        'content_sha256': content_sha256,
        'why_matters': why_matters,
        'limitations': limitations,
        'genesis': genesis_obj,
        'attribution': attribution,
        'context': context,
        'evidence': evidence,
        'open_questions': open_q,
        'declared_relations': declared_relations,
        'supersedes_id': supersedes_val,
        'anchors': anchors,
    }


def compute_content_sha256(
    *,
    kind,
    work_state,
    title,
    claim,
    why_matters,
    limitations,
    genesis,
    context,
    evidence,
    open_questions,
    formulation_origin,
    attribution,
    declared_relations,
    supersedes_id,
) -> str:
    """Hash canônico integral dos elementos intelectuais e contextuais do registro."""
    payload = {
        'kind': kind,
        'work_state': work_state,
        'title': title,
        'claim': claim,
        'why_matters': why_matters,
        'limitations': limitations,
        'genesis': genesis or {},
        'context': context or {},
        'evidence': evidence or [],
        'open_questions': open_questions or [],
        'formulation_origin': formulation_origin,
        'attribution': attribution,
        'declared_relations': declared_relations or [],
        'supersedes_id': supersedes_id,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    ).hexdigest()


def parse_parametrized_markdown(raw_bytes: bytes) -> dict:
    """Interpreta deterministicamente um Markdown parametrizado (BB-CORE-ING-0.2.0)."""
    yaml_text, body_start = _split_front_matter(raw_bytes)
    header = _load_strict_yaml(yaml_text)
    if not isinstance(header, dict):
        raise ParametrizedError('Cabeçalho YAML deve ser um mapeamento')
    if 'export_schema' in header or header.get('document_role') == 'EXPORTED_RECORD':
        raise ParametrizedError(
            'Documento de exportação (BB-CORE-EXP) não pode ser reimportado como novo registro de ingestão'
        )
    _reject_unknown_keys(header, TOP_KEYS, 'header')

    schema = header.get('schema')
    if schema != SCHEMA_VERSION:
        raise ParametrizedError(f'Versão de schema incompatível: esperado {SCHEMA_VERSION}, recebido {schema!r}')
    if 'document' not in header or 'records' not in header:
        raise ParametrizedError('Cabeçalho exige os blocos "document" e "records"')

    doc_meta = _validate_document_meta(header['document'])
    raw_records = header['records']
    if not isinstance(raw_records, list) or len(raw_records) > MAX_RECORDS:
        raise ParametrizedError(f'records: esperada lista de 0 a {MAX_RECORDS} itens')

    sections = _index_sections(raw_bytes, body_start)
    seen_ids: set[str] = set()
    records = [
        _validate_record(rec, idx, doc_meta, raw_bytes, sections, seen_ids)
        for idx, rec in enumerate(raw_records)
    ]

    gaps = list(doc_meta['source_context']['provenance_gaps']) if doc_meta['source_context'] else []
    if not doc_meta['provenance']:
        gaps.append('Procedência do documento não declarada no cabeçalho; deverá ser informada no recebimento.')

    return {
        'schema': SCHEMA_VERSION,
        'state': 'INTERPRETED',
        'sha256': hashlib.sha256(raw_bytes).hexdigest(),
        'byte_length': len(raw_bytes),
        'document': doc_meta,
        'records': records,
        'provenance_gaps': gaps,
        'epistemic_notice': (
            'Interpretação estrutural determinística. Nenhum registro foi gravado; '
            'integridade dos bytes não comprova fidelidade a conversas externas, autoria ou validade científica.'
        ),
    }
