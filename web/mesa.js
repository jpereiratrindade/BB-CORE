'use strict';
(() => {
    const el = id => document.getElementById(id);
    const make = (tag, text, cls) => {
        const n = document.createElement(tag);
        if (text !== undefined) n.textContent = text;
        if (cls) n.className = cls;
        return n;
    };
    const states = {PROPOSED:'Proposta', ADOPTED:'Decisão adotada no trabalho', OPEN:'Em aberto', REPORTED:'Relato atribuído'};
    const permitted = {
        CONCEPTUAL_FINDING: ['PROPOSED'],
        METHODOLOGICAL_DECISION: ['PROPOSED', 'ADOPTED'],
        OPEN_QUESTION: ['OPEN'],
        EMPIRICAL_REPORT: ['REPORTED'],
    };

    let activeId = null;
    let excerpts = [];
    let references = [];
    let targetInsightId = null;
    let drafts = [];
    let pendingRecord = null;
    let pendingEvent = null;
    let lastConfirmedRecord = null;
    let lastUpdatedInsightId = null;

    const uuid = () => crypto.randomUUID();

    function requestPayload(data, pending) {
        const fingerprint = JSON.stringify(data);
        return pending && pending.fingerprint === fingerprint
            ? pending
            : {fingerprint, payload: {...data, request_id: uuid()}};
    }

    async function api(path, {method = 'GET', body} = {}) {
        const r = await fetch(path, {
            method,
            credentials: 'same-origin',
            headers: body ? {'Content-Type': 'application/json'} : {},
            body: body ? JSON.stringify(body) : undefined,
        });
        const data = await r.json();
        if (!r.ok) throw Error(data.message || data.error || 'Falha na operação (' + r.status + ')');
        return data;
    }

    function updateStatus(message) {
        const bar = el('mesa-status-bar');
        if (message) {
            bar.textContent = message;
            return;
        }
        bar.textContent = activeId
            ? 'Editando rascunho salvo (' + activeId.slice(0, 8) + '…) · fora do acervo canônico'
            : 'Elaboração em andamento (ainda não salva no SQLite)';
        el('mesa-discard').hidden = !activeId;
    }

    function updateBadge() {
        const badge = el('mesa-badge');
        badge.textContent = String(drafts.length);
        badge.hidden = drafts.length === 0;
    }

    function renderDrafts() {
        const box = el('mesa-drafts');
        box.replaceChildren();
        el('mesa-drafts-notice').textContent = drafts.length
            ? drafts.length + ' rascunho(s) independente(s) do acervo.'
            : 'Nenhum rascunho salvo ainda.';
        updateBadge();
        for (const d of drafts) {
            const btn = make('button', undefined, 'item');
            btn.type = 'button';
            if (d.id === activeId) btn.setAttribute('aria-pressed', 'true');
            const title = d.title.trim() || (d.notes.trim().slice(0, 60) || 'Elaboração sem título');
            btn.append(
                make('span', 'Rascunho', 'tag'),
                make('strong', title),
                make('small', d.excerpts.length + ' trecho(s) · ' + d.references.length + ' referência(s)')
            );
            btn.addEventListener('click', () => loadDraft(d.id));
            box.append(btn);
        }
    }

    function renderExcerpts() {
        const box = el('mesa-excerpts');
        box.replaceChildren();
        if (!excerpts.length) {
            box.append(make('p', 'Nenhum trecho guardado. Abra um documento, selecione um trecho e clique em "Guardar trecho na mesa".', 'muted'));
            return;
        }
        excerpts.forEach((ex, index) => {
            const card = make('div', undefined, 'anchor-card');
            const label = make('label', undefined, 'check');
            const check = make('input');
            check.type = 'checkbox';
            check.checked = ex.selected !== false;
            check.addEventListener('change', () => { ex.selected = check.checked; });
            const meta = make('small', (ex.label || 'Documento') + ' · versão ' + (ex.declared_version || 'Não declarada') + ' · bytes ' + ex.start_byte + '–' + ex.end_byte);
            label.append(check, meta);
            const remove = make('button', 'Remover da mesa', 'button outline');
            remove.type = 'button';
            remove.addEventListener('click', () => {
                excerpts.splice(index, 1);
                renderExcerpts();
            });
            card.append(label, make('p', ex.quote), remove);
            box.append(card);
        });
    }

    function renderReferences() {
        const box = el('mesa-references');
        box.replaceChildren();
        const picker = el('event-target-picker');
        picker.replaceChildren();
        if (!references.length) {
            box.append(make('p', 'Nenhum registro referenciado. Ao ler um achado no acervo, use "Referenciar na mesa".', 'muted'));
            return;
        }
        const hint = make('p', 'Atalho de registros referenciados na Mesa:', 'muted');
        picker.append(hint);
        references.forEach((ref, index) => {
            const card = make('div', undefined, 'anchor-card');
            const label = make('label', undefined, 'check');
            const check = make('input');
            check.type = 'checkbox';
            check.checked = ref.selected !== false;
            check.addEventListener('change', () => { ref.selected = check.checked; });
            label.append(check, make('small', (ref.title || ref.insight_id) + ' (' + ref.insight_id.slice(0, 8) + '…)'));
            const actions = make('div', undefined, 'view-actions');
            const useTarget = make('button', 'Usar como alvo de acontecimento', 'button outline');
            useTarget.type = 'button';
            useTarget.addEventListener('click', () => {
                targetInsightId = ref.insight_id;
                el('event-target-id').value = ref.insight_id;
                el('mesa-confirm-box').open = true;
                document.querySelector('input[name="mesa-confirm-kind"][value="event"]').checked = true;
                toggleConfirmKind();
            });
            const remove = make('button', 'Remover', 'button outline');
            remove.type = 'button';
            remove.addEventListener('click', () => {
                references.splice(index, 1);
                renderReferences();
            });
            actions.append(useTarget, remove);
            card.append(label, actions);
            box.append(card);

            const quick = make('button', 'Alvo: ' + (ref.title || ref.insight_id.slice(0, 12)), 'button outline');
            quick.type = 'button';
            quick.addEventListener('click', () => { el('event-target-id').value = ref.insight_id; });
            picker.append(quick);
        });
    }

    function applyDraft(d) {
        activeId = d ? d.id : null;
        el('mesa-title').value = d ? d.title : '';
        el('mesa-notes').value = d ? d.notes : '';
        el('mesa-why').value = d ? d.why_matters : '';
        el('mesa-genesis').value = d ? d.genesis : '';
        el('mesa-limitations').value = d ? d.limitations : '';
        excerpts = d ? d.excerpts.map(x => ({...x, selected: true})) : [];
        references = d ? d.references.map(x => ({...x, selected: true})) : [];
        targetInsightId = d ? d.target_insight_id : null;
        if (targetInsightId) el('event-target-id').value = targetInsightId;
        el('mesa-notice').textContent = '';
        renderExcerpts();
        renderReferences();
        renderDrafts();
        updateStatus();
    }

    async function refreshDrafts() {
        try {
            const res = await api('/api/elaborations');
            drafts = res.items || [];
            renderDrafts();
        } catch (e) {
            el('mesa-drafts-notice').textContent = e.message;
        }
    }

    async function loadDraft(id) {
        try {
            const d = await api('/api/elaborations/' + encodeURIComponent(id));
            applyDraft(d);
            el('mesa-notice').textContent = 'Rascunho retomado.';
        } catch (e) {
            el('mesa-notice').textContent = e.message;
        }
    }

    el('mesa-new').addEventListener('click', () => {
        applyDraft(null);
        el('mesa-notice').textContent = 'Nova elaboração em andamento.';
    });

    el('mesa-form').addEventListener('submit', async event => {
        event.preventDefault();
        el('mesa-save').disabled = true;
        try {
            const payload = {
                id: activeId,
                title: el('mesa-title').value,
                notes: el('mesa-notes').value,
                why_matters: el('mesa-why').value,
                genesis: el('mesa-genesis').value,
                limitations: el('mesa-limitations').value,
                excerpts: excerpts.map(({selected, ...rest}) => rest),
                references: references.map(({selected, ...rest}) => rest),
                target_insight_id: targetInsightId || el('event-target-id').value.trim() || null,
            };
            const saved = await api('/api/elaborations', {method: 'POST', body: payload});
            activeId = saved.id;
            el('mesa-notice').textContent = 'Rascunho guardado no SQLite (fora do acervo canônico).';
            await refreshDrafts();
            updateStatus();
        } catch (e) {
            el('mesa-notice').textContent = e.message;
        } finally {
            el('mesa-save').disabled = false;
        }
    });

    el('mesa-discard').addEventListener('click', async () => {
        if (!activeId) return;
        el('mesa-discard').disabled = true;
        try {
            await api('/api/elaborations/' + encodeURIComponent(activeId), {method: 'DELETE'});
            applyDraft(null);
            el('mesa-notice').textContent = 'Rascunho descartado.';
            await refreshDrafts();
        } catch (e) {
            el('mesa-notice').textContent = e.message;
        } finally {
            el('mesa-discard').disabled = false;
        }
    });

    function prefillConfirmationFromMesa() {
        const title = el('mesa-title').value.trim();
        const notes = el('mesa-notes').value.trim();
        const why = el('mesa-why').value.trim();
        const genesis = el('mesa-genesis').value.trim();
        const limits = el('mesa-limitations').value.trim();
        if (title && !el('record-title').value) el('record-title').value = title;
        if (notes && !el('record-claim').value) el('record-claim').value = notes;
        if (why && !el('record-why').value) el('record-why').value = why;
        if (genesis && !el('record-genesis').value) el('record-genesis').value = genesis;
        if (limits && !el('record-limitations').value) el('record-limitations').value = limits;
        if (notes && !el('event-summary').value) el('event-summary').value = notes;
        if (limits && !el('event-limitations').value) el('event-limitations').value = limits;
    }

    el('mesa-confirm-box').addEventListener('toggle', () => {
        if (el('mesa-confirm-box').open) prefillConfirmationFromMesa();
    });

    function toggleConfirmKind() {
        const selected = document.querySelector('input[name="mesa-confirm-kind"]:checked').value;
        el('confirm-record-form').hidden = selected !== 'record';
        el('confirm-event-form').hidden = selected !== 'event';
    }
    for (const radio of document.querySelectorAll('input[name="mesa-confirm-kind"]')) {
        radio.addEventListener('change', toggleConfirmKind);
    }

    function updateRecordStates() {
        el('record-state').replaceChildren();
        for (const st of permitted[el('record-kind').value]) {
            const opt = make('option', states[st]);
            opt.value = st;
            el('record-state').append(opt);
        }
    }
    el('record-kind').addEventListener('change', updateRecordStates);
    updateRecordStates();

    function updateEventFields() {
        const kind = el('event-type').value;
        const isRevision = kind === 'FORMULATION_REVISED';
        const isRelation = kind === 'RELATION_RECOGNIZED' || kind === 'RELATION_CONTESTED';
        const isProp = kind === 'INTERPRETATION_PROPOSED';
        el('event-revision-fields').hidden = !isRevision;
        el('event-relation-fields').hidden = !isRelation;
        el('event-mode-wrap').hidden = isRevision || isProp;
        if (isRevision) el('event-mode').value = 'OBSERVED';
        else if (isProp) el('event-mode').value = 'PROPOSED';
        else if (isRelation && el('event-mode').value === 'PROPOSED') el('event-mode').value = 'REPORTED';
    }
    el('event-type').addEventListener('change', updateEventFields);
    updateEventFields();

    el('confirm-record-form').addEventListener('submit', async event => {
        event.preventDefault();
        el('record-submit').disabled = true;
        try {
            const chosenExcerpts = excerpts.filter(x => x.selected !== false);
            if (!chosenExcerpts.length) throw Error('Selecione ao menos um trecho documental na Mesa para fundamentar o novo registro.');
            const data = {
                title: el('record-title').value,
                claim: el('record-claim').value,
                why_matters: el('record-why').value,
                genesis: {elaboration: el('record-genesis').value || null},
                limitations: el('record-limitations').value,
                kind: el('record-kind').value,
                work_state: el('record-state').value,
                formulation_origin: el('record-origin').value,
                confirmed_by_declared: el('record-actor').value,
                confirmed: el('record-confirm').checked,
                supersedes_id: el('record-supersedes').value.trim() || null,
                anchors: chosenExcerpts.map(x => ({
                    receipt_id: x.receipt_id,
                    quote: x.quote,
                    start_byte: x.start_byte,
                    end_byte: x.end_byte,
                    role: x.role || 'documentary_support',
                })),
            };
            pendingRecord = requestPayload(data, pendingRecord);
            const result = await api('/api/document-records', {method: 'POST', body: pendingRecord.payload});
            pendingRecord = null;
            lastConfirmedRecord = result;
            el('record-notice').textContent = 'Novo registro confirmado (' + result.id + '). A elaboração restante foi preservada na Mesa.';
            el('record-confirm').checked = false;
            el('created-record-link').hidden = false;
            if (typeof window.start === 'function') await window.start();
            document.dispatchEvent(new CustomEvent('bb-documents-refresh'));
        } catch (e) {
            el('record-notice').textContent = e.message;
        } finally {
            el('record-submit').disabled = false;
        }
    });

    el('confirm-event-form').addEventListener('submit', async event => {
        event.preventDefault();
        el('event-submit').disabled = true;
        try {
            const kind = el('event-type').value;
            const target = el('event-target-id').value.trim();
            if (!target) throw Error('Informe o ID do registro-alvo existente.');
            const actorName = el('event-actor').value.trim();
            const responsible = actorName ? {id: 'local:' + actorName.toLowerCase().replace(/\s+/g, '-'), name: actorName} : null;
            const evidence = [
                ...excerpts.filter(x => x.selected !== false).map(x => ({kind: 'receipt', id: x.receipt_id, role: x.role || 'documentary_support'})),
                ...references.filter(x => x.selected !== false && x.insight_id !== target).map(x => ({kind: 'insight', id: x.insight_id, role: x.role || 'reference'})),
            ];
            const content = {summary: el('event-summary').value};
            if (kind === 'FORMULATION_REVISED') {
                const changes = {};
                if (el('event-rev-title').value.trim()) changes.title = el('event-rev-title').value.trim();
                if (el('event-rev-claim').value.trim()) changes.claim = el('event-rev-claim').value.trim();
                if (el('event-rev-limitations').value.trim()) changes.limitations = el('event-rev-limitations').value.trim();
                if (!Object.keys(changes).length) throw Error('Informe ao menos um campo alterado na reformulação.');
                content.changes = changes;
            }
            if (kind === 'RELATION_RECOGNIZED' || kind === 'RELATION_CONTESTED') {
                content.relation_id = el('event-relation-id').value.trim();
                content.scope = el('event-relation-scope').value.trim();
            }
            const data = {
                insight_id: target,
                event_type: kind,
                mode: el('event-mode').value,
                occurred_at: el('event-occurred-at').value || null,
                origin: el('event-origin').value.trim() || null,
                responsible,
                content,
                evidence,
                limitations: el('event-limitations').value,
                confirmed: el('event-confirm').checked,
            };
            pendingEvent = requestPayload(data, pendingEvent);
            const result = await api('/api/events', {method: 'POST', body: pendingEvent.payload});
            pendingEvent = null;
            lastUpdatedInsightId = target;
            el('event-notice').textContent = 'Acontecimento registrado na trajetória (' + result.id.slice(0, 12) + '…). A elaboração restante foi preservada na Mesa.';
            el('event-confirm').checked = false;
            el('updated-insight-link').hidden = false;
        } catch (e) {
            el('event-notice').textContent = e.message;
        } finally {
            el('event-submit').disabled = false;
        }
    });

    el('created-record-link').addEventListener('click', async e => {
        e.preventDefault();
        BBViews.open('acervo');
        if (lastConfirmedRecord && typeof window.show === 'function') await window.show(lastConfirmedRecord, e.currentTarget);
    });
    el('updated-insight-link').addEventListener('click', async e => {
        e.preventDefault();
        BBViews.open('acervo');
        if (lastUpdatedInsightId && typeof window.show === 'function') await window.show({id: lastUpdatedInsightId}, e.currentTarget);
    });

    document.addEventListener('bb-mesa-add-excerpt', event => {
        const ex = event.detail;
        if (!excerpts.some(x => x.receipt_id === ex.receipt_id && x.start_byte === ex.start_byte && x.end_byte === ex.end_byte)) {
            excerpts.push({...ex, selected: true});
            renderExcerpts();
        }
        updateStatus();
    });

    document.addEventListener('bb-mesa-add-reference', event => {
        const ref = event.detail;
        if (!references.some(x => x.insight_id === ref.insight_id)) {
            references.push({...ref, selected: true});
            renderReferences();
        }
        updateStatus();
    });

    document.addEventListener('bb-mesa-focus-insight', event => {
        const d = event.detail;
        targetInsightId = d.id;
        if (!references.some(x => x.insight_id === d.id)) {
            references.push({insight_id: d.id, title: d.title, role: 'target', selected: true});
            renderReferences();
        }
        el('event-target-id').value = d.id;
        if (!el('mesa-title').value.trim()) el('mesa-title').value = 'Sobre: ' + d.title;
        el('event-rev-title').value = d.title || '';
        el('event-rev-claim').value = d.claim || '';
        el('event-rev-limitations').value = d.limitations || '';
        updateStatus();
        BBViews.open('elaboracao');
    });

    document.addEventListener('bb-revise-record', event => {
        const d = event.detail;
        if (!d.elaboration) return;
        el('record-kind').value = d.elaboration.kind;
        updateRecordStates();
        el('record-state').value = d.elaboration.work_state;
        el('record-title').value = d.title;
        el('record-claim').value = d.claim;
        el('record-why').value = d.context.why_matters || '';
        el('record-limitations').value = d.limitations;
        el('record-origin').value = 'HUMAN_FORMULATION';
        el('record-supersedes').value = d.id;
        el('record-genesis').value = 'Desdobramento do registro ' + d.id + '.';
        for (const s of (d.sources || [])) {
            if (s.receipt_id && s.version_id && !excerpts.some(x => x.receipt_id === s.receipt_id && x.start_byte === s.start_byte && x.end_byte === s.end_byte)) {
                excerpts.push({
                    receipt_id: s.receipt_id, version_id: s.version_id, label: s.origin,
                    declared_version: '', quote: s.quote, start_byte: s.start_byte, end_byte: s.end_byte,
                    role: s.role, selected: true,
                });
            }
        }
        renderExcerpts();
        el('mesa-confirm-box').open = true;
        document.querySelector('input[name="mesa-confirm-kind"][value="record"]').checked = true;
        toggleConfirmKind();
        BBViews.open('elaboracao');
    });

    document.addEventListener('bb-session-ready', refreshDrafts);
    renderExcerpts();
    renderReferences();
    updateStatus();
})();
