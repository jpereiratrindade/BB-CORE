'use strict';
function renderTrajectory(container, trajectory) {
    const make = (tag, text, cls) => {
        const element = document.createElement(tag);
        if (text !== undefined) element.textContent = text;
        if (cls) element.className = cls;
        return element;
    };
    const types = {
        INSIGHT_REGISTERED: 'Registro gravado', OCCURRENCE_RECORDED: 'Acontecimento registrado',
        EVIDENCE_REFERENCED: 'Evidência referenciada', CRITIQUE_RECORDED: 'Crítica registrada',
        INTERPRETATION_PROPOSED: 'Interpretação proposta', FORMULATION_REVISED: 'Formulação revista',
        PROVENANCE_SUPPLEMENTED: 'Proveniência complementada',
        REVISION_REFERENCE_RECORDED: 'Revisão vinculada explicitamente',
        RELATION_PROPOSED: 'Relação proposta', RELATION_RECOGNIZED: 'Reconhecimento atribuído',
        RELATION_CONTESTED: 'Relação ou reconhecimento contestado',
    };
    const referenceKinds = {source:'Fonte textual',insight:'Registro intelectual',document_version:'Versão documental',receipt:'Recebimento documental',anchor:'Trecho ancorado',relation:'Relação candidata',event:'Acontecimento'};
    const linkKinds = {RESPONDS_TO:'Resposta declarada',MOTIVATED_BY:'Motivação declarada',CORRECTS:'Correção declarada',CONTESTS:'Contestação declarada'};
    const missingLabels = {occurred_at:'Momento do acontecimento não informado',responsible:'Responsável não informado',event_evidence:'Sem evidência de suporte vinculada',origin:'Origem não informada'};
    const modes = {OBSERVED: 'Observado', REPORTED: 'Relatado', PROPOSED: 'Proposto'};
    const moment = value => {
        if (!value) return 'Não informado';
        if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.split('-').reverse().join('/');
        return new Date(value).toLocaleString('pt-BR') + ' (' + value + ')';
    };
    const entry = (list, label, value) => list.append(make('dt', label), make('dd', value));
    container.append(make('h4', 'Trajetória registrada'));
    if (!trajectory || !trajectory.event_count) {
        container.append(make('p', 'Nenhum acontecimento registrado neste diário. Os dados anteriores permanecem preservados, sem reconstrução retrospectiva. Este insight pode permanecer sem evolução ou relações.', 'trajectory-empty'));
        return;
    }
    const details = make('details', undefined, 'trajectory');
    details.append(make('summary', 'Consultar ' + trajectory.event_count + ' acontecimento(s) registrado(s)'));
    details.append(make('p', 'Ordem de registro no sistema. A sequência e o encadeamento técnico não demonstram influência ou causalidade.', 'muted'));
    if (trajectory.baseline?.nature === 'EXISTING_RECORD_AT_FIRST_EVENT') {
        details.append(make('p', 'O insight já existia quando seu primeiro acontecimento foi registrado. A base preservada nesse momento não reconstrói sua história anterior.', 'trajectory-baseline'));
    }
    if (trajectory.formulation_revision_count) {
        const current = make('section', undefined, 'trajectory-projection');
        current.append(make('h4', 'Formulação corrente segundo os eventos'), make('p', trajectory.current_state.claim));
        current.append(make('p', trajectory.current_state.limitations, 'muted'));
        details.append(current);
    }
    const list = make('ol', undefined, 'event-list');
    for (const event of trajectory.events) {
        const item = make('li', undefined, 'event-item');
        item.append(make('span', modes[event.mode] || event.mode, 'tag'), make('h5', types[event.event_type] || event.event_type));
        item.append(make('p', event.content.summary));
        const metadata = make('dl');
        entry(metadata, 'Acontecimento', moment(event.occurred_at));
        entry(metadata, 'Registrado no sistema', moment(event.recorded_at));
        entry(metadata, 'Responsável declarado', event.responsible ? event.responsible.name + ' · ' + event.responsible.id : 'Não informado');
        entry(metadata, 'Origem declarada', event.origin || 'Não informada');
        if (event.content.scope) entry(metadata, 'Alcance declarado', event.content.scope);
        if (event.content.origin_reference) entry(metadata, 'Referência de origem declarada', event.content.origin_reference);
        if (event.content.origin_kind) entry(metadata, 'Tipo de origem declarado', event.content.origin_kind);
        entry(metadata, 'Limitações', event.limitations);
        if (event.missing.length) entry(metadata, 'Lacunas preservadas', event.missing.map(item=>missingLabels[item]||item).join('\n'));
        item.append(metadata);
        if (event.content.changes) {
            const changes = make('details');
            changes.append(make('summary', 'Conteúdo da revisão'), make('pre', JSON.stringify(event.content.changes, null, 2)));
            item.append(changes);
        }
        if (event.evidence.length) {
            item.append(make('h6', 'Referências de suporte'));
            for (const ref of event.evidence) {
                const row = make('div', (referenceKinds[ref.kind] || ref.kind) + ' · ' + (ref.snapshot.filename || ref.snapshot.title || ref.snapshot.external_id || ref.id) + '\nPapel declarado: ' + ref.role, 'event-reference');
                if (ref.kind === 'document_version' || ref.kind === 'receipt' || ref.kind === 'anchor') {
                    const versionId = ref.kind === 'document_version' ? ref.id : ref.snapshot.version_id;
                    if (versionId && ref.snapshot.outcome !== 'VERSION_CONFLICT') {
                        const button = make('button', 'Consultar documento de suporte', 'button outline');
                        button.type = 'button';
                        button.addEventListener('click', () => {
                            Reader.close({restoreFocus: false});
                            document.dispatchEvent(new CustomEvent('bb-open-document', {detail: versionId}));
                        });
                        row.append(button);
                    }
                }
                const supportId = ref.kind === 'insight' ? ref.id : ref.kind === 'source' ? ref.snapshot.anchors?.[0]?.insight_id : null;
                if (supportId) {
                    const button = make('button', 'Consultar registro de suporte', 'button outline');
                    button.type = 'button';
                    button.addEventListener('click', () => { Reader.close({restoreFocus:false}); BBViews.open('acervo'); show({id:supportId},null); });
                    row.append(button);
                }
                const metadata = make('details');
                metadata.append(make('summary','Identificação da referência'),make('pre',JSON.stringify({kind:ref.kind,id:ref.id,role:ref.role,snapshot:ref.snapshot,fingerprint:ref.fingerprint},null,2)));
                row.append(metadata);
                item.append(row);
            }
        }
        if (event.prior_events.length) {
            item.append(make('h6', 'Vínculos anteriores explicitamente declarados'));
            for (const link of event.prior_events) item.append(make('p', (linkKinds[link.relationship] || link.relationship) + ' · ' + link.event_id + '\nFundamento: ' + link.basis));
        }
        const integrity = make('details');
        integrity.append(make('summary', 'Identidade e integridade do acontecimento'),
            make('pre', 'Evento: ' + event.id + '\nSequência técnica: ' + event.seq + '\nSHA-256: ' + event.event_hash + '\nHash técnico anterior: ' + event.previous_hash + '\nEste encadeamento não é um vínculo intelectual.'));
        item.append(integrity);
        list.append(item);
    }
    details.append(list, make('p', 'Cadeia e referências locais conferidas. Isso não comprova verdade científica ou autenticação dos sujeitos declarados.', 'muted'));
    container.append(details);
    if (trajectory.relation_attributions.length) {
        const relations = make('details', undefined, 'documented-relations');
        relations.append(make('summary', 'Atribuições documentadas sobre relações (' + trajectory.relation_attributions.length + ')'));
        for (const event of trajectory.relation_attributions) {
            relations.append(make('h5', types[event.event_type]), make('p', event.content.summary));
            const metadata = make('dl');
            entry(metadata, 'Sujeito declarado', event.responsible ? event.responsible.name + ' · ' + event.responsible.id : 'Não informado');
            entry(metadata, 'Data do acontecimento', moment(event.occurred_at));
            entry(metadata, 'Alcance', event.content.scope || 'Não informado');
            entry(metadata, 'Relação identificada', event.content.relation_id);
            relations.append(metadata);
        }
        relations.append(make('p', 'Reconhecimento é uma atribuição documentada e contestável; não uma homologação científica pelo BB-CORE.', 'muted'));
        container.append(relations);
    }
}
