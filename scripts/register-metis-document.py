"""Registra o original MÉTIS e dois trechos documentais, por API local autenticada.

Operação explícita e idempotente. Não altera o registro legado nem usa extração por IA.
"""
import base64
import json
from pathlib import Path
import uuid
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/reference/METIS-ACH-20261123-001_v0.1.0.md'


def request_id(label):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'bb-core:document-layer:METIS-ACH-20261123-001:0.1.0:' + label))


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
        'provenance': 'Documento fornecido pelo usuário em Downloads e preservado no repositório. Registro legado: c957bd2e55254bd8ac2eb8f35ea3e2ff. Conversa original e repositório científico citado não fornecidos.',
        'received_by': actor, 'confirmed': True,
    })

    def anchor(quote, role):
        start = body.index(quote.encode())
        return {'receipt_id': receipt['receipt_id'], 'quote': quote, 'start_byte': start,
                'end_byte': start + len(quote.encode()), 'role': role}

    decision = text.split('## Decisão de prioridade\n\n', 1)[1].split('\n## Distinção terminológica', 1)[0].strip()
    question = text.split('## Questão científica preservada\n\n**', 1)[1].split('**', 1)[0]
    common = {
        'formulation_origin': 'DOCUMENT_EXCERPT', 'confirmed_by_declared': actor, 'confirmed': True,
        'genesis': {'origin': 'Trecho do documento sintético fornecido; transcrição da conversa não disponível.'},
        'context': {'external_document_id': 'METIS-ACH-20261123-001', 'document_version': '0.1.0',
                    'legacy_record_id': 'c957bd2e55254bd8ac2eb8f35ea3e2ff',
                    'missing': ['Conversa original', 'Evidências do repositório citado', 'Documento METIS-ESP-MOD-001']},
    }
    decision_record = call('/api/document-records', {
        **common, 'request_id': request_id('decision'), 'title': 'Consolidar a base paramétrica de R',
        'claim': decision, 'kind': 'METHODOLOGICAL_DECISION', 'work_state': 'ADOPTED',
        'why_matters': 'Preservar a prioridade de trabalho declarada, sem confundi-la com validação científica.',
        'limitations': 'Decisão de prioridade relatada no documento. Não demonstra auditoria dos dados, validade empírica de R ou emergência. A adoção é atribuída ao processo descrito no documento.',
        'anchors': [anchor(decision, 'methodological_decision')],
    })
    question_record = call('/api/document-records', {
        **common, 'request_id': request_id('question'), 'title': 'Questão científica da resiliência emergente',
        'claim': question, 'kind': 'OPEN_QUESTION', 'work_state': 'OPEN',
        'why_matters': 'Manter recuperável a pergunta científica cuja investigação foi postergada.',
        'limitations': 'Questão em aberto, sem identificação empírica de emergência. Deve aceitar resultados negativos, inconclusivos e hipóteses alternativas.',
        'anchors': [anchor(question, 'scientific_question'), anchor('A investigação deve aceitar ausência de emergência detectável, resultados inconclusivos, escalas inadequadas e hipóteses alternativas.', 'epistemic_limit')],
    })
    assert call('/api/documents/' + receipt['version_id'] + '/original', raw=True) == body
    for record in (decision_record, question_record):
        context = call('/api/insights/' + record['id'] + '/context')
        assert context['integrity'] == 'VERIFIED_LOCAL_BYTES'
        assert context['elaboration']['work_state'] == record['work_state']
    result = {'document': receipt, 'records': [decision_record, question_record],
              'integrity': 'VERIFIED_LOCAL_BYTES', 'legacy_record_preserved': 'c957bd2e55254bd8ac2eb8f35ea3e2ff'}
    destination = ROOT / 'docs/reference/METIS-ACH-20261123-001.document-receipt.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
