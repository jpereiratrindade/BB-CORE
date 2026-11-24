'use strict';
(() => {
const el = id => document.getElementById(id);
const make = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
const kinds = {CONCEPTUAL_FINDING:'Achado conceitual', METHODOLOGICAL_DECISION:'Decisão metodológica', OPEN_QUESTION:'Questão aberta', EMPIRICAL_REPORT:'Relato empírico'};
const states = {PROPOSED:'Proposta', ADOPTED:'Decisão adotada no trabalho', OPEN:'Em aberto', REPORTED:'Relato atribuído'};
const origins = {DOCUMENT_EXCERPT:'Reprodução literal do documento', HUMAN_FORMULATION:'Formulação humana local'};
const outcomes = {PRESERVED:'Original preservado', RECEIVED_AGAIN:'Novo recebimento de conteúdo já preservado', VERSION_CONFLICT:'Conflito de versão — conteúdo divergente preservado para revisão'};
const archiveLabels = {
    NEW_CANDIDATE: 'Novo registro candidato (aguardando confirmação)',
    ALREADY_CONFIRMED: 'Já confirmado no acervo (sem duplicação)',
    FORMULATION_DIVERGENCE: 'Divergência de formulação em relação ao registro confirmado',
    LEGACY_MATCH_CANDIDATE: 'Possível vínculo com registro anterior (pré-identidade declarada)',
};

let bytes = null, selectedDocument = null, pendingDocument = null, receivedVersion = null;
const uuid = () => crypto.randomUUID();
const base64 = buffer => { let s = ''; for (const byte of buffer) s += String.fromCharCode(byte); return btoa(s); };
function requestPayload(data, pending) {
    const fingerprint = JSON.stringify(data);
    return pending && pending.fingerprint === fingerprint ? pending : {fingerprint, payload: {...data, request_id: uuid()}};
}
async function request(path, body) {
    const response = await fetch(path, {
        method: body ? 'POST' : 'GET',
        credentials: 'same-origin',
        headers: body ? {'Content-Type': 'application/json'} : {},
        body: body ? JSON.stringify(body) : undefined,
    });
    const result = await response.json();
    if (!response.ok && result.outcome !== 'VERSION_CONFLICT') throw Error(result.message || result.error || 'Falha na consulta');
    return result;
}

async function preview() {
    const paramBox = el('document-parametrized-preview');
    try {
        if (el('document-file').files.length) {
            const file = el('document-file').files[0];
            if (file.size > 256000) throw Error('O limite é de 256000 bytes.');
            bytes = new Uint8Array(await file.arrayBuffer());
            el('document-filename').value = file.name;
        } else {
            bytes = new TextEncoder().encode(el('document-paste').value);
        }
        if (bytes.length > 256000) throw Error('O limite é de 256000 bytes.');
        const text = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(bytes);
        el('document-preview').textContent = text || 'Selecione um arquivo ou cole um texto.';
        el('document-notice').textContent = bytes.length ? bytes.length + ' bytes preparados. Nenhum documento foi gravado.' : '';
        paramBox.hidden = true;
        paramBox.classList.remove('error');
        if (bytes.length && text.replace(/^\ufeff/, '').startsWith('---')) {
            const inspected = await request('/api/documents/inspect', {content_base64: base64(bytes)});
            paramBox.hidden = false;
            if (inspected.is_parametrized) {
                const doc = inspected.document || {};
                if (doc.external_id && !el('document-external-id').value) el('document-external-id').value = doc.external_id;
                if (doc.version && !el('document-version').value) el('document-version').value = doc.version;
                if (doc.declared_date && !el('document-date').value) el('document-date').value = doc.declared_date;
                if (doc.provenance && !el('document-provenance').value) el('document-provenance').value = doc.provenance;
                paramBox.textContent = 'Markdown parametrizado válido (' + inspected.schema + ') · ' + inspected.records.length + ' registro(s) candidato(s) interpretado(s). Preserve o documento para examinar e confirmar.';
            } else {
                paramBox.classList.add('error');
                paramBox.textContent = 'Cabeçalho YAML parametrizado inválido: ' + inspected.error;
            }
        }
    } catch (error) {
        bytes = null;
        paramBox.hidden = true;
        el('document-preview').textContent = 'Não foi possível preparar este arquivo.';
        el('document-notice').textContent = error.message;
    }
}

el('document-file').addEventListener('change', preview);
el('document-paste').addEventListener('input', preview);
el('document-form').addEventListener('submit', async event => {
    event.preventDefault();
    el('document-submit').disabled = true;
    try {
        await preview();
        if (!bytes || !bytes.length) throw Error('Selecione um arquivo ou cole texto antes de confirmar.');
        const data = {
            filename: el('document-filename').value,
            content_base64: base64(bytes),
            external_id: el('document-external-id').value || null,
            declared_version: el('document-version').value || null,
            declared_date: el('document-date').value || null,
            provenance: el('document-provenance').value,
            received_by: el('document-actor').value,
            confirmed: el('document-confirm').checked,
        };
        pendingDocument = requestPayload(data, pendingDocument);
        const result = await request('/api/documents', pendingDocument.payload);
        el('document-receipt').textContent = JSON.stringify(result, null, 2);
        el('document-notice').textContent = outcomes[result.outcome] + '. Recibo: ' + result.receipt_id;
        el('received-document-link').hidden = false;
        receivedVersion = result.version_id;
        el('document-confirm').checked = false;
        pendingDocument = null;
        await documents();
        await openDocument(result.version_id, {trigger: el('document-submit')});
    } catch (error) {
        el('document-notice').textContent = error.message;
    } finally {
        el('document-submit').disabled = false;
    }
});

async function documents() {
    try {
        el('documents-notice').textContent = 'Consultando documentos…';
        const items = [];
        let offset = 0;
        do {
            const result = await request('/api/documents?offset=' + offset);
            items.push(...result.items);
            offset = result.next_offset;
        } while (offset !== null);
        el('documents-list').replaceChildren();
        for (const item of items) {
            const button = make('button', undefined, 'item');
            button.type = 'button';
            button.append(
                make('span', item.conflict_count ? 'Conflito em revisão' : 'Documento preservado', 'tag'),
                make('strong', item.external_id || item.filename),
                make('small', 'Versão: ' + (item.declared_version || 'Não declarada') + ' · ' + item.receipt_count + ' recebimento(s)')
            );
            button.setAttribute('aria-haspopup', 'dialog');
            button.append(make('span', 'Examinar documento ↗', 'card-action'));
            button.addEventListener('click', () => openDocument(item.id, {trigger: button}));
            el('documents-list').append(button);
        }
        el('documents-notice').textContent = items.length ? items.length + ' versão(ões) documental(is).' : 'Ainda não há documentos nesta camada.';
    } catch (error) {
        el('documents-notice').textContent = error.message;
    }
}

function renderParametrizedSection(box, doc, param, acceptedReceipts) {
    const section = make('div');
    section.append(make('h4', 'Interpretação parametrizada (' + param.schema + ')'));
    if (param.document?.source_context) {
        const sc = param.document.source_context;
        const scBox = make('div', undefined, 'box-muted');
        scBox.append(make('p', 'Origem declarada: ' + (sc.origin_kind || 'Não informada') + (sc.origin_reference ? ' · ' + sc.origin_reference : '') + '\nTranscrição integral incluída: ' + (sc.transcript_included === true ? 'Sim' : sc.transcript_included === 'PARTIAL' ? 'Parcial' : 'Não')));
        if (param.provenance_gaps?.length) {
            scBox.append(make('p', 'Lacunas de proveniência:\n• ' + param.provenance_gaps.join('\n• '), 'muted'));
        }
        section.append(scBox);
    }
    if (!param.records.length) {
        section.append(make('p', 'Este documento não transporta registros candidatos (records: []). Preservado como fonte de contexto.', 'muted'));
        box.append(section);
        return;
    }
    const defaultActor = acceptedReceipts[0]?.received_by || '';
    for (const rec of param.records) {
        const cardCls = 'param-card' + (rec.archive_status === 'ALREADY_CONFIRMED' ? ' confirmed' : (rec.archive_status === 'FORMULATION_DIVERGENCE' || rec.archive_status === 'LEGACY_MATCH_CANDIDATE' ? ' conflict' : ''));
        const card = make('div', undefined, cardCls);
        card.append(
            make('span', (kinds[rec.kind] || rec.kind) + ' · ' + (states[rec.work_state] || rec.work_state), 'tag'),
            make('strong', rec.title),
            make('p', archiveLabels[rec.archive_status] || rec.archive_status, 'muted'),
            make('blockquote', rec.claim),
            make('p', 'Incorporação: ' + (origins[rec.formulation_origin] || rec.formulation_origin) + (rec.attribution?.ai_assisted ? ' · Redigido com assistência de IA (não classificado como formulação humana)' : '')),
            make('p', 'Por que preservar: ' + rec.why_matters),
            make('p', 'Limitações: ' + rec.limitations)
        );
        if (rec.context?.missing?.length) {
            card.append(make('p', 'Lacunas declaradas:\n• ' + rec.context.missing.join('\n• '), 'muted'));
        }
        if (rec.open_questions?.length) {
            card.append(make('p', 'Questões decorrentes:\n• ' + rec.open_questions.join('\n• ')));
        }
        if (rec.anchors?.length) {
            card.append(make('small', rec.anchors.map(a => a.role + ' (bytes ' + a.start_byte + '–' + a.end_byte + ')').join(' · '), 'muted'));
        }

        if (rec.archive_status === 'ALREADY_CONFIRMED' || rec.archive_status === 'FORMULATION_DIVERGENCE') {
            const openBtn = make('button', 'Abrir registro existente no acervo →', 'button outline');
            openBtn.type = 'button';
            openBtn.addEventListener('click', async () => {
                Reader.close({restoreFocus: false});
                BBViews.open('acervo');
                if (typeof window.show === 'function') await window.show({id: rec.existing_insight_id}, openBtn);
            });
            card.append(openBtn);
        } else {
            if (rec.archive_status === 'LEGACY_MATCH_CANDIDATE' && rec.legacy_matches?.length) {
                for (const m of rec.legacy_matches) {
                    const legacyBtn = make('button', 'Examinar registro legado vinculado (' + m.title + ') →', 'button outline');
                    legacyBtn.type = 'button';
                    legacyBtn.addEventListener('click', async () => {
                        Reader.close({restoreFocus: false});
                        BBViews.open('acervo');
                        if (typeof window.show === 'function') await window.show({id: m.insight_id}, legacyBtn);
                    });
                    card.append(legacyBtn);
                }
            }
            if (acceptedReceipts.length) {
                const form = make('form', undefined, 'param-confirm-form');
                const actorInput = make('input');
                actorInput.required = true;
                actorInput.maxLength = 240;
                actorInput.placeholder = 'Nome de quem confirma este registro';
                actorInput.value = defaultActor;
                const actorLabel = make('label', 'Responsável pela confirmação');
                actorLabel.append(actorInput);
                const check = make('input');
                check.type = 'checkbox';
                check.required = true;
                const checkLabel = make('label', undefined, 'check');
                checkLabel.append(check, document.createTextNode('Examinei os parâmetros, fontes e limitações. Confirmo a preservação deste registro (sem validação científica).'));
                const btn = make('button', 'Confirmar este registro no acervo', 'button primary');
                btn.type = 'submit';
                const notice = make('p', '', 'muted');
                let pendingConfirm = null;
                form.addEventListener('submit', async ev => {
                    ev.preventDefault();
                    btn.disabled = true;
                    try {
                        const receiptId = acceptedReceipts[0].id;
                        const payloadData = {
                            title: rec.title,
                            claim: rec.claim,
                            why_matters: rec.why_matters,
                            genesis: rec.genesis || {},
                            limitations: rec.limitations,
                            kind: rec.kind,
                            work_state: rec.work_state,
                            formulation_origin: rec.formulation_origin,
                            confirmed_by_declared: actorInput.value,
                            confirmed: check.checked,
                            supersedes_id: rec.supersedes_id || null,
                            declared_record_key: rec.external_record_id || null,
                            content_sha256: rec.content_sha256,
                            context: {
                                ...(rec.context || {}),
                                external_document_id: param.document?.external_id || null,
                                document_version: param.document?.version || null,
                                attribution: rec.attribution || null,
                                open_questions: rec.open_questions || [],
                            },
                            anchors: rec.anchors.map(a => ({
                                receipt_id: receiptId,
                                quote: a.quote,
                                start_byte: a.start_byte,
                                end_byte: a.end_byte,
                                role: a.role,
                            })),
                        };
                        pendingConfirm = requestPayload(payloadData, pendingConfirm);
                        const created = await request('/api/document-records', pendingConfirm.payload);
                        pendingConfirm = null;
                        notice.textContent = 'Registro confirmado (' + created.id + ').';
                        if (typeof window.start === 'function') await window.start();
                        await openDocument(doc.id, {reveal: false});
                    } catch (err) {
                        notice.textContent = err.message;
                    } finally {
                        btn.disabled = false;
                    }
                });
                form.append(actorLabel, checkLabel, btn, notice);
                card.append(form);
            } else {
                card.append(make('p', 'Confirmação bloqueada: este recebimento está em conflito de versão.', 'muted'));
            }
        }
        section.append(card);
    }
    box.append(section);
}

async function openDocument(id, {reveal = true, trigger} = {}) {
    const ticket = reveal ? Reader.open('document-detail', 'Carregando documento…', trigger) : null;
    if (reveal) el('document-detail').replaceChildren(make('p', 'Recuperando documento…'));
    try {
        const [doc, param] = await Promise.all([
            request('/api/documents/' + encodeURIComponent(id)),
            request('/api/documents/' + encodeURIComponent(id) + '/parametrized'),
        ]);
        if (reveal && !Reader.current(ticket)) return;
        selectedDocument = doc;
        if (reveal) Reader.title(doc.external_id || 'Documento preservado');
        const box = el('document-detail');
        box.replaceChildren(
            make('span', 'Integridade local verificada', 'tag'),
            make('h3', doc.external_id || 'Documento sem identificador declarado'),
            make('p', 'Versão declarada: ' + (doc.declared_version || 'Não informada') + '\nSHA-256: ' + doc.sha256)
        );
        const actions = make('div', undefined, 'document-actions');
        const download = make('a', '↓ Baixar original', 'button outline');
        download.href = '/api/documents/' + doc.id + '/original';
        actions.append(download);
        box.append(actions);

        const accepted = doc.receipts.filter(r => r.outcome !== 'VERSION_CONFLICT');
        if (param.is_parametrized) {
            renderParametrizedSection(box, doc, param, accepted);
        } else if (doc.text.replace(/^\ufeff/, '').startsWith('---')) {
            box.append(make('p', 'Cabeçalho YAML parametrizado inválido: ' + param.error, 'muted'));
        }

        box.append(make('h4', 'Original preservado'));
        const pre = make('pre', doc.text, 'document-text');
        pre.id = 'preserved-document-text';
        box.append(pre);

        box.append(make('h4', 'Registros vinculados'));
        for (const record of doc.records) {
            const button = make('button', record.title + ' · ' + states[record.work_state], 'item');
            button.addEventListener('click', async () => {
                BBViews.open('acervo');
                await show(record, button);
            });
            box.append(button);
        }
        if (!doc.records.length) box.append(make('p', 'Nenhum registro confirmado a partir desta versão.'));

        box.append(make('h4', 'Recebimentos e procedências'));
        for (const r of doc.receipts) {
            const row = make('div', undefined, 'receipt-row');
            row.append(
                make('span', outcomes[r.outcome], 'tag'),
                make('p', r.provenance),
                make('p', 'Responsável declarado: ' + r.received_by + '\nRecebido: ' + r.received_at + '\nData documental declarada: ' + (r.declared_date || 'Não informada') + '\nArquivo: ' + r.filename + '\nSHA-256 recebido: ' + r.sha256)
            );
            const a = make('a', r.outcome === 'VERSION_CONFLICT' ? 'Baixar conteúdo divergente preservado' : 'Baixar bytes deste recebimento');
            a.href = '/api/receipts/' + r.id + '/original';
            row.append(a);
            box.append(row);
        }

        box.append(make('h4', 'Histórico de versões declaradas'));
        for (const version of doc.versions) {
            const button = make('button', (version.declared_version || 'Não declarada') + ' · ' + version.sha256.slice(0, 14), 'item');
            button.addEventListener('click', () => openDocument(version.id));
            box.append(button);
        }
    } catch (error) {
        if (reveal && Reader.current(ticket)) el('document-detail').replaceChildren(make('p', error.message));
        else if (!reveal) el('documents-notice').textContent = error.message;
    }
}

el('documents-refresh').addEventListener('click', documents);
el('received-document-link').addEventListener('click', event => {
    event.preventDefault();
    BBViews.open('documentos');
    if (receivedVersion) openDocument(receivedVersion, {trigger: event.currentTarget});
});
document.addEventListener('bb-session-ready', documents);
document.addEventListener('bb-documents-refresh', documents);
document.addEventListener('bb-open-document', async event => {
    BBViews.open('documentos');
    await openDocument(event.detail);
});
})();
