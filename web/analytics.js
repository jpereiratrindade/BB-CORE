'use strict';
(() => {
    const byId = id => document.getElementById(id);
    const SVG_NS = 'http://www.w3.org/2000/svg';

    const state = {
        data: null,
        selectedInsightId: null,
        selectedDimensionId: null,
        selectedDate: null,
        showUndated: false,
        calAxis: 'recorded_at',
        calPeriodDays: 90,
        calEventType: '',
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
        for (const a of (state.data?.graph?.anchors || [])) m.set(a.id, a);
        return m;
    }

    function filteredEvents() {
        if (!state.data) return [];
        return state.data.calendar.events.filter(ev => {
            if (state.calEventType && ev.event_type !== state.calEventType) return false;
            if (state.selectedInsightId && ev.insight_id !== state.selectedInsightId && ev.related_insight_id !== state.selectedInsightId) {
                return false;
            }
            if (state.selectedDimensionId && !ev.dimensions.includes(state.selectedDimensionId)) {
                return false;
            }
            return true;
        });
    }

    function activeInsightIdsFilter() {
        if (!state.data) return null;
        if (state.selectedInsightId) {
            const rec = recordMap().get(state.selectedInsightId);
            return {
                insightIds: [state.selectedInsightId],
                label: 'registro "' + (rec ? rec.title.slice(0, 40) : state.selectedInsightId.slice(0, 8)) + '"',
            };
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
            for (const ev of filteredEvents()) {
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
        const hasFilter = Boolean(state.selectedInsightId || state.selectedDimensionId || state.selectedDate || state.calEventType || state.showUndated);
        if (clearBtn) clearBtn.hidden = !hasFilter;
        document.dispatchEvent(new CustomEvent('bb-analytics-filter', {detail: activeInsightIdsFilter()}));
        renderSelectionBox();
        renderGraph();
        renderCalendar();
    }

    function renderSelectionBox() {
        const box = byId('analytics-selection-box');
        if (!box) return;
        box.replaceChildren();
        if (state.selectedInsightId) {
            const rec = recordMap().get(state.selectedInsightId);
            box.hidden = false;
            box.append(el('strong', 'Âncora selecionada: ' + (rec ? rec.title : state.selectedInsightId)));
            const row = el('div', undefined, 'document-actions');
            const openBtn = el('button', 'Abrir registro e trajetória ↗', 'button outline');
            openBtn.type = 'button';
            openBtn.addEventListener('click', () => {
                if (rec) document.dispatchEvent(new CustomEvent('bb-open-record', {detail: rec}));
            });
            row.append(openBtn);
            box.append(row);
            return;
        }
        if (state.selectedDimensionId) {
            const dim = state.data.graph.dimensions.find(d => d.id === state.selectedDimensionId);
            box.hidden = false;
            box.append(el('strong', 'Dimensão selecionada: ' + (dim ? dim.label : state.selectedDimensionId)));
            box.append(el('p', (dim ? dim.record_count : 0) + ' registro(s) associado(s) por léxico explícito (' + (dim?.origin || '') + ').'));
            return;
        }
        if (state.selectedDate) {
            box.hidden = false;
            box.append(el('strong', 'Data selecionada: ' + state.selectedDate.split('-').reverse().join('/') + ' (' + state.calAxis + ')'));
            return;
        }
        box.hidden = true;
    }

    function renderGraph() {
        const svg = byId('analytics-graph');
        const linksBox = byId('analytics-links');
        const relBox = byId('analytics-relations');
        if (!svg || !state.data) return;

        const {anchors, dimensions, inferred_associations: assocs, registered_relations: rels} = state.data.graph;
        svg.replaceChildren();
        svg.append(svgEl('rect', {width: 1100, height: 560, fill: '#f8fbfd'}));
        svg.append(svgEl('text', {x: 80, y: 38, class: 'graph-caption'}, 'Registros intelectuais (âncoras)'));
        svg.append(svgEl('text', {x: 730, y: 38, class: 'graph-caption'}, 'Dimensões conceituais (léxico)'));

        if (!anchors.length) {
            svg.append(svgEl('text', {x: 550, y: 280, 'text-anchor': 'middle', fill: '#5d768a'}, 'Nenhum registro preservado no acervo.'));
            linksBox.replaceChildren(el('p', 'Sem associações calculadas.', 'muted'));
            relBox.replaceChildren(el('p', 'Sem relações registradas.', 'muted'));
            return;
        }

        const anchorPos = {};
        anchors.forEach((a, i) => {
            anchorPos[a.id] = graphPoint(i, anchors.length, 230, 285, 185);
        });
        const dimPos = {};
        dimensions.forEach((d, i) => {
            dimPos[d.id] = {
                ...graphPoint(i, dimensions.length, 830, 285, 200),
                color: d.color,
            };
        });
        const maxDimCount = Math.max(...dimensions.map(d => d.record_count), 1);

        const activeFilter = activeInsightIdsFilter();
        const highlightedIds = activeFilter ? new Set(activeFilter.insightIds) : null;

        // 1. Relações intelectuais registradas (âncora <-> âncora)
        for (const rel of rels) {
            const p1 = anchorPos[rel.left_id];
            const p2 = anchorPos[rel.right_id];
            if (!p1 || !p2) continue;
            const path = svgEl('path', {
                class: 'graph-edge',
                d: `M ${p1.x} ${p1.y} Q ${Math.min(p1.x, p2.x) - 90} ${(p1.y + p2.y) / 2} ${p2.x} ${p2.y}`,
                stroke: '#0b5cab',
                'stroke-width': 2.2,
                'stroke-dasharray': '5 4',
                opacity: 0.75,
            });
            path.append(svgEl('title', {}, `Relação registrada (${rel.status}): ${rel.rationale}`));
            svg.append(path);
        }

        // 2. Associações conceituais calculadas (âncora -> dimensão)
        for (const assoc of assocs) {
            const src = anchorPos[assoc.insight_id];
            const dst = dimPos[assoc.dimension_id];
            if (!src || !dst) continue;
            const isDimmed = (state.selectedDimensionId && state.selectedDimensionId !== assoc.dimension_id)
                || (highlightedIds && !highlightedIds.has(assoc.insight_id));
            const width = 1.5 + assoc.normalized_weight * 6;
            const opacity = 0.22 + assoc.normalized_weight * 0.58;
            const path = svgEl('path', {
                class: 'graph-edge' + (isDimmed ? ' dimmed' : ''),
                d: `M ${src.x} ${src.y} C ${src.x + 230} ${src.y}, ${dst.x - 230} ${dst.y}, ${dst.x} ${dst.y}`,
                stroke: dst.color,
                'stroke-width': width.toFixed(2),
                opacity: opacity.toFixed(2),
            });
            path.append(svgEl('title', {}, `${assoc.dimension_label} · pontuação absoluta ${assoc.absolute_score} (norm. ${assoc.normalized_weight})`));
            path.addEventListener('click', () => {
                state.selectedDimensionId = state.selectedDimensionId === assoc.dimension_id ? null : assoc.dimension_id;
                state.selectedInsightId = null;
                state.selectedDate = null;
                syncCrossFilter();
            });
            svg.append(path);
        }

        // 3. Nós âncoras (tamanho uniforme; isolados visíveis com contorno tracejado)
        const anchorRadius = 32;
        for (const a of anchors) {
            const p = anchorPos[a.id];
            const isDimmed = highlightedIds && !highlightedIds.has(a.id);
            const g = svgEl('g', {
                class: 'graph-node-svg' + (isDimmed ? ' dimmed' : ''),
                transform: `translate(${p.x} ${p.y})`,
            });
            g.append(svgEl('circle', {
                r: anchorRadius,
                fill: a.unclassified ? '#f3f7fa' : '#fff',
                stroke: a.unclassified ? '#6b8194' : '#062a4f',
                'stroke-width': state.selectedInsightId === a.id ? 4 : 2.6,
                'stroke-dasharray': a.unclassified ? '4 3' : '',
            }));
            g.append(svgEl('circle', {
                r: anchorRadius - 9,
                fill: a.unclassified ? 'rgba(107,129,148,.06)' : 'rgba(6,42,79,.05)',
                stroke: 'rgba(6,42,79,.15)',
            }));
            const shortTitle = a.title.length > 16 ? a.title.slice(0, 15) + '…' : a.title;
            g.append(svgEl('text', {'text-anchor': 'middle', y: -2}, shortTitle));
            g.append(svgEl('text', {class: 'node-subtitle', 'text-anchor': 'middle', y: 13}, a.unclassified ? 'isolado' : a.matched_dimensions.length + ' dim.'));
            g.append(svgEl('title', {}, `${a.title}\nID: ${a.id}\n${a.unclassified ? 'Sem dimensão inferida (registro isolado)' : 'Dimensões: ' + a.matched_dimensions.join(', ')}`));
            g.addEventListener('click', () => {
                state.selectedInsightId = state.selectedInsightId === a.id ? null : a.id;
                state.selectedDimensionId = null;
                state.selectedDate = null;
                syncCrossFilter();
            });
            svg.append(g);
        }

        // 4. Nós de dimensões conceituais (diâmetro proporcional ao número de registros associados)
        for (const d of dimensions) {
            const p = dimPos[d.id];
            const radius = 28 + (d.record_count / maxDimCount) * 26;
            const isDimmed = state.selectedDimensionId && state.selectedDimensionId !== d.id;
            const g = svgEl('g', {
                class: 'graph-node-svg' + (isDimmed ? ' dimmed' : ''),
                transform: `translate(${p.x} ${p.y})`,
            });
            g.append(svgEl('circle', {
                r: radius,
                fill: '#fff',
                stroke: d.color,
                'stroke-width': state.selectedDimensionId === d.id ? 4.5 : 3,
            }));
            g.append(svgEl('circle', {
                r: Math.max(8, radius - 10),
                fill: d.color,
                opacity: 0.12,
            }));
            const label = d.label.length > 22 ? d.label.slice(0, 21) + '…' : d.label;
            g.append(svgEl('text', {'text-anchor': 'middle', y: -2}, label));
            g.append(svgEl('text', {class: 'node-subtitle', 'text-anchor': 'middle', y: 14}, d.record_count + ' reg.'));
            g.append(svgEl('title', {}, `${d.label} (${d.origin}): ${d.record_count} registro(s)`));
            g.addEventListener('click', () => {
                state.selectedDimensionId = state.selectedDimensionId === d.id ? null : d.id;
                state.selectedInsightId = null;
                state.selectedDate = null;
                syncCrossFilter();
            });
            svg.append(g);
        }

        // Lista auditável das associações no painel lateral
        const recById = recordMap();
        const visibleAssocs = assocs.filter(a =>
            (!state.selectedDimensionId || a.dimension_id === state.selectedDimensionId)
            && (!highlightedIds || highlightedIds.has(a.insight_id))
        );
        linksBox.replaceChildren();
        if (!visibleAssocs.length) {
            linksBox.append(el('p', 'Nenhuma associação conceitual inferida para a seleção atual.', 'muted'));
        } else {
            for (const a of visibleAssocs) {
                const rec = recById.get(a.insight_id);
                const item = el('div', undefined, 'graph-link-item');
                const head = el('div', undefined, 'graph-link-head');
                head.append(
                    el('strong', (rec ? rec.title.slice(0, 32) + (rec.title.length > 32 ? '…' : '') : a.insight_id.slice(0, 8)) + ' → ' + a.dimension_label),
                    el('small', 'pts: ' + a.absolute_score)
                );
                head.addEventListener('click', () => {
                    state.selectedInsightId = a.insight_id;
                    state.selectedDimensionId = null;
                    syncCrossFilter();
                });
                const details = el('details');
                details.append(el('summary', 'Inspecionar termos e pesos (' + a.evidence.length + ' regra(s))'));
                const ruleLines = a.evidence.map(e => `${e.field} (peso ${e.field_weight}): "${e.term}" (+${e.contribution})`).join('\n');
                details.append(el('pre', `Pontuação absoluta: ${a.absolute_score}\nPeso visual normalizado: ${a.normalized_weight}\nOrigem da categoria: ${a.category_origin}\n${ruleLines}`));
                item.append(head, details);
                linksBox.append(item);
            }
        }

        // Relações intelectuais registradas (separadas das inferências)
        relBox.replaceChildren();
        if (!rels.length) {
            relBox.append(el('p', 'Nenhuma relação intelectual registrada entre registros.', 'muted'));
        } else {
            for (const r of rels) {
                const lRec = recById.get(r.left_id);
                const rRec = recById.get(r.right_id);
                const item = el('div', undefined, 'graph-link-item');
                const head = el('div', undefined, 'graph-link-head');
                head.append(
                    el('strong', (lRec ? lRec.title.slice(0, 20) + '…' : r.left_id.slice(0, 8)) + ' ↔ ' + (rRec ? rRec.title.slice(0, 20) + '…' : r.right_id.slice(0, 8))),
                    el('small', r.status)
                );
                const details = el('details');
                details.append(el('summary', 'Fundamento registrado (' + r.attributions.length + ' atribuição/ões)'));
                details.append(el('p', r.rationale));
                item.append(head, details);
                relBox.append(item);
            }
        }
    }

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
            if (ev.category === 'NEW_RECORD') {
                bucket.newRecords += 1;
                newCount += 1;
            } else {
                bucket.subsequent += 1;
                subCount += 1;
            }
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
        // Alinhar ao domingo anterior para manter 7 linhas exatas (Dom..Sáb)
        start.setDate(start.getDate() - start.getDay());

        const maxDay = Math.max(...[...byDay.values()].map(b => b.total), 1);
        container.replaceChildren();

        const labels = el('div', undefined, 'cal-day-labels');
        for (const name of ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']) {
            labels.append(el('span', name));
        }
        const grid = el('div', undefined, 'cal-grid');
        for (let d = new Date(start); d <= today; d.setDate(d.getDate() + 1)) {
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
                state.selectedInsightId = null;
                state.selectedDimensionId = null;
                syncCrossFilter();
            });
            grid.append(cell);
        }
        container.append(labels, grid);

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
            meta.textContent = `Metodologia ${m.version} · ${m.record_universe_count} registro(s) · ${m.event_universe_count} acontecimento(s) · ${data.graph.unclassified_record_ids.length} registro(s) isolado(s) · calculado em ${m.computed_at}`;
            note.textContent = m.epistemic_note;

            // Preencher opções de tipo de evento existentes no diário
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
            renderGraph();
            renderCalendar();
        } catch (err) {
            if (meta) meta.textContent = err.message;
        }
    }

    document.addEventListener('bb-session-ready', loadAnalytics);
    byId('analytics-refresh')?.addEventListener('click', loadAnalytics);
    byId('analytics-clear')?.addEventListener('click', () => {
        state.selectedInsightId = null;
        state.selectedDimensionId = null;
        state.selectedDate = null;
        state.showUndated = false;
        state.calEventType = '';
        if (byId('cal-event-type')) byId('cal-event-type').value = '';
        syncCrossFilter();
    });
    byId('cal-axis')?.addEventListener('change', e => {
        state.calAxis = e.target.value;
        state.selectedDate = null;
        state.showUndated = false;
        syncCrossFilter();
    });
    byId('cal-period')?.addEventListener('change', e => {
        state.calPeriodDays = Number(e.target.value) || 90;
        renderCalendar();
    });
    byId('cal-event-type')?.addEventListener('change', e => {
        state.calEventType = e.target.value;
        state.selectedDate = null;
        syncCrossFilter();
    });
})();
