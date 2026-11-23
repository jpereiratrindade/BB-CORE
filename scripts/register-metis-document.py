"""Registra o original MÉTIS e um único insight, por API local autenticada.

Operação explícita e idempotente. Decisão e questão permanecem no mesmo registro; não usa extração por IA.
"""
import base64
import json
from pathlib import Path
import uuid
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path.home() / 'Downloads/METIS-ACH-20261123-001_v0.1.0.md'


def request_id(label):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'bb-core:single-insight:METIS-ACH-20261123-001:0.1.0:' + label))


def main():
    body = SOURCE.read_bytes()
    text = body.decode('utf-8')
    private_config = Path.home() / '.config/bb-core/secret.env'
    config = dict(line.split('=', 1) for line in private_config.read_text().splitlines() if '=' in line and not line.startswith('#'))
    opener = build_opener(ProxyHandler({}))

    def call(path, data=None, raw=False):
        request = Request('http://127.0.0.1:8789' + path,
                          data=json.dumps(data).encode() if data is not None else None,
                          headers={'Authorization': 'Bearer ' + config['BB_WRITE_TOKEN'], 'Content-Type': 'application/json'})
        with opener.open(request, timeout=10) as response:
            return response.read() if raw else json.load(response)

    actor = 'jpereiratrindade (autorização declarada nesta conversa; operação pelo assistente)'
    receipt = call('/api/documents', {
        'request_id': request_id('receipt'), 'filename': SOURCE.name,
        'content_base64': base64.b64encode(body).decode(), 'external_id': 'METIS-ACH-20261123-001',
        'declared_version': '0.1.0', 'declared_date': '2026-11-23',
        'provenance': 'Documento fornecido pelo usuário em Downloads e preservado no repositório. Conversa original e repositório científico citado não fornecidos.',
        'received_by': actor, 'confirmed': True,
    })

    def anchor(quote, role):
        start = body.index(quote.encode())
        return {'receipt_id': receipt['receipt_id'], 'quote': quote, 'start_byte': start,
                'end_byte': start + len(quote.encode()), 'role': role}

    claim = text.split('## Formulação consolidada\n\n', 1)[1].split('\n## Alcance e limites deste registro', 1)[0].strip()
    record = call('/api/document-records', {
        'request_id': request_id('insight'),
        'title': 'Separação entre o indicador paramétrico R e a identificação empírica de resiliência emergente.',
        'claim': claim, 'kind': 'CONCEPTUAL_FINDING', 'work_state': 'PROPOSED',
        'formulation_origin': 'DOCUMENT_EXCERPT', 'confirmed_by_declared': actor, 'confirmed': True,
        'why_matters': 'Preservar a distinção conceitual, sua decisão metodológica e a questão científica em um único insight autônomo.',
        'limitations': 'Proposta conceitual para crítica; não é achado empírico nem validação científica. A decisão é relatada pelo documento e a emergência permanece em aberto. As afirmações sobre implementação não foram verificadas nesta ingestão. Conversa original, repositório científico citado e METIS-ESP-MOD-001 não foram fornecidos. O registro no BB-CORE não implica registro no NOESE.',
        'genesis': {'origin': 'Documento sintético posterior da discussão, fornecido pelo usuário; não é transcrição literal.'},
        'context': {'external_document_id': 'METIS-ACH-20261123-001', 'document_version': '0.1.0',
                    'missing': ['Conversa original', 'Evidências do repositório citado', 'Documento METIS-ESP-MOD-001']},
        'anchors': [anchor(claim, 'conceptual_finding_with_decision_and_open_question')],
    })
    assert call('/api/documents/' + receipt['version_id'] + '/original', raw=True) == body
    context = call('/api/insights/' + record['id'] + '/context')
    assert context['integrity'] == 'VERIFIED_LOCAL_BYTES'
    assert context['elaboration']['work_state'] == 'PROPOSED'
    result = {'document': receipt, 'records': [record], 'integrity': 'VERIFIED_LOCAL_BYTES'}
    destination = ROOT / 'docs/reference/METIS-ACH-20261123-001.document-receipt.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
