'use strict';
(() => {
    const byId = id => document.getElementById(id);
    const SVG_NS = 'http://www.w3.org/2000/svg';

    const state = {
        data: null,
        viewMode: 'records', // 'records' (BB-CORE-UI-001 v0.2.0) | 'lexical' (referência v0.1.0)
        selectedInsightId: null,
        selectedDimensionId: null,
        selectedConnectionId: null,
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
        for (const a of (state.data?.record_network?.nodes || state.data?.graph?.anchors || [])) {
            m.set(a.id, a);
        }
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
            if (state.selectedConnectionId) {
                const conn = findConnection(state.selectedConnectionId);
                if (conn && ev.insight_id !== conn.source_id && ev.insight_id !== conn.target_id) {
                    return false;
                }
            }
            return true;
        });
    }

    function findConnection(connId) {
        if (!state.data?.record_network) return null;
        const cand = state.data.record_network.candidate_connections.find(c => c.id === connId);
        if (cand) return {...cand, isRegistered: false};
        const reg = state.data.record_network.registered_relations.find(r => r.id === connId);
        if (reg) return {...reg, source_id: reg.left_id, target_id: reg.right_id, isRegistered: true};
        return null;
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
        const hasFilter = Boolean(
            state.selectedInsightId || state.selectedDimensionId || state.selectedConnectionId
            || state.selectedDate || state.calEventType || state.showUndated
        );
        if (clearBtn) clearBtn.hidden = !hasFilter;
        document.dispatchEvent(new CustomEvent('bb-analytics-filter', {detail: activeInsightIdsFilter()}));
        renderSelectionBox();
        renderNetworkOrGraph();
        renderCalendar();
    }

    function renderSelectionBox() {
        const box = byId('analytics-selection-box');
        if (!box) return;
        box.replaceChildren();
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

    // Distribuição determinística orientada pelas conexões (sem sobreposição de cards 210x84)
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

            // Refinamento leve por forças determinísticas (atração entre conectados + repulsão mínima)
            const adj = new Map(connectedIds.map(id => [id, []]));
            for (const [u, v] of edges) {
                if (adj.has(u) && adj.has(v)) {
                    adj.get(u).push(v);
                    adj.get(v).push(u);
                }
            }
            for (let iter = 0; iter < 55; iter++) {
                const disp = new Map(connectedIds.map(id => [id, {dx: 0, dy: 0}]));
                for (let i = 0; i < connectedIds.length; i++) {
                    for (let j = i + 1; j < connectedIds.length; j++) {
                        const u = connectedIds[i], v = connectedIds[j];
                        const dx = pos[u].x - pos[v].x;
                        const dy = pos[u].y - pos[v].y;
                        const dist = Math.hypot(dx, dy) || 1;
                        const minDist = 250;
                        if (dist < minDist) {
                            const push = (minDist - dist) * 0.14;
                            disp.get(u).dx += (dx / dist) * push;
                            disp.get(u).dy += (dy / dist) * push * 0.7;
                            disp.get(v).dx -= (dx / dist) * push;
                            disp.get(v).dy -= (dy / dist) * push * 0.7;
                        }
                    }
                }
                for (const [u, v] of edges) {
                    if (!pos[u] || !pos[v]) continue;
                    const dx = pos[v].x - pos[u].x;
                    const dy = pos[v].y - pos[u].y;
                    const dist = Math.hypot(dx, dy) || 1;
                    if (dist > 290) {
                        const pull = (dist - 290) * 0.05;
                        disp.get(u).dx += (dx / dist) * pull;
                        disp.get(u).dy += (dy / dist) * pull;
                        disp.get(v).dx -= (dx / dist) * pull;
                        disp.get(v).dy -= (dy / dist) * pull;
                    }
                }
                for (const id of connectedIds) {
                    pos[id].x = Math.max(130, Math.min(W - 130, pos[id].x + disp.get(id).dx));
                    pos[id].y = Math.max(75, Math.min(isolatedIds.length ? 395 : H - 75, pos[id].y + disp.get(id).dy));
                }
            }
        }

        // Posicionar nós isolados sem sobreposição na faixa inferior
        if (isolatedIds.length) {
            const cols = Math.min(4, isolatedIds.length);
            const spacingX = Math.min(255, (W - 140) / Math.max(cols, 1));
            const startX = (W - spacingX * (cols - 1)) / 2;
            const baseY = connectedIds.length ? 495 : 220;
            isolatedIds.forEach((id, idx) => {
                const row = Math.floor(idx / cols);
                const col = idx % cols;
                pos[id] = {x: startX + col * spacingX, y: baseY + row * 105};
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
            ? `${nodes.length} registro(s) · ${cands.length} conexão(ões) candidata(s) (${net.concordant_connected_count} concordante(s), ${net.divergent_count} divergente(s)) · ${net.abstained_count} abstenção(ões) · ${topology.clusters.length} agrupamento(s) · ${topology.isolated_record_ids.length} isolado(s)`
            : `${nodes.length} registro(s) · sem resultados analíticos externos carregados (exibindo registros isolados e relações registradas)`;

        svg.replaceChildren();
        const bg = svgEl('rect', {width: 1100, height: 580, fill: '#f8fbfd'});
        svg.append(bg);

        if (!nodes.length) {
            svg.append(svgEl('text', {x: 550, y: 290, 'text-anchor': 'middle', fill: '#5d768a'}, 'Nenhum registro preservado no acervo.'));
            panel.replaceChildren(el('p', 'Sem registros para explorar.', 'muted'));
            return;
        }

        const viewport = svgEl('g', {id: 'net-viewport'});
        applyTransform(viewport);
        svg.append(viewport);

        const allEdges = [
            ...cands.map(c => [c.source_id, c.target_id]),
            ...regs.map(r => [r.left_id, r.right_id]),
        ];
        const pos = layoutRecordNodes(nodes, allEdges, topology);

        // Vizinhança ativa quando há seleção
        const neighborIds = new Set();
        if (state.selectedInsightId) {
            neighborIds.add(state.selectedInsightId);
            for (const c of cands) {
                if (c.source_id === state.selectedInsightId) neighborIds.add(c.target_id);
                if (c.target_id === state.selectedInsightId) neighborIds.add(c.source_id);
            }
            for (const r of regs) {
                if (r.left_id === state.selectedInsightId) neighborIds.add(r.right_id);
                if (r.right_id === state.selectedInsightId) neighborIds.add(r.left_id);
            }
        } else if (state.selectedConnectionId) {
            const conn = findConnection(state.selectedConnectionId);
            if (conn) {
                neighborIds.add(conn.source_id);
                neighborIds.add(conn.target_id);
            }
        } else if (state.selectedDate) {
            const af = activeInsightIdsFilter();
            if (af) af.insightIds.forEach(id => neighborIds.add(id));
        }
        const hasHighlight = neighborIds.size > 0;

        // 1. Conexões analíticas candidatas (largura uniforme — sem intensidade numérica arbitrária)
        for (const c of cands) {
            const p1 = pos[c.source_id];
            const p2 = pos[c.target_id];
            if (!p1 || !p2) continue;
            const isDivergent = c.stability === 'DIVERGENT_ORDER_DEPENDENT';
            const isActive = state.selectedConnectionId === c.id
                || (state.selectedInsightId && (c.source_id === state.selectedInsightId || c.target_id === state.selectedInsightId));
            const isDimmed = hasHighlight && !isActive && !(neighborIds.has(c.source_id) && neighborIds.has(c.target_id));

            const mx = (p1.x + p2.x) / 2;
            const my = (p1.y + p2.y) / 2 - 22;
            const path = svgEl('path', {
                class: 'net-edge' + (isDimmed ? ' dimmed' : ''),
                d: `M ${p1.x} ${p1.y} Q ${mx} ${my} ${p2.x} ${p2.y}`,
                stroke: isDivergent ? '#c97a16' : '#1c9b98',
                'stroke-width': state.selectedConnectionId === c.id ? 3.5 : 2.1,
                'stroke-dasharray': isDivergent ? '6 4' : '',
                opacity: isActive ? 0.95 : 0.65,
            });
            path.append(svgEl('title', {}, `${c.nature || 'Conexão analítica candidata'}\nEstabilidade: ${c.stability}`));
            path.addEventListener('click', e => {
                e.stopPropagation();
                state.selectedConnectionId = state.selectedConnectionId === c.id ? null : c.id;
                state.selectedInsightId = null;
                state.selectedDate = null;
                syncCrossFilter();
            });
            viewport.append(path);
        }

        // 2. Relações intelectuais registradas (distintas das conexões candidatas)
        for (const r of regs) {
            const p1 = pos[r.left_id];
            const p2 = pos[r.right_id];
            if (!p1 || !p2) continue;
            const mx = (p1.x + p2.x) / 2;
            const my = (p1.y + p2.y) / 2 + 28;
            const path = svgEl('path', {
                class: 'net-edge',
                d: `M ${p1.x} ${p1.y} Q ${mx} ${my} ${p2.x} ${p2.y}`,
                stroke: '#062a4f',
                'stroke-width': 3,
                opacity: 0.85,
            });
            path.append(svgEl('title', {}, `Relação intelectual registrada (${r.status}): ${r.rationale}`));
            path.addEventListener('click', e => {
                e.stopPropagation();
                state.selectedConnectionId = state.selectedConnectionId === r.id ? null : r.id;
                state.selectedInsightId = null;
                syncCrossFilter();
            });
            viewport.append(path);
        }

        // 3. Nós como cards compactos (210x84)
        const cardW = 210;
        const cardH = 84;
        const bridgeSet = new Set(topology.bridge_record_ids);
        const isolatedSet = new Set(topology.isolated_record_ids);

        for (const n of nodes) {
            const p = pos[n.id];
            if (!p) continue;
            const isSelected = state.selectedInsightId === n.id;
            const isIsolated = isolatedSet.has(n.id);
            const isBridge = bridgeSet.has(n.id);
            const isDimmed = hasHighlight && !neighborIds.has(n.id);

            const g = svgEl('g', {
                class: 'net-card-node' + (isDimmed ? ' dimmed' : ''),
                transform: `translate(${p.x - cardW / 2} ${p.y - cardH / 2})`,
            });
            g.append(svgEl('rect', {
                width: cardW,
                height: cardH,
                rx: 9,
                fill: isIsolated ? '#f4f7fa' : '#ffffff',
                stroke: isSelected ? '#0b5cab' : (isIsolated ? '#73899b' : '#183a56'),
                'stroke-width': isSelected ? 3 : 1.6,
                'stroke-dasharray': isIsolated ? '5 3' : '',
            }));

            const badge = isIsolated ? 'Sem conexões' : (isBridge ? 'Ponte · ' + (topology.degrees[n.id] || 0) + ' con.' : (topology.degrees[n.id] || 0) + ' conexão(ões)');
            const kindTxt = (kindLabels[n.kind] || n.status || '').slice(0, 20);
            g.append(svgEl('text', {x: 11, y: 19, fill: '#47657d', 'font-size': 10, 'font-weight': 700}, `${kindTxt} · ${n.id.slice(0, 6)}`));
            g.append(svgEl('text', {x: cardW - 10, y: 19, 'text-anchor': 'end', fill: isIsolated ? '#6b8194' : '#0b5cab', 'font-size': 10, 'font-weight': 600}, badge));

            // Quebrar título em até 2 linhas legíveis dentro do card
            const words = n.title.split(/\s+/);
            let line1 = '', line2 = '';
            for (const w of words) {
                if ((line1 + ' ' + w).trim().length <= 27) {
                    line1 = (line1 + ' ' + w).trim();
                } else if ((line2 + ' ' + w).trim().length <= 27) {
                    line2 = (line2 + ' ' + w).trim();
                } else {
                    line2 = line2.slice(0, 24) + '…';
                    break;
                }
            }
            g.append(svgEl('text', {x: 11, y: 43, fill: '#0e2438', 'font-size': 12.5, 'font-weight': 600}, line1));
            if (line2) g.append(svgEl('text', {x: 11, y: 60, fill: '#0e2438', 'font-size': 12.5, 'font-weight': 600}, line2));
            g.append(svgEl('title', {}, `${n.title}\nID: ${n.id}\n${badge}`));

            g.addEventListener('click', e => {
                e.stopPropagation();
                state.selectedInsightId = state.selectedInsightId === n.id ? null : n.id;
                state.selectedConnectionId = null;
                state.selectedDate = null;
                syncCrossFilter();
            });
            viewport.append(g);
        }

        // Painel lateral contextualizado (sem despejar listas longas sem seleção)
        panel.replaceChildren();
        const recById = recordMap();

        if (state.selectedConnectionId) {
            const conn = findConnection(state.selectedConnectionId);
            if (conn) {
                const a = recById.get(conn.source_id);
                const b = recById.get(conn.target_id);
                panel.append(el('p', `${a ? a.title : conn.source_id} ↔ ${b ? b.title : conn.target_id}`));
                if (conn.isRegistered) {
                    panel.append(el('span', 'Relação intelectual registrada', 'net-badge registered'));
                    panel.append(el('p', conn.rationale));
                    panel.append(el('p', 'Contraponto: ' + conn.counterpoint, 'muted'));
                } else {
                    panel.append(el('span', 'Proposição analítica candidata (não reconhecida)', 'net-badge'));
                    panel.append(el('span', conn.stability === 'DIVERGENT_ORDER_DEPENDENT' ? 'Divergente entre (A,B) e (B,A)' : 'Concordante nas duas ordens', 'net-badge' + (conn.stability === 'DIVERGENT_ORDER_DEPENDENT' ? ' divergent' : '')));
                    panel.append(el('p', 'Mecanismo: ' + conn.mechanism, 'muted'));
                    if (conn.nature) panel.append(el('p', 'Natureza proposta: ' + conn.nature));
                    for (const [dirLabel, side] of [['Ordem direta (A → B)', conn.forward_ab], ['Ordem inversa (B → A)', conn.reverse_ba]]) {
                        const sec = el('details');
                        sec.open = side.connection_proposed;
                        sec.append(el('summary', `${dirLabel}: ${side.connection_proposed ? 'Conexão proposta' : 'Abstenção'}`));
                        if (side.connection_proposed) {
                            if (side.justification) sec.append(el('p', side.justification));
                            for (const ex of [...(side.excerpts_a || []), ...(side.excerpts_b || [])]) {
                                const q = el('div', `${ex.exact_match ? '✓' : '⚠'} "${ex.excerpt}"`, 'net-excerpt' + (ex.exact_match ? '' : ' unverified'));
                                sec.append(q);
                            }
                        } else if (side.abstention_reason) {
                            sec.append(el('p', 'Abstenção: ' + side.abstention_reason));
                        }
                        if (side.limitations?.length) {
                            sec.append(el('p', 'Limitações: ' + side.limitations.join(' · '), 'muted'));
                        }
                        panel.append(sec);
                    }
                }
                return;
            }
        }

        if (state.selectedInsightId) {
            const neighbors = cands.filter(c => c.source_id === state.selectedInsightId || c.target_id === state.selectedInsightId);
            panel.append(el('h4', `Vizinhança direta (${neighbors.length})`));
            if (!neighbors.length) {
                panel.append(el('p', 'Este registro permanece isolado (sem conexões analíticas propostas ou relações registradas).', 'muted'));
            } else {
                for (const c of neighbors) {
                    const otherId = c.source_id === state.selectedInsightId ? c.target_id : c.source_id;
                    const other = recById.get(otherId);
                    const item = el('div', undefined, 'graph-link-item');
                    const head = el('div', undefined, 'graph-link-head');
                    head.append(
                        el('strong', other ? other.title : otherId),
                        el('small', c.stability === 'DIVERGENT_ORDER_DEPENDENT' ? 'divergente' : 'concordante')
                    );
                    head.addEventListener('click', () => {
                        state.selectedConnectionId = c.id;
                        state.selectedInsightId = null;
                        syncCrossFilter();
                    });
                    item.append(head);
                    if (c.nature) item.append(el('p', c.nature, 'muted'));
                    panel.append(item);
                }
            }
            return;
        }

        // Sem seleção: síntese quantitativa e semiótica do universo
        panel.append(el('h4', 'Síntese do universo analisado'));
        const statsList = el('ul');
        statsList.append(
            el('li', `Registros intelectuais (nós): ${nodes.length}`),
            el('li', `Conexões analíticas candidatas: ${cands.length} (${net.concordant_connected_count} concordantes, ${net.divergent_count} divergentes)`),
            el('li', `Pares com abstenção concordante: ${net.abstained_count}`),
            el('li', `Relações intelectuais registradas: ${regs.length}`),
            el('li', `Agrupamentos topológicos emergentes: ${topology.clusters.length}`),
            el('li', `Registros isolados: ${topology.isolated_record_ids.length}`)
        );
        panel.append(statsList);
        if (net.mechanism) {
            panel.append(el('p', `Fonte analítica: ${net.mechanism}. Clique em qualquer card ou conexão para inspecionar vizinhança e fundamentos.`, 'muted'));
        }
    }

    function renderLexicalGraph() {
        const svg = byId('analytics-graph');
        const legend = byId('net-legend');
        const panel = byId('net-panel-body');
        const summaryLine = byId('net-summary-line');
        if (!svg || !state.data) return;

        legend.replaceChildren(
            el('span', '○ Âncora (registro)'),
            el('span', '◌ Registro isolado'),
            el('span', '◎ Dimensão lexical')
        );
        summaryLine.textContent = `Referência lexical experimental (${state.data.methodology.version}) · ${state.data.graph.inferred_associations.length} associação(ões)`;

        const {anchors, dimensions, inferred_associations: assocs} = state.data.graph;
        svg.replaceChildren();
        svg.append(svgEl('rect', {width: 1100, height: 580, fill: '#f8fbfd'}));
        svg.append(svgEl('text', {x: 80, y: 38, class: 'graph-caption'}, 'Registros intelectuais (âncoras)'));
        svg.append(svgEl('text', {x: 730, y: 38, class: 'graph-caption'}, 'Dimensões conceituais (léxico)'));

        const anchorPos = {};
        anchors.forEach((a, i) => {
            anchorPos[a.id] = graphPoint(i, anchors.length, 230, 290, 185);
        });
        const dimPos = {};
        dimensions.forEach((d, i) => {
            dimPos[d.id] = {...graphPoint(i, dimensions.length, 830, 290, 200), color: d.color};
        });
        const maxDimCount = Math.max(...dimensions.map(d => d.record_count), 1);
        const activeFilter = activeInsightIdsFilter();
        const highlightedIds = activeFilter ? new Set(activeFilter.insightIds) : null;

        for (const assoc of assocs) {
            const src = anchorPos[assoc.insight_id];
            const dst = dimPos[assoc.dimension_id];
            if (!src || !dst) continue;
            const isDimmed = (state.selectedDimensionId && state.selectedDimensionId !== assoc.dimension_id)
                || (highlightedIds && !highlightedIds.has(assoc.insight_id));
            const path = svgEl('path', {
                class: 'graph-edge' + (isDimmed ? ' dimmed' : ''),
                d: `M ${src.x} ${src.y} C ${src.x + 230} ${src.y}, ${dst.x - 230} ${dst.y}, ${dst.x} ${dst.y}`,
                stroke: dst.color,
                'stroke-width': (1.5 + assoc.normalized_weight * 6).toFixed(2),
                opacity: (0.22 + assoc.normalized_weight * 0.58).toFixed(2),
            });
            path.append(svgEl('title', {}, `${assoc.dimension_label} · pontuação absoluta ${assoc.absolute_score}`));
            svg.append(path);
        }

        for (const a of anchors) {
            const p = anchorPos[a.id];
            const isDimmed = highlightedIds && !highlightedIds.has(a.id);
            const g = svgEl('g', {class: 'graph-node-svg' + (isDimmed ? ' dimmed' : ''), transform: `translate(${p.x} ${p.y})`});
            g.append(svgEl('circle', {r: 32, fill: a.unclassified ? '#f3f7fa' : '#fff', stroke: a.unclassified ? '#6b8194' : '#062a4f', 'stroke-width': 2.6, 'stroke-dasharray': a.unclassified ? '4 3' : ''}));
            g.append(svgEl('text', {'text-anchor': 'middle', y: -2}, a.title.length > 16 ? a.title.slice(0, 15) + '…' : a.title));
            g.append(svgEl('text', {class: 'node-subtitle', 'text-anchor': 'middle', y: 13}, a.unclassified ? 'isolado' : a.matched_dimensions.length + ' dim.'));
            g.addEventListener('click', () => {
                state.selectedInsightId = state.selectedInsightId === a.id ? null : a.id;
                state.selectedDimensionId = null;
                syncCrossFilter();
            });
            svg.append(g);
        }

        for (const d of dimensions) {
            const p = dimPos[d.id];
            const radius = 28 + (d.record_count / maxDimCount) * 26;
            const g = svgEl('g', {class: 'graph-node-svg', transform: `translate(${p.x} ${p.y})`});
            g.append(svgEl('circle', {r: radius, fill: '#fff', stroke: d.color, 'stroke-width': 3}));
            g.append(svgEl('text', {'text-anchor': 'middle', y: -2}, d.label.length > 22 ? d.label.slice(0, 21) + '…' : d.label));
            g.append(svgEl('text', {class: 'node-subtitle', 'text-anchor': 'middle', y: 14}, d.record_count + ' reg.'));
            g.addEventListener('click', () => {
                state.selectedDimensionId = state.selectedDimensionId === d.id ? null : d.id;
                state.selectedInsightId = null;
                syncCrossFilter();
            });
            svg.append(g);
        }

        panel.replaceChildren(el('h4', 'Associações lexicais (referência v0.1.0)'));
        const recById = recordMap();
        for (const a of assocs.slice(0, 12)) {
            const rec = recById.get(a.insight_id);
            const item = el('div', undefined, 'graph-link-item');
            const head = el('div', undefined, 'graph-link-head');
            head.append(el('strong', (rec ? rec.title.slice(0, 28) + '…' : a.insight_id.slice(0, 8)) + ' → ' + a.dimension_label), el('small', 'pts: ' + a.absolute_score));
            item.append(head);
            panel.append(item);
        }
    }

    function renderNetworkOrGraph() {
        const controls = byId('net-controls');
        if (controls) controls.hidden = state.viewMode !== 'records';
        if (state.viewMode === 'records') {
            renderRecordNetwork();
        } else {
            renderLexicalGraph();
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
        start.setDate(start.getDate() - start.getDay());

        const maxDay = Math.max(...[...byDay.values()].map(b => b.total), 1);
        container.replaceChildren();

        const monthNames = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
        const board = el('div', undefined, 'cal-board');
        const monthsRow = el('div', undefined, 'cal-months');
        const labels = el('div', undefined, 'cal-day-labels');
        for (const name of ['', 'Seg', '', 'Qua', '', 'Sex', '']) {
            labels.append(el('span', name));
        }
        const grid = el('div', undefined, 'cal-grid');
        let lastMonth = -1;
        let weekIndex = 0;
        for (let d = new Date(start); d <= today; d.setDate(d.getDate() + 1)) {
            if (d.getDay() === 0) {
                const m = d.getMonth();
                const mLabel = (m !== lastMonth && (weekIndex > 0 || d.getDate() <= 7)) ? monthNames[m] : '';
                monthsRow.append(el('span', mLabel));
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
                state.selectedInsightId = null;
                state.selectedDimensionId = null;
                state.selectedConnectionId = null;
                syncCrossFilter();
            });
            grid.append(cell);
        }
        const body = el('div', undefined, 'cal-body');
        body.append(labels, grid);
        const footer = el('div', undefined, 'cal-footer');
        footer.append(el('span', 'Menos'));
        for (const lvl of ['', 'l1', 'l2', 'l3', 'l4']) {
            footer.append(el('i', undefined, 'cal-legend-box' + (lvl ? ' ' + lvl : '')));
        }
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
            const net = data.record_network;
            meta.textContent = `${m.record_universe_count} registro(s) · ${m.event_universe_count} acontecimento(s) · ${net?.candidate_connections?.length || 0} conexão(ões) candidata(s) · calculado em ${m.computed_at}`;
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
            renderNetworkOrGraph();
            renderCalendar();
        } catch (err) {
            if (meta) meta.textContent = err.message;
        }
    }

    // Pan & Zoom na área SVG da rede de registros
    const svgElNode = byId('analytics-graph');
    if (svgElNode) {
        let dragging = false, sx = 0, sy = 0;
        svgElNode.addEventListener('mousedown', e => {
            if (state.viewMode !== 'records' || e.target !== svgElNode && e.target.tagName !== 'rect') return;
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
        svgElNode.addEventListener('wheel', e => {
            if (state.viewMode !== 'records') return;
            e.preventDefault();
            state.zoom = Math.max(0.55, Math.min(2.2, state.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
            applyTransform(byId('net-viewport'));
        }, {passive: false});
    }

    byId('net-zoom-in')?.addEventListener('click', () => {
        state.zoom = Math.min(2.2, state.zoom * 1.15);
        applyTransform(byId('net-viewport'));
    });
    byId('net-zoom-out')?.addEventListener('click', () => {
        state.zoom = Math.max(0.55, state.zoom * 0.85);
        applyTransform(byId('net-viewport'));
    });
    byId('net-zoom-reset')?.addEventListener('click', () => {
        state.zoom = 1;
        state.panX = 0;
        state.panY = 0;
        applyTransform(byId('net-viewport'));
    });
    byId('net-expand')?.addEventListener('click', () => {
        state.expanded = !state.expanded;
        byId('net-layout')?.classList.toggle('expanded', state.expanded);
        byId('net-expand').textContent = state.expanded ? '⤡ Recolher' : '⤢ Expandir';
    });

    byId('net-mode-records')?.addEventListener('click', () => {
        state.viewMode = 'records';
        state.selectedDimensionId = null;
        byId('net-mode-records')?.classList.add('active');
        byId('net-mode-lexical')?.classList.remove('active');
        syncCrossFilter();
    });
    byId('net-mode-lexical')?.addEventListener('click', () => {
        state.viewMode = 'lexical';
        state.selectedConnectionId = null;
        byId('net-mode-lexical')?.classList.add('active');
        byId('net-mode-records')?.classList.remove('active');
        syncCrossFilter();
    });

    document.addEventListener('bb-session-ready', loadAnalytics);
    byId('analytics-refresh')?.addEventListener('click', loadAnalytics);
    byId('analytics-clear')?.addEventListener('click', () => {
        state.selectedInsightId = null;
        state.selectedDimensionId = null;
        state.selectedConnectionId = null;
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
        state.calPeriodDays = Number(e.target.value) || 365;
        renderCalendar();
    });
    byId('cal-event-type')?.addEventListener('change', e => {
        state.calEventType = e.target.value;
        state.selectedDate = null;
        syncCrossFilter();
    });
})();
