"""Exercita captura e recuperação MÉTIS em acervo temporário, sem rede."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bbcore.store import Archive, Conflict


def payload():
    source = ROOT / 'docs/reference/METIS-ACH-20261123-001_v0.1.0.md'
    text = source.read_bytes().decode('utf-8')
    return {
        'request_id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'bb-core:METIS-ACH-20261123-001:0.1.0')),
        'title': 'Separação entre o indicador paramétrico R e a identificação empírica de resiliência emergente.',
        'claim': text.split('## Formulação consolidada\n\n', 1)[1].split('\n## Decisão de prioridade', 1)[0].strip(),
        'why_matters': 'Preservar a distinção entre grandeza paramétrica e hipótese de emergência, com a decisão metodológica e seus limites.',
        'genesis': {
            'origin': 'Síntese posterior de discussão, conforme declaração no documento fornecido.',
            'conversation_date_declared': '2026-11-23',
            'conversation_id': None,
            'authorship_verified': False,
        },
        'context': {
            'external_id': 'METIS-ACH-20261123-001',
            'document_version': '0.1.0',
            'record_kind': 'conceptual_finding_and_methodological_decision',
            'review_state_declared': 'Proposta para crítica e homologação humana',
            'coverage': 'Documento integral fornecido; conversa original indisponível',
            'related_document': 'METIS-ESP-MOD-001; revisão editorial proposta v0.3.1',
            'desired_destination': 'NOESE',
            'noese_registration_verified': False,
            'missing': ['Transcrição original', 'Repositório referido como evidência', 'Documento relacionado'],
        },
        'limitations': 'Não é achado empírico nem homologação científica. A existência das quatro funções é alegação do documento, não verificada nesta captura. A integridade local não autentica autoria ou conversa. Não há envio ao NOESE.',
        'status': 'INFERRED_CANDIDATE',
        'sharing': 'PRIVATE',
        'sources': [{
            'text': text,
            'quote': 'Este é um **registro sintético posterior da discussão**, não uma transcrição literal nem evidência de implementação adicional.',
            'origin': source.name,
            'coverage': 'USER_SUPPLIED_FULL',
            'role': 'documentary_record',
        }],
    }


def main():
    data = payload()
    with tempfile.TemporaryDirectory(prefix='bb-metis-') as tmp:
        archive = Archive(Path(tmp) / 'archive.sqlite')
        try:
            captured = archive.capture(data)
            assert archive.capture(data) == captured, 'Retry deve ser idempotente'
            recovered = archive.context(captured['id'])
            assert recovered['sources'][0]['body'] == data['sources'][0]['text']
            expected_hash = hashlib.sha256(data['sources'][0]['text'].encode('utf-8')).hexdigest()
            assert recovered['sources'][0]['sha256'] == expected_hash
            assert recovered['context']['external_id'] == data['context']['external_id']
            assert recovered['context']['document_version'] == '0.1.0'
            assert recovered['status'] == 'INFERRED_CANDIDATE'
            assert recovered['integrity'] == 'VERIFIED_LOCAL_BYTES'
            assert any(item['id'] == captured['id'] for item in archive.search('resiliência'))
            changed = {**data, 'limitations': data['limitations'] + ' Alteração de teste.'}
            try:
                archive.capture(changed)
            except Conflict:
                pass
            else:
                raise AssertionError('Conteúdo alterado com mesmo request_id deve gerar conflito')
            print(json.dumps({'result': 'OK', 'checks': ['capture', 'literal_recovery', 'sha256', 'metadata', 'candidate_status', 'search', 'idempotency', 'conflicting_retry'], 'storage': 'temporary; removed after execution'}, ensure_ascii=False))
        finally:
            archive.db.close()


if __name__ == '__main__':
    main()
