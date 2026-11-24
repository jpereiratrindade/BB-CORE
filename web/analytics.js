'use strict';
(() => {
    const byId = id => document.getElementById(id);
    const SVG_NS = 'http://www.w3.org/2000/svg';

    const state = {
        data: null,
        viewMode: 'discoveries', // 'discoveries' | 'semantic' | 'records' | 'lexical'
        discFilter: 'sustained', // 'sustained' | 'all'
        semField: 'similarity_full',
        selectedDiscoveryId: null,
        selectedInsightId: null,
        selectedDimensionId: null,
        selectedConnectionId: null,
        selectedSemPairIndex: null,
        selectedDate: null,
        showUndated: false,
        calAxis: 'recorded_at',
        calPeriodDays: 365,
        calEventType: '',
        zoom: 1,
        panX: 0,
        panY: 0,
        expanded: false,
    };

    const eventTypeLabels = {
        INSIGHT_REGISTERED: 'Novo registro gravado',
        PROVENANCE_SUPPLEMENTED: 'Proveniência complementada',
        FORMULATION_REVISED: 'Formulação revista',
        CRITIQUE_RECORDED: 'Crítica registrada',
        EVIDENCE_REFERENCED: 'Evidência referenciada',
        INTERPRETATION_PROPOSED: 'Interpretação proposta',
        OCCURRENCE_RECORDED: 'Acontecimento registrado',
        REVISION_REFERENCE_RECORDED: 'Revisão vinculada',
        RELATION_PROPOSED: 'Relação proposta',
        RELATION_RECOGNIZED: 'Relação reconhecida',
        RELATION_CONTESTED: 'Relação contestada',
    };

    const kindLabels = {
        CONCEPTUAL_FINDING: 'Achado conceitual',
        METHODOLOGICAL_DECISION: 'Decisão metodológica',
        OPEN_QUESTION: 'Questão aberta',
        EMPIRICAL_REPORT: 'Relato empírico',
    };

    const verdictLabels = {
        SUSTAINED_CANDIDATE: 'Sustentada (automático)',
        WEAK_OR_REDUNDANT: 'Fraca ou redundante',
        CONTESTED: 'Contestada',
        NOT_EXAMINED: 'Não examinada',
    };

    function el(tag, text, cls) {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        if (cls) node.className = cls;
        return node;
    }

    function svgEl(tag, attrs = {}, text) {
        const node = document.createElementNS(SVG_NS, tag);
        for (const [k, v] of Object.entries(attrs)) {
            node.setAttribute(k, String(v));
        }
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function wrapTitle(title, maxLen = 28) {
        const words = (title || '').split(/\s+/);
        let l1 = '', l2 = '';
        for (const w of words) {
            if ((l1 + ' ' + w).trim().length <= maxLen) {
                l1 = (l1 + ' ' + w).trim();
            } else if ((l2 + ' ' + w).trim().length <= maxLen) {
                l2 = (l2 + ' ' + w).trim();
            } else {
                l2 = l2.slice(0, maxLen - 3) + '…';
                break;
            }
        }
        return [l1, l2];
    }

    function graphPoint(index, total, cx, cy, radius) {
        if (total <= 1) return {x: cx, y: cy};
        const angle = -Math.PI / 2 + (index / (total - 1)) * Math.PI;
        return {x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius};
    }

    function dateKey(iso) {
        if (!iso || typeof iso !== 'string') return null;
        return iso.slice(0, 10);
    }

    function recordMap() {
        const m = new Map();
        for (const a of (state.data?.record_network?.nodes || state.data?.graph?.anchors || [])) {
            m.set(a.id, a);
        }
        return m;
    }

    function allDiscoveries() {
        return state.data?.discoveries_overview?.discoveries || [];
    }

    function visibleDiscoveries() {
        const all = allDiscoveries();
        if (state.discFilter === 'sustained') {
            return all.filter(d => d.confrontation_status === 'SUSTAINED_CANDIDATE');
        }
        return all;
    }

    function findDiscovery(id) {
        return allDiscoveries().find(d => d.discovery_id === id) || null;
    }

    function findConnection(connId) {
        if (!state.data?.record_network) return null;
        const cand = state.data.record_network.candidate_connections.find(c => c.id === connId);
        if (cand) return {...cand, isRegistered: false};
        const reg = state.data.record_network.registered_relations.find(r => r.id === connId);
        if (reg) return {...reg, source_id: reg.left_id, target_id: reg.right_id, isRegistered: true};
        return null;
    }

    function filteredEvents() {
        if (!state.data) return [];
        const af = activeInsightIdsFilter();
        const allowedSet = af ? new Set(af.insightIds) : null;
        return state.data.calendar.events.filter(ev => {
            if (state.calEventType && ev.event_type !== state.calEventType) return false;
            if (allowedSet && !allowedSet.has(ev.insight_id) && !allowedSet.has(ev.related_insight_id)) {
                return false;
            }
            return true;
        });
    }

    function activeInsightIdsFilter() {
        if (!state.data) return null;
        if (state.selectedDiscoveryId) {
            const disc = findDiscovery(state.selectedDiscoveryId);
            if (disc) {
                return {
                    insightIds: disc.supporting_records.map(s => s.record_id),
                    label: 'descoberta "' + disc.title.slice(0, 36) + '"',
                };
            }
        }
        if (state.selectedInsightId) {
            const rec = recordMap().get(state.selectedInsightId);
            return {
                insightIds: [state.selectedInsightId],
                label: 'registro "' + (rec ? rec.title.slice(0, 40) : state.selectedInsightId.slice(0, 8)) + '"',
            };
        }
        if (state.selectedSemPairIndex !== null) {
            const pairs = state.data.discoveries_overview?.semantic_space?.[state.semField] || [];
            const p = pairs[state.selectedSemPairIndex];
            if (p) {
                return {
                    insightIds: [p.a_id, p.b_id],
                    label: 'par semântico (cosseno ' + p.cosine + ')',
                };
            }
        }
        if (state.selectedConnectionId) {
            const conn = findConnection(state.selectedConnectionId);
            if (conn) {
                return {
                    insightIds: [conn.source_id, conn.target_id],
                    label: 'conexão selecionada',
                };
            }
        }
        if (state.selectedDimensionId) {
            const dim = state.data.graph.dimensions.find(d => d.id === state.selectedDimensionId);
            if (dim) {
                return {
                    insightIds: dim.record_ids,
                    label: 'dimensão "' + dim.label + '"',
                };
            }
        }
        if (state.selectedDate) {
            const ids = new Set();
            for (const ev of state.data.calendar.events) {
                if (state.calEventType && ev.event_type !== state.calEventType) continue;
                if (dateKey(ev[state.calAxis]) === state.selectedDate) {
                    ids.add(ev.insight_id);
                    if (ev.related_insight_id) ids.add(ev.related_insight_id);
                }
            }
            return {
                insightIds: [...ids],
                label: 'dia ' + state.selectedDate.split('-').reverse().join('/') + ' (' + state.calAxis + ')',
            };
        }
        return null;
    }

    function syncCrossFilter() {
        const clearBtn = byId('analytics-clear');
        const hasFilter = Boolean(
            state.selectedDiscoveryId || state.selectedInsightId || state.selectedDimensionId
            || state.selectedConnectionId || state.selectedSemPairIndex !== null
            || state.selectedDate || state.calEventType || state.showUndated
        );
        if (clearBtn) clearBtn.hidden = !hasFilter;
        document.dispatchEvent(new CustomEvent('bb-analytics-filter', {detail: activeInsightIdsFilter()}));
        renderDiscoveryCards();
        renderSelectionBox();
        renderActivePerspective();
        renderCalendar();
    }

    function buildDiscoveryDossier(disc) {
        const recById = recordMap();
        const dossier = el('div', undefined, 'disc-dossier');
        const badgeCls = disc.confrontation_status === 'SUSTAINED_CANDIDATE' ? 'sustained' : 'weak';
        dossier.append(el('span', verdictLabels[disc.confrontation_status] || disc.confrontation_status, 'net-badge ' + badgeCls));
        dossier.append(el('span', disc.strategy_label || ('Estratégia ' + disc.strategy), 'net-badge'));
        dossier.append(el('span', 'Objeto analítico (não canônico)', 'net-badge'));
        if (disc.stale) {
            dossier.append(el('span', 'Potencialmente desatualizada', 'net-badge stale'));
            dossier.append(el('p', disc.stale_reasons.join(' · '), 'muted'));
        }
        dossier.append(el('p', disc.epistemic_notice, 'muted'));

        dossier.append(el('h5', 'Formulação'));
        dossier.append(el('p', disc.formulation));

        if (disc.description) {
            dossier.append(el('h5', 'Descrição do que foi percebido'));
            dossier.append(el('p', disc.description));
        }

        dossier.append(el('h5', 'Natureza da abstração'));
        dossier.append(el('p', disc.nature));

        dossier.append(el('h5', 'Contribuição intelectual e justificativa da integração'));
        dossier.append(el('p', disc.integration_justification));

        dossier.append(el('h5', 'Distinção em relação aos registros individuais'));
        dossier.append(el('p', disc.distinction_from_preserved_content));

        dossier.append(el('h5', 'Relevância potencial'));
        dossier.append(el('p', disc.potential_relevance));

        if (disc.confrontation) {
            const cf = disc.confrontation;
            dossier.append(el('h5', 'Confrontação crítica independente (E)'));
            dossier.append(el('p', cf.critique));
            const critDet = el('details');
            critDet.append(el('summary', 'Critérios examinados (7 verificações)'));
            critDet.append(el('pre',
                `Já explícita em único registro: ${cf.already_explicit_in_single_record ? 'Sim' : 'Não'}\n`
                + `Apenas resumo/classificação: ${cf.merely_summary_or_classification ? 'Sim' : 'Não'}\n`
                + `Estrutura transversal fundamentada: ${cf.reveals_grounded_transversal_structure ? 'Sim' : 'Não'}\n`
                + `Depende da integração: ${cf.depends_on_integration ? 'Sim' : 'Não'}\n`
                + `Registros sustentam: ${cf.records_sustain_interpretation ? 'Sim' : 'Não'}\n`
                + `Acrescenta compreensão/investigação: ${cf.adds_comprehension_or_investigation ? 'Sim' : 'Não'}`
            ));
            dossier.append(critDet);
        }

        if (disc.limitations_and_counterarguments?.length) {
            dossier.append(el('h5', 'Alcance, limitações e contra-argumentos'));
            const ul = el('ul');
            for (const l of disc.limitations_and_counterarguments) ul.append(el('li', l));
            dossier.append(ul);
        }

        if (disc.investigation_possibilities?.length) {
            dossier.append(el('h5', 'Possibilidades de investigação'));
            const ul = el('ul');
            for (const inv of disc.investigation_possibilities) ul.append(el('li', inv));
            dossier.append(ul);
        }

        dossier.append(el('h5', `Conhecimentos que a fundamentam (${disc.supporting_records.length} registro(s))`));
        for (const sr of disc.supporting_records) {
            const rc = el('div', undefined, 'disc-rec-card');
            rc.append(el('strong', sr.record_title));
            if (sr.specific_contribution) rc.append(el('p', 'Contribuição específica: ' + sr.specific_contribution));
            for (const ex of sr.excerpts) {
                rc.append(el('div', `${ex.exact_match ? '✓' : '⚠'} "${ex.excerpt}"`, 'net-excerpt' + (ex.exact_match ? '' : ' unverified')));
            }
            const recObj = recById.get(sr.record_id);
            if (recObj) {
                const openBtn = el('button', 'Abrir registro canônico e trajetória ↗', 'button outline');
                openBtn.type = 'button';
                openBtn.addEventListener('click', () => document.dispatchEvent(new CustomEvent('bb-open-record', {detail: recObj})));
                rc.append(openBtn);
            }
            dossier.append(rc);
        }
        return dossier;
    }

    function renderDiscoveryCards() {
        const cardsBox = byId('disc-cards');
        const dossierBox = byId('disc-dossier-box');
        const summaryLine = byId('disc-summary-line');
        const ov = state.data?.discoveries_overview;
        if (!cardsBox || !dossierBox || !ov) return;

        const discs = visibleDiscoveries();
        const c = ov.counts;
        if (summaryLine) {
            summaryLine.textContent = ov.source_available
                ? `${c.sustained} sustentada(s) na confrontação automática · ${c.weak_or_redundant} fraca(s)/redundante(s) · ${c.stale} desatualizada(s) (${ov.llm_model})`
                : 'Nenhum resultado de descoberta disponível.';
        }

        cardsBox.replaceChildren();
        if (!discs.length) {
            cardsBox.append(el('p', 'Nenhuma descoberta candidata para o filtro selecionado.', 'muted'));
            dossierBox.hidden = true;
            return;
        }

        for (const d of discs) {
            const isSustained = d.confrontation_status === 'SUSTAINED_CANDIDATE';
            const isSelected = state.selectedDiscoveryId === d.discovery_id;
            const card = el('button', undefined, 'disc-card' + (isSustained ? '' : ' weak') + (isSelected ? ' selected' : ''));
            card.type = 'button';

            const top = el('div');
            top.append(el('span', verdictLabels[d.confrontation_status] || d.confrontation_status, 'net-badge ' + (isSustained ? 'sustained' : 'weak')));
            top.append(el('span', `Estratégia ${d.strategy}`, 'net-badge'));
            if (d.stale) top.append(el('span', 'Desatualizada', 'net-badge stale'));

            card.append(
                top,
                el('div', d.title, 'disc-card-title'),
                el('p', d.formulation, 'disc-card-formulation'),
                el('div', `${d.nature} · ${d.supporting_records.length} registro(s) fundamentador(es)`, 'disc-card-meta')
            );
            card.addEventListener('click', () => {
                state.selectedDiscoveryId = state.selectedDiscoveryId === d.discovery_id ? null : d.discovery_id;
                state.selectedInsightId = null;
                state.selectedDimensionId = null;
                state.selectedConnectionId = null;
                state.selectedSemPairIndex = null;
                syncCrossFilter();
            });
            cardsBox.append(card);
        }

        const selected = state.selectedDiscoveryId ? findDiscovery(state.selectedDiscoveryId) : null;
        if (selected) {
            dossierBox.hidden = false;
            dossierBox.replaceChildren(buildDiscoveryDossier(selected));
        } else {
            dossierBox.hidden = true;
            dossierBox.replaceChildren();
        }
    }

    function renderSelectionBox() {
        const box = byId('analytics-selection-box');
        if (!box) return;
        box.replaceChildren();
        if (state.selectedDiscoveryId) {
            const disc = findDiscovery(state.selectedDiscoveryId);
            box.hidden = false;
            box.append(el('strong', disc ? disc.title : state.selectedDiscoveryId));
            box.append(el('p', (disc?.strategy_label || '') + ' · ' + (verdictLabels[disc?.confrontation_status] || ''), 'muted'));
            return;
        }
        if (state.selectedInsightId) {
            const rec = recordMap().get(state.selectedInsightId);
            box.hidden = false;
            box.append(el('strong', rec ? rec.title : state.selectedInsightId));
            const row = el('div', undefined, 'document-actions');
            const openBtn = el('button', 'Abrir card integral e trajetória ↗', 'button outline');
            openBtn.type = 'button';
            openBtn.addEventListener('click', () => {
                if (rec) document.dispatchEvent(new CustomEvent('bb-open-record', {detail: rec}));
            });
            row.append(openBtn);
            box.append(row);
            return;
        }
        if (state.selectedConnectionId) {
            const conn = findConnection(state.selectedConnectionId);
            box.hidden = false;
            box.append(el('strong', conn?.isRegistered ? 'Relação intelectual registrada' : 'Conexão analítica candidata'));
            return;
        }
        if (state.selectedDimensionId) {
            const dim = state.data.graph.dimensions.find(d => d.id === state.selectedDimensionId);
            box.hidden = false;
            box.append(el('strong', 'Dimensão (referência lexical): ' + (dim ? dim.label : state.selectedDimensionId)));
            return;
        }
        if (state.selectedDate) {
            box.hidden = false;
            box.append(el('strong', 'Data selecionada: ' + state.selectedDate.split('-').reverse().join('/') + ' (' + state.calAxis + ')'));
            return;
        }
        box.hidden = true;
    }

    // 1. PERSPECTIVA PRINCIPAL: DESCOBERTAS (BB-CORE-EXP-003)
    function renderDiscoveriesView() {
        const svg = byId('analytics-graph');
        const legend = byId('net-legend');
        const panel = byId('net-panel-body');
        const summaryLine = byId('net-summary-line');
        const ov = state.data?.discoveries_overview;
        if (!svg || !ov) return;

        legend.replaceChildren(
            el('span', '◈ Descoberta candidata (sustentada)'),
            el('span', '◇ Fraca/redundante (confrontada)'),
            el('span', '▢ Registro fundamentador')
        );

        const discs = visibleDiscoveries();
        const nodes = state.data.record_network?.nodes || [];
        const c = ov.counts;
        summaryLine.textContent = ov.source_available
            ? `${ov.instruction} (${ov.llm_model}) · ${c.sustained} sustentada(s) · ${c.weak_or_redundant} fraca(s)/redundante(s) · ${c.stale} desatualizada(s) · veredito automático ≠ validação científica`
            : 'Nenhum resultado de descoberta (EXP-003) carregado.';

        svg.replaceChildren();
        svg.append(svgEl('rect', {width: 1100, height: 580, fill: '#f8fbfd'}));
        if (!ov.source_available || !discs.length) {
            svg.append(svgEl('text', {x: 550, y: 290, 'text-anchor': 'middle', fill: '#5d768a'}, 'Nenhuma descoberta candidata disponível para os filtros atuais.'));
            panel.replaceChildren(el('p', 'Sem descobertas disponíveis.', 'muted'));
            return;
        }

        const viewport = svgEl('g', {id: 'net-viewport'});
        applyTransform(viewport);
        svg.append(viewport);

        // Modo focado quando uma descoberta ou registro está selecionado (Seção 6: evitar poluição permanente)
        const selectedDisc = state.selectedDiscoveryId ? findDiscovery(state.selectedDiscoveryId) : null;
        const shownDiscs = selectedDisc
            ? [selectedDisc]
            : (state.selectedInsightId
                ? discs.filter(d => d.supporting_records.some(s => s.record_id === state.selectedInsightId))
                : discs);

        const shownRecIds = new Set();
        for (const d of shownDiscs) {
            for (const s of d.supporting_records) shownRecIds.add(s.record_id);
        }
        const shownRecs = selectedDisc
            ? nodes.filter(n => shownRecIds.has(n.id))
            : (state.selectedInsightId ? nodes.filter(n => n.id === state.selectedInsightId) : nodes);

        viewport.append(svgEl('text', {x: 90, y: 36, class: 'graph-caption'}, selectedDisc ? 'Descoberta em exame' : 'Descobertas candidatas (EXP-003)'));
        viewport.append(svgEl('text', {x: 730, y: 36, class: 'graph-caption'}, selectedDisc ? 'Registros que a fundamentam' : 'Registros intelectuais (âncoras)'));

        const discPos = {};
        const dStepY = Math.min(82, 460 / Math.max(shownDiscs.length, 1));
        const dStartY = 290 - ((shownDiscs.length - 1) * dStepY) / 2;
        shownDiscs.forEach((d, i) => {
            discPos[d.discovery_id] = {x: 245, y: selectedDisc ? 280 : dStartY + i * dStepY};
        });

        const recPos = {};
        const rStepY = Math.min(96, 460 / Math.max(shownRecs.length, 1));
        const rStartY = 290 - ((shownRecs.length - 1) * rStepY) / 2;
        shownRecs.forEach((r, i) => {
            recPos[r.id] = {x: 840, y: shownRecs.length === 1 ? 280 : rStartY + i * rStepY};
        });

        // Arestas Descoberta <-> Registro fundamentador
        for (const d of shownDiscs) {
            const p1 = discPos[d.discovery_id];
            if (!p1) continue;
            const isSustained = d.confrontation_status === 'SUSTAINED_CANDIDATE';
            for (const sr of d.supporting_records) {
                const p2 = recPos[sr.record_id];
                if (!p2) continue;
                const path = svgEl('path', {
                    class: 'net-edge',
                    d: `M ${p1.x + 175} ${p1.y} C ${p1.x + 330} ${p1.y}, ${p2.x - 300} ${p2.y}, ${p2.x - 115} ${p2.y}`,
                    stroke: isSustained ? '#0c7c66' : '#8a99a8',
                    'stroke-width': isSustained ? 2.4 : 1.5,
                    'stroke-dasharray': isSustained ? '' : '5 4',
                    opacity: isSustained ? 0.85 : 0.45,
                });
                path.append(svgEl('title', {}, `${d.title} ← ${sr.record_title}`));
                viewport.append(path);
            }
        }

        // Nós de descoberta (cards à esquerda)
        for (const d of shownDiscs) {
            const p = discPos[d.discovery_id];
            const isSustained = d.confrontation_status === 'SUSTAINED_CANDIDATE';
            const isSelected = state.selectedDiscoveryId === d.discovery_id;
            const cardW = 350;
            const cardH = shownDiscs.length > 5 ? 64 : 74;
            const g = svgEl('g', {
                class: 'net-card-node',
                transform: `translate(${p.x - cardW / 2} ${p.y - cardH / 2})`,
            });
            g.append(svgEl('rect', {
                width: cardW,
                height: cardH,
                rx: 9,
                fill: isSustained ? '#f4fbf9' : '#f8fafc',
                stroke: isSelected ? '#0b5cab' : (isSustained ? '#0c7c66' : '#8a99a8'),
                'stroke-width': isSelected ? 3 : (isSustained ? 2.2 : 1.4),
                'stroke-dasharray': isSustained ? '' : '4 3',
            }));
            g.append(svgEl('text', {x: 12, y: 18, fill: isSustained ? '#0c5947' : '#586b7a', 'font-size': 10, 'font-weight': 700},
                `Estratégia ${d.strategy} · ${verdictLabels[d.confrontation_status] || d.confrontation_status}${d.stale ? ' · ⚠ DESATUALIZADA' : ''}`));
            const [l1, l2] = wrapTitle(d.title, 44);
            g.append(svgEl('text', {x: 12, y: 38, fill: '#0e2438', 'font-size': 12.2, 'font-weight': 600}, l1));
            if (l2) g.append(svgEl('text', {x: 12, y: 54, fill: '#0e2438', 'font-size': 12.2, 'font-weight': 600}, l2));
            g.addEventListener('click', () => {
                state.selectedDiscoveryId = state.selectedDiscoveryId === d.discovery_id ? null : d.discovery_id;
                state.selectedInsightId = null;
                syncCrossFilter();
            });
            viewport.append(g);
        }

        // Nós de registros (cards compactos à direita)
        for (const r of shownRecs) {
            const p = recPos[r.id];
            const isSelected = state.selectedInsightId === r.id;
            const depCount = discs.filter(d => d.supporting_records.some(s => s.record_id === r.id)).length;
            const cardW = 230;
            const cardH = 74;
            const g = svgEl('g', {
                class: 'net-card-node',
                transform: `translate(${p.x - cardW / 2} ${p.y - cardH / 2})`,
            });
            g.append(svgEl('rect', {
                width: cardW,
                height: cardH,
                rx: 9,
                fill: '#ffffff',
                stroke: isSelected ? '#0b5cab' : '#183a56',
                'stroke-width': isSelected ? 3 : 1.6,
            }));
            g.append(svgEl('text', {x: 11, y: 18, fill: '#47657d', 'font-size': 10, 'font-weight': 700}, `${r.id.slice(0, 6)} · ${depCount} desc.`));
            const [l1, l2] = wrapTitle(r.title, 28);
            g.append(svgEl('text', {x: 11, y: 38, fill: '#0e2438', 'font-size': 12, 'font-weight': 600}, l1));
            if (l2) g.append(svgEl('text', {x: 11, y: 54, fill: '#0e2438', 'font-size': 12, 'font-weight': 600}, l2));
            g.addEventListener('click', () => {
                state.selectedInsightId = state.selectedInsightId === r.id ? null : r.id;
                state.selectedDiscoveryId = null;
                syncCrossFilter();
            });
            viewport.append(g);
        }

        // Painel lateral de exame da descoberta / registro
        panel.replaceChildren();
        const recById = recordMap();

        if (selectedDisc) {
            const dossier = el('div', undefined, 'disc-dossier');
            const badgeCls = selectedDisc.confrontation_status === 'SUSTAINED_CANDIDATE' ? 'sustained' : 'weak';
            dossier.append(el('span', verdictLabels[selectedDisc.confrontation_status] || selectedDisc.confrontation_status, 'net-badge ' + badgeCls));
            dossier.append(el('span', 'Proposição candidata (não canônica)', 'net-badge'));
            if (selectedDisc.stale) {
                dossier.append(el('span', 'Potencialmente desatualizada', 'net-badge stale'));
                dossier.append(el('p', selectedDisc.stale_reasons.join(' · '), 'muted'));
            }
            dossier.append(el('p', selectedDisc.epistemic_notice, 'muted'));

            dossier.append(el('h5', 'Formulação percebida'));
            dossier.append(el('p', selectedDisc.formulation));

            dossier.append(el('h5', 'Justificativa da integração'));
            dossier.append(el('p', selectedDisc.integration_justification));

            dossier.append(el('h5', 'Distinção do conteúdo preservado'));
            dossier.append(el('p', selectedDisc.distinction_from_preserved_content));

            dossier.append(el('h5', 'Relevância potencial'));
            dossier.append(el('p', selectedDisc.potential_relevance));

            if (selectedDisc.confrontation) {
                const cf = selectedDisc.confrontation;
                dossier.append(el('h5', 'Confrontação crítica independente (E)'));
                dossier.append(el('p', cf.critique));
                const critDet = el('details');
                critDet.append(el('summary', 'Critérios examinados (7 verificações)'));
                critDet.append(el('pre',
                    `Já explícita em único registro: ${cf.already_explicit_in_single_record ? 'Sim' : 'Não'}\n`
                    + `Apenas resumo/classificação: ${cf.merely_summary_or_classification ? 'Sim' : 'Não'}\n`
                    + `Estrutura transversal fundamentada: ${cf.reveals_grounded_transversal_structure ? 'Sim' : 'Não'}\n`
                    + `Depende da integração: ${cf.depends_on_integration ? 'Sim' : 'Não'}\n`
                    + `Registros sustentam: ${cf.records_sustain_interpretation ? 'Sim' : 'Não'}\n`
                    + `Acrescenta compreensão/investigação: ${cf.adds_comprehension_or_investigation ? 'Sim' : 'Não'}`
                ));
                dossier.append(critDet);
            }

            if (selectedDisc.limitations_and_counterarguments?.length) {
                dossier.append(el('h5', 'Limitações e contra-argumentos'));
                const ul = el('ul');
                for (const l of selectedDisc.limitations_and_counterarguments) ul.append(el('li', l));
                dossier.append(ul);
            }

            if (selectedDisc.investigation_possibilities?.length) {
                dossier.append(el('h5', 'Possibilidades de investigação'));
                const ul = el('ul');
                for (const inv of selectedDisc.investigation_possibilities) ul.append(el('li', inv));
                dossier.append(ul);
            }

            dossier.append(el('h5', `Registros de origem (${selectedDisc.supporting_records.length})`));
            for (const sr of selectedDisc.supporting_records) {
                const rc = el('div', undefined, 'disc-rec-card');
                rc.append(el('strong', sr.record_title));
                if (sr.specific_contribution) rc.append(el('p', 'Contribuição: ' + sr.specific_contribution));
                for (const ex of sr.excerpts) {
                    rc.append(el('div', `${ex.exact_match ? '✓' : '⚠'} "${ex.excerpt}"`, 'net-excerpt' + (ex.exact_match ? '' : ' unverified')));
                }
                const recObj = recById.get(sr.record_id);
                if (recObj) {
                    const openBtn = el('button', 'Abrir card canônico e trajetória ↗', 'button outline');
                    openBtn.type = 'button';
                    openBtn.addEventListener('click', () => document.dispatchEvent(new CustomEvent('bb-open-record', {detail: recObj})));
                    rc.append(openBtn);
                }
                dossier.append(rc);
            }
            panel.append(dossier);
            return;
        }

        if (state.selectedInsightId) {
            const deps = allDiscoveries().filter(d => d.supporting_records.some(s => s.record_id === state.selectedInsightId));
            panel.append(el('h4', `Descobertas que dependem deste registro (${deps.length})`));
            if (!deps.length) {
                panel.append(el('p', 'Nenhuma descoberta candidata depende diretamente deste registro.', 'muted'));
            } else {
                for (const d of deps) {
                    const item = el('div', undefined, 'graph-link-item');
                    const head = el('div', undefined, 'graph-link-head');
                    head.append(el('strong', d.title), el('small', d.confrontation_status === 'SUSTAINED_CANDIDATE' ? 'sustentada' : 'fraca/red.'));
                    head.addEventListener('click', () => {
                        state.selectedDiscoveryId = d.discovery_id;
                        state.selectedInsightId = null;
                        syncCrossFilter();
                    });
                    item.append(head);
                    panel.append(item);
                }
            }
            return;
        }

        // Sem seleção: lista resumida das descobertas para seleção direta
        panel.append(el('h4', `Descobertas do EXP-003 (${discs.length})`));
        panel.append(el('p', 'Selecione uma descoberta para examinar formulação, trechos literais verificados, confrontação crítica e registros de origem.', 'muted'));
        for (const d of discs) {
            const item = el('div', undefined, 'graph-link-item');
            const head = el('div', undefined, 'graph-link-head');
            head.append(el('strong', `[${d.strategy}] ${d.title}`), el('small', d.confrontation_status === 'SUSTAINED_CANDIDATE' ? 'sustentada' : 'fraca/red.'));
            head.addEventListener('click', () => {
                state.selectedDiscoveryId = d.discovery_id;
                syncCrossFilter();
            });
            item.append(head);
            panel.append(item);
        }
    }

    // 2. ESPAÇO SEMÂNTICO (qwen3-embedding:4b)
    function renderSemanticSpaceView() {
        const svg = byId('analytics-graph');
        const legend = byId('net-legend');
        const panel = byId('net-panel-body');
        const summaryLine = byId('net-summary-line');
        const sem = state.data?.discoveries_overview?.semantic_space;
        if (!svg || !sem) return;

        legend.replaceChildren(
            el('span', '▢ Registro intelectual'),
            el('span', '─ Proximidade cosseno (auxiliar; não é relação intelectual)')
        );
        summaryLine.textContent = `${sem.embed_model || 'embeddings'} · ${sem.epistemic_note}`;

        const pairs = sem[state.semField] || [];
        const nodes = state.data.record_network?.nodes || [];
        svg.replaceChildren();
        svg.append(svgEl('rect', {width: 1100, height: 580, fill: '#f8fbfd'}));
        svg.append(svgEl('text', {x: 550, y: 36, 'text-anchor': 'middle', class: 'graph-caption'}, `Espaço semântico exploratório (${state.semField})`));

        const pos = {};
        nodes.forEach((n, i) => {
            const ang = -Math.PI / 2 + (i / Math.max(nodes.length, 1)) * Math.PI * 2;
            pos[n.id] = {x: 550 + Math.cos(ang) * 350, y: 300 + Math.sin(ang) * 195};
        });

        pairs.forEach((p, idx) => {
            const p1 = pos[p.a_id];
            const p2 = pos[p.b_id];
            if (!p1 || !p2) return;
            const isSel = state.selectedSemPairIndex === idx;
            const norm = Math.max(0, Math.min(1, (p.cosine - 0.3) / 0.6));
            const line = svgEl('line', {
                class: 'net-edge',
                x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y,
                stroke: isSel ? '#0b5cab' : '#1c9b98',
                'stroke-width': isSel ? 4 : (1 + norm * 3.5).toFixed(2),
                opacity: isSel ? 0.95 : (0.15 + norm * 0.65).toFixed(2),
            });
            line.append(svgEl('title', {}, `${p.a_title} ↔ ${p.b_title}: cosseno ${p.cosine}`));
            line.addEventListener('click', () => {
                state.selectedSemPairIndex = state.selectedSemPairIndex === idx ? null : idx;
                syncCrossFilter();
            });
            svg.append(line);
        });

        for (const n of nodes) {
            const p = pos[n.id];
            const g = svgEl('g', {class: 'net-card-node', transform: `translate(${p.x - 105} ${p.y - 34})`});
            g.append(svgEl('rect', {width: 210, height: 68, rx: 8, fill: '#fff', stroke: '#183a56', 'stroke-width': 1.6}));
            const [l1, l2] = wrapTitle(n.title, 27);
            g.append(svgEl('text', {x: 10, y: 27, fill: '#0e2438', 'font-size': 12, 'font-weight': 600}, l1));
            if (l2) g.append(svgEl('text', {x: 10, y: 44, fill: '#0e2438', 'font-size': 12, 'font-weight': 600}, l2));
            g.addEventListener('click', () => {
                state.selectedInsightId = state.selectedInsightId === n.id ? null : n.id;
                state.selectedSemPairIndex = null;
                syncCrossFilter();
            });
            svg.append(g);
        }

        panel.replaceChildren(el('h4', 'Similaridades cosseno (ordenadas)'));
        pairs.forEach((p, idx) => {
            const item = el('div', undefined, 'graph-link-item');
            const head = el('div', undefined, 'graph-link-head');
            head.append(el('strong', `${p.a_title.slice(0, 22)}… ↔ ${p.b_title.slice(0, 22)}…`), el('small', String(p.cosine)));
            head.addEventListener('click', () => {
                state.selectedSemPairIndex = state.selectedSemPairIndex === idx ? null : idx;
                syncCrossFilter();
            });
            item.append(head);
            panel.append(item);
        });
    }

    // 3. REDE DE REGISTROS (EXP-002)
    function layoutRecordNodes(nodes, edges, topology) {
        const W = 1100;
        const H = 580;
        const pos = {};
        const connectedIds = nodes.filter(n => (topology.degrees[n.id] || 0) > 0).map(n => n.id);
        const isolatedIds = nodes.filter(n => (topology.degrees[n.id] || 0) === 0).map(n => n.id);

        if (connectedIds.length) {
            const centerX = W / 2;
            const centerY = isolatedIds.length ? 235 : H / 2;
            const rx = Math.min(370, 170 + connectedIds.length * 36);
            const ry = Math.min(185, 110 + connectedIds.length * 16);
            connectedIds.forEach((id, i) => {
                const ang = -Math.PI / 2 + (i / connectedIds.length) * Math.PI * 2;
                pos[id] = {x: centerX + Math.cos(ang) * rx, y: centerY + Math.sin(ang) * ry};
            });
            for (let iter = 0; iter < 55; iter++) {
                const disp = new Map(connectedIds.map(id => [id, {dx: 0, dy: 0}]));
                for (let i = 0; i < connectedIds.length; i++) {
                    for (let j = i + 1; j < connectedIds.length; j++) {
                        const u = connectedIds[i], v = connectedIds[j];
                        const dx = pos[u].x - pos[v].x;
                        const dy = pos[u].y - pos[v].y;
                        const dist = Math.hypot(dx, dy) || 1;
                        if (dist < 250) {
                            const push = (250 - dist) * 0.14;
                            disp.get(u).dx += (dx / dist) * push;
                            disp.get(u).dy += (dy / dist) * push * 0.7;
                            disp.get(v).dx -= (dx / dist) * push;
                            disp.get(v).dy -= (dy / dist) * push * 0.7;
                        }
                    }
                }
                for (const id of connectedIds) {
                    pos[id].x = Math.max(130, Math.min(W - 130, pos[id].x + disp.get(id).dx));
                    pos[id].y = Math.max(75, Math.min(isolatedIds.length ? 395 : H - 75, pos[id].y + disp.get(id).dy));
                }
            }
        }
        if (isolatedIds.length) {
            const cols = Math.min(4, isolatedIds.length);
            const spacingX = Math.min(255, (W - 140) / Math.max(cols, 1));
            const startX = (W - spacingX * (cols - 1)) / 2;
            const baseY = connectedIds.length ? 495 : 220;
            isolatedIds.forEach((id, idx) => {
                pos[id] = {x: startX + (idx % cols) * spacingX, y: baseY + Math.floor(idx / cols) * 105};
            });
        }
        return pos;
    }

    function applyTransform(viewport) {
        if (!viewport) return;
        viewport.setAttribute('transform', `translate(${state.panX} ${state.panY}) scale(${state.zoom})`);
    }

    function renderRecordNetwork() {
        const svg = byId('analytics-graph');
        const legend = byId('net-legend');
        const panel = byId('net-panel-body');
        const summaryLine = byId('net-summary-line');
        if (!svg || !state.data?.record_network) return;

        const net = state.data.record_network;
        const {nodes, candidate_connections: cands, registered_relations: regs, topology} = net;

        legend.replaceChildren(
            el('span', '▢ Card (registro)'),
            el('span', '─ Conexão analítica concordante'),
            el('span', '┄ Conexão divergente (ordem)'),
            el('span', '═ Relação registrada')
        );

        summaryLine.textContent = net.source_available
            ? `${nodes.length} registro(s) · ${cands.length} conexão(ões) candidata(s) (${net.concordant_connected_count} concordante(s), ${net.divergent_count} divergente(s)) · ${net.abstained_count} abstenção(ões)`
            : `${nodes.length} registro(s) · sem resultados do EXP-002`;

        svg.replaceChildren();
        svg.append(svgEl('rect', {width: 1100, height: 580, fill: '#f8fbfd'}));
        const viewport = svgEl('g', {id: 'net-viewport'});
        applyTransform(viewport);
        svg.append(viewport);

        const allEdges = [...cands.map(c => [c.source_id, c.target_id]), ...regs.map(r => [r.left_id, r.right_id])];
        const pos = layoutRecordNodes(nodes, allEdges, topology);

        const neighborIds = new Set();
        if (state.selectedInsightId) {
            neighborIds.add(state.selectedInsightId);
            for (const c of cands) {
                if (c.source_id === state.selectedInsightId) neighborIds.add(c.target_id);
                if (c.target_id === state.selectedInsightId) neighborIds.add(c.source_id);
            }
        } else if (state.selectedConnectionId) {
            const conn = findConnection(state.selectedConnectionId);
            if (conn) { neighborIds.add(conn.source_id); neighborIds.add(conn.target_id); }
        }
        const hasHighlight = neighborIds.size > 0;

        for (const c of cands) {
            const p1 = pos[c.source_id], p2 = pos[c.target_id];
            if (!p1 || !p2) continue;
            const isDiv = c.stability === 'DIVERGENT_ORDER_DEPENDENT';
            const isDim = hasHighlight && !(neighborIds.has(c.source_id) && neighborIds.has(c.target_id));
            const path = svgEl('path', {
                class: 'net-edge' + (isDim ? ' dimmed' : ''),
                d: `M ${p1.x} ${p1.y} Q ${(p1.x + p2.x) / 2} ${(p1.y + p2.y) / 2 - 22} ${p2.x} ${p2.y}`,
                stroke: isDiv ? '#c97a16' : '#1c9b98',
                'stroke-width': state.selectedConnectionId === c.id ? 3.5 : 2.1,
                'stroke-dasharray': isDiv ? '6 4' : '',
                opacity: 0.7,
            });
            path.addEventListener('click', () => {
                state.selectedConnectionId = state.selectedConnectionId === c.id ? null : c.id;
                state.selectedInsightId = null;
                syncCrossFilter();
            });
            viewport.append(path);
        }

        for (const n of nodes) {
            const p = pos[n.id];
            if (!p) continue;
            const isDim = hasHighlight && !neighborIds.has(n.id);
            const g = svgEl('g', {class: 'net-card-node' + (isDim ? ' dimmed' : ''), transform: `translate(${p.x - 105} ${p.y - 42})`});
            g.append(svgEl('rect', {width: 210, height: 84, rx: 9, fill: '#fff', stroke: state.selectedInsightId === n.id ? '#0b5cab' : '#183a56', 'stroke-width': state.selectedInsightId === n.id ? 3 : 1.6}));
            const [l1, l2] = wrapTitle(n.title, 27);
            g.append(svgEl('text', {x: 11, y: 19, fill: '#47657d', 'font-size': 10, 'font-weight': 700}, `${(kindLabels[n.kind] || n.status || '').slice(0, 20)} · ${n.id.slice(0, 6)}`));
            g.append(svgEl('text', {x: 11, y: 43, fill: '#0e2438', 'font-size': 12.5, 'font-weight': 600}, l1));
            if (l2) g.append(svgEl('text', {x: 11, y: 60, fill: '#0e2438', 'font-size': 12.5, 'font-weight': 600}, l2));
            g.addEventListener('click', () => {
                state.selectedInsightId = state.selectedInsightId === n.id ? null : n.id;
                state.selectedConnectionId = null;
                syncCrossFilter();
            });
            viewport.append(g);
        }

        panel.replaceChildren();
        const recById = recordMap();
        if (state.selectedConnectionId) {
            const conn = findConnection(state.selectedConnectionId);
            if (conn) {
                panel.append(el('p', `${recById.get(conn.source_id)?.title || conn.source_id} ↔ ${recById.get(conn.target_id)?.title || conn.target_id}`));
                if (conn.nature) panel.append(el('p', conn.nature));
                return;
            }
        }
        panel.append(el('h4', 'Síntese do EXP-002'));
        panel.append(el('p', `${nodes.length} registros · ${cands.length} conexões candidatas · ${regs.length} relações registradas.`, 'muted'));
    }

    // 4. REFERÊNCIA LEXICAL (v0.1.0)
    function renderLexicalGraph() {
        const svg = byId('analytics-graph');
        const legend = byId('net-legend');
        const panel = byId('net-panel-body');
        const summaryLine = byId('net-summary-line');
        if (!svg || !state.data) return;

        legend.replaceChildren(el('span', '○ Âncora'), el('span', '◎ Dimensão lexical'));
        summaryLine.textContent = `Referência lexical (${state.data.methodology.version}) · ${state.data.graph.inferred_associations.length} associação(ões)`;

        const {anchors, dimensions, inferred_associations: assocs} = state.data.graph;
        svg.replaceChildren();
        svg.append(svgEl('rect', {width: 1100, height: 580, fill: '#f8fbfd'}));
        const anchorPos = {};
        anchors.forEach((a, i) => { anchorPos[a.id] = graphPoint(i, anchors.length, 230, 290, 185); });
        const dimPos = {};
        dimensions.forEach((d, i) => { dimPos[d.id] = {...graphPoint(i, dimensions.length, 830, 290, 200), color: d.color}; });
        const maxDimCount = Math.max(...dimensions.map(d => d.record_count), 1);

        for (const assoc of assocs) {
            const src = anchorPos[assoc.insight_id], dst = dimPos[assoc.dimension_id];
            if (!src || !dst) continue;
            svg.append(svgEl('path', {
                class: 'graph-edge',
                d: `M ${src.x} ${src.y} C ${src.x + 230} ${src.y}, ${dst.x - 230} ${dst.y}, ${dst.x} ${dst.y}`,
                stroke: dst.color,
                'stroke-width': (1.5 + assoc.normalized_weight * 6).toFixed(2),
                opacity: (0.22 + assoc.normalized_weight * 0.58).toFixed(2),
            }));
        }
        for (const a of anchors) {
            const p = anchorPos[a.id];
            const g = svgEl('g', {class: 'graph-node-svg', transform: `translate(${p.x} ${p.y})`});
            g.append(svgEl('circle', {r: 32, fill: '#fff', stroke: '#062a4f', 'stroke-width': 2.6}));
            g.append(svgEl('text', {'text-anchor': 'middle', y: 4}, a.title.length > 16 ? a.title.slice(0, 15) + '…' : a.title));
            svg.append(g);
        }
        for (const d of dimensions) {
            const p = dimPos[d.id];
            const r = 28 + (d.record_count / maxDimCount) * 26;
            const g = svgEl('g', {class: 'graph-node-svg', transform: `translate(${p.x} ${p.y})`});
            g.append(svgEl('circle', {r, fill: '#fff', stroke: d.color, 'stroke-width': 3}));
            g.append(svgEl('text', {'text-anchor': 'middle', y: 4}, d.label.length > 22 ? d.label.slice(0, 21) + '…' : d.label));
            svg.append(g);
        }
        panel.replaceChildren(el('h4', 'Referência lexical (v0.1.0)'));
        panel.append(el('p', `${assocs.length} associações lexicais calculadas sobre ${anchors.length} registros.`, 'muted'));
    }

    function renderActivePerspective() {
        const zoomCtrl = byId('net-zoom-controls');
        const discCtrl = byId('disc-filter-controls');
        const semCtrl = byId('sem-field-controls');
        if (zoomCtrl) zoomCtrl.hidden = state.viewMode === 'lexical' || state.viewMode === 'semantic';
        if (discCtrl) discCtrl.hidden = state.viewMode !== 'discoveries';
        if (semCtrl) semCtrl.hidden = state.viewMode !== 'semantic';

        if (state.viewMode === 'discoveries') renderDiscoveriesView();
        else if (state.viewMode === 'semantic') renderSemanticSpaceView();
        else if (state.viewMode === 'records') renderRecordNetwork();
        else renderLexicalGraph();
    }

    // 5. TEMPORALIDADE (Calendário GitHub)
    function renderCalendar() {
        const container = byId('analytics-calendar');
        const summary = byId('cal-summary');
        const dayBox = byId('cal-day-events');
        if (!container || !state.data) return;

        const events = filteredEvents();
        const byDay = new Map();
        const undated = [];
        let newCount = 0;
        let subCount = 0;

        for (const ev of events) {
            const dk = dateKey(ev[state.calAxis]);
            if (!dk) {
                undated.push(ev);
                continue;
            }
            const bucket = byDay.get(dk) || {total: 0, newRecords: 0, subsequent: 0, events: []};
            bucket.total += 1;
            if (ev.category === 'NEW_RECORD') { bucket.newRecords += 1; newCount += 1; }
            else { bucket.subsequent += 1; subCount += 1; }
            bucket.events.push(ev);
            byDay.set(dk, bucket);
        }

        summary.replaceChildren(
            el('span', `Total datado (${state.calAxis}): ${newCount + subCount}`, 'cal-pill'),
            el('span', `Novos registros: ${newCount}`, 'cal-pill'),
            el('span', `Acontecimentos posteriores: ${subCount}`, 'cal-pill'),
        );
        if (state.calAxis === 'occurred_at' && undated.length) {
            const undatedBtn = el('button', `Sem data declarada (occurred_at): ${undated.length}`, 'cal-pill warn');
            undatedBtn.type = 'button';
            undatedBtn.addEventListener('click', () => {
                state.showUndated = !state.showUndated;
                state.selectedDate = null;
                renderDayEvents(undated, 'Acontecimentos sem data declarada (occurred_at)');
                const clearBtn = byId('analytics-clear');
                if (clearBtn) clearBtn.hidden = false;
            });
            summary.append(undatedBtn);
        }

        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const start = new Date(today);
        start.setDate(start.getDate() - (state.calPeriodDays - 1));
        start.setDate(start.getDate() - start.getDay());

        const maxDay = Math.max(...[...byDay.values()].map(b => b.total), 1);
        container.replaceChildren();

        const monthNames = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
        const board = el('div', undefined, 'cal-board');
        const monthsRow = el('div', undefined, 'cal-months');
        const labels = el('div', undefined, 'cal-day-labels');
        for (const name of ['', 'Seg', '', 'Qua', '', 'Sex', '']) labels.append(el('span', name));
        const grid = el('div', undefined, 'cal-grid');
        let lastMonth = -1;
        let weekIndex = 0;
        for (let d = new Date(start); d <= today; d.setDate(d.getDate() + 1)) {
            if (d.getDay() === 0) {
                const m = d.getMonth();
                monthsRow.append(el('span', (m !== lastMonth && (weekIndex > 0 || d.getDate() <= 7)) ? monthNames[m] : ''));
                lastMonth = m;
                weekIndex += 1;
            }
            const iso = d.toISOString().slice(0, 10);
            const bucket = byDay.get(iso);
            const count = bucket ? bucket.total : 0;
            let level = '';
            if (count > 0) {
                const ratio = count / maxDay;
                level = ratio <= 0.25 ? 'l1' : ratio <= 0.5 ? 'l2' : ratio <= 0.75 ? 'l3' : 'l4';
            }
            const cell = el('button', undefined, 'cal-cell' + (level ? ' ' + level : '') + (state.selectedDate === iso ? ' selected' : ''));
            cell.type = 'button';
            cell.title = bucket
                ? `${iso}: ${bucket.total} acontecimento(s) (${bucket.newRecords} novo(s), ${bucket.subsequent} posterior(es))`
                : `${iso}: 0 acontecimentos`;
            cell.addEventListener('click', () => {
                state.showUndated = false;
                state.selectedDate = state.selectedDate === iso ? null : iso;
                state.selectedDiscoveryId = null;
                state.selectedInsightId = null;
                state.selectedDimensionId = null;
                state.selectedConnectionId = null;
                state.selectedSemPairIndex = null;
                syncCrossFilter();
            });
            grid.append(cell);
        }
        const body = el('div', undefined, 'cal-body');
        body.append(labels, grid);
        const footer = el('div', undefined, 'cal-footer');
        footer.append(el('span', 'Menos'));
        for (const lvl of ['', 'l1', 'l2', 'l3', 'l4']) footer.append(el('i', undefined, 'cal-legend-box' + (lvl ? ' ' + lvl : '')));
        footer.append(el('span', 'Mais'));
        board.append(monthsRow, body, footer);
        container.append(board);

        if (state.selectedDate) {
            const bucket = byDay.get(state.selectedDate);
            renderDayEvents(bucket ? bucket.events : [], 'Acontecimentos em ' + state.selectedDate.split('-').reverse().join('/') + ' (' + state.calAxis + ')');
        } else if (!state.showUndated) {
            dayBox.hidden = true;
        }
    }

    function renderDayEvents(events, heading) {
        const dayBox = byId('cal-day-events');
        if (!dayBox) return;
        dayBox.hidden = false;
        dayBox.replaceChildren(el('strong', heading));
        if (!events.length) {
            dayBox.append(el('p', 'Nenhum acontecimento registrado nesta data para os filtros atuais.', 'muted'));
            return;
        }
        const recById = recordMap();
        const ul = el('ul');
        for (const ev of events) {
            const li = el('li');
            const rec = recById.get(ev.insight_id);
            const kindBadge = ev.category === 'NEW_RECORD' ? '[Novo registro]' : '[Acontecimento posterior]';
            li.append(el('span', `${kindBadge} ${eventTypeLabels[ev.event_type] || ev.event_type} — ${ev.summary || '(sem resumo)'} `));
            if (rec) {
                const btn = el('button', 'Abrir "' + rec.title.slice(0, 36) + (rec.title.length > 36 ? '…' : '') + '" ↗', 'button outline');
                btn.type = 'button';
                btn.addEventListener('click', () => document.dispatchEvent(new CustomEvent('bb-open-record', {detail: rec})));
                li.append(btn);
            }
            ul.append(li);
        }
        dayBox.append(ul);
    }

    async function loadAnalytics() {
        const meta = byId('analytics-meta');
        const note = byId('analytics-epistemic-note');
        try {
            const res = await fetch('/api/analytics/overview', {credentials: 'same-origin'});
            if (!res.ok) throw Error('Erro ao calcular projeção analítica (' + res.status + ')');
            const data = await res.json();
            state.data = data;
            const m = data.methodology;
            const ov = data.discoveries_overview;
            meta.textContent = `${m.record_universe_count} registro(s) · ${m.event_universe_count} acontecimento(s) · ${ov?.counts?.sustained || 0} descoberta(s) sustentada(s) (de ${ov?.counts?.total || 0} candidatas) · calculado em ${m.computed_at}`;
            note.textContent = m.epistemic_note;

            const sel = byId('cal-event-type');
            if (sel) {
                const currentVal = sel.value;
                sel.replaceChildren(el('option', 'Todos os tipos'));
                sel.firstChild.value = '';
                const types = [...new Set(data.calendar.events.map(e => e.event_type))].sort();
                for (const t of types) {
                    const opt = el('option', eventTypeLabels[t] || t);
                    opt.value = t;
                    sel.append(opt);
                }
                sel.value = currentVal;
            }
            renderSelectionBox();
            renderDiscoveryCards();
            renderActivePerspective();
            renderCalendar();
        } catch (err) {
            if (meta) meta.textContent = err.message;
        }
    }

    // Pan & Zoom
    const svgElNode = byId('analytics-graph');
    if (svgElNode) {
        let dragging = false, sx = 0, sy = 0;
        svgElNode.addEventListener('mousedown', e => {
            if ((state.viewMode !== 'records' && state.viewMode !== 'discoveries') || (e.target !== svgElNode && e.target.tagName !== 'rect')) return;
            dragging = true;
            sx = e.clientX;
            sy = e.clientY;
        });
        window.addEventListener('mousemove', e => {
            if (!dragging) return;
            state.panX += (e.clientX - sx) / state.zoom;
            state.panY += (e.clientY - sy) / state.zoom;
            sx = e.clientX;
            sy = e.clientY;
            applyTransform(byId('net-viewport'));
        });
        window.addEventListener('mouseup', () => { dragging = false; });
    }

    byId('net-zoom-in')?.addEventListener('click', () => { state.zoom = Math.min(2.2, state.zoom * 1.15); applyTransform(byId('net-viewport')); });
    byId('net-zoom-out')?.addEventListener('click', () => { state.zoom = Math.max(0.55, state.zoom * 0.85); applyTransform(byId('net-viewport')); });
    byId('net-zoom-reset')?.addEventListener('click', () => { state.zoom = 1; state.panX = 0; state.panY = 0; applyTransform(byId('net-viewport')); });
    byId('net-expand')?.addEventListener('click', () => {
        state.expanded = !state.expanded;
        byId('net-layout')?.classList.toggle('expanded', state.expanded);
        byId('net-expand').textContent = state.expanded ? '⤡ Recolher' : '⤢ Expandir';
    });

    function setViewMode(mode) {
        state.viewMode = mode;
        state.selectedDiscoveryId = null;
        state.selectedInsightId = null;
        state.selectedDimensionId = null;
        state.selectedConnectionId = null;
        state.selectedSemPairIndex = null;
        state.zoom = 1;
        state.panX = 0;
        state.panY = 0;
        for (const [id, m] of [['net-mode-discoveries', 'discoveries'], ['net-mode-semantic', 'semantic'], ['net-mode-records', 'records'], ['net-mode-lexical', 'lexical']]) {
            byId(id)?.classList.toggle('active', mode === m);
        }
        syncCrossFilter();
    }

    byId('net-mode-discoveries')?.addEventListener('click', () => setViewMode('discoveries'));
    byId('net-mode-semantic')?.addEventListener('click', () => setViewMode('semantic'));
    byId('net-mode-records')?.addEventListener('click', () => setViewMode('records'));
    byId('net-mode-lexical')?.addEventListener('click', () => setViewMode('lexical'));

    byId('disc-filter-all')?.addEventListener('click', () => {
        state.discFilter = 'all';
        byId('disc-filter-all')?.classList.add('active');
        byId('disc-filter-sustained')?.classList.remove('active');
        renderDiscoveryCards();
        renderDiscoveriesView();
    });
    byId('disc-filter-sustained')?.addEventListener('click', () => {
        state.discFilter = 'sustained';
        byId('disc-filter-sustained')?.classList.add('active');
        byId('disc-filter-all')?.classList.remove('active');
        renderDiscoveryCards();
        renderDiscoveriesView();
    });
    byId('sem-field-select')?.addEventListener('change', e => {
        state.semField = e.target.value;
        state.selectedSemPairIndex = null;
        syncCrossFilter();
    });

    document.addEventListener('bb-session-ready', loadAnalytics);
    byId('analytics-refresh')?.addEventListener('click', loadAnalytics);
    byId('analytics-clear')?.addEventListener('click', () => {
        state.selectedDiscoveryId = null;
        state.selectedInsightId = null;
        state.selectedDimensionId = null;
        state.selectedConnectionId = null;
        state.selectedSemPairIndex = null;
        state.selectedDate = null;
        state.showUndated = false;
        state.calEventType = '';
        if (byId('cal-event-type')) byId('cal-event-type').value = '';
        syncCrossFilter();
    });
    byId('cal-axis')?.addEventListener('change', e => { state.calAxis = e.target.value; state.selectedDate = null; state.showUndated = false; syncCrossFilter(); });
    byId('cal-period')?.addEventListener('change', e => { state.calPeriodDays = Number(e.target.value) || 365; renderCalendar(); });
    byId('cal-event-type')?.addEventListener('change', e => { state.calEventType = e.target.value; state.selectedDate = null; syncCrossFilter(); });
})();
