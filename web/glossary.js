'use strict';
(() => {
    const TERMS = {
        CONCEPTUAL_DISCOVERY: {
            category: 'Natureza da abstração',
            title: 'Descoberta conceitual',
            code: 'CONCEPTUAL_DISCOVERY',
            description: 'Proposição analítica que emerge da integração de múltiplos registros do acervo e que não está formulada explicitamente em nenhum registro isolado.',
        },
        CONCEPTUAL: {
            category: 'Natureza da abstração',
            title: 'Abstração conceitual',
            code: 'CONCEPTUAL',
            description: 'Síntese ou generalização conceitual proposta pelo modelo de linguagem a partir dos registros analisados.',
        },
        ABSTRACTION: {
            category: 'Natureza da abstração',
            title: 'Abstração analítica',
            code: 'abstraction',
            description: 'Formulação que abstrai princípios comuns entre registros mantendo vínculo com os trechos de origem.',
        },
        COMPLEMENTARIDADE: {
            category: 'Natureza da abstração',
            title: 'Complementaridade',
            code: 'complementaridade',
            description: 'Articulação entre registros distintos (muitas vezes distantes no espaço semântico) cujas ideias se completam ou geram tensão produtiva.',
        },
        'EXP-003': {
            category: 'Experimento analítico',
            title: 'Experimento BB-CORE-EXP-003',
            code: 'EXP-003',
            description: 'Investigação experimental de descoberta semântica e abstração intelectual sobre o acervo. Todas as saídas ficam fora do acervo canônico.',
        },
        SUSTAINED_CANDIDATE: {
            category: 'Confrontação automática',
            title: 'Sustentada (automático)',
            code: 'SUSTAINED_CANDIDATE',
            description: 'Candidata aprovada na confrontação crítica automática (Estratégia E): depende da integração entre registros, não é mero resumo e tem trechos verificados. Não equivale a validação científica.',
        },
        WEAK_OR_REDUNDANT: {
            category: 'Confrontação automática',
            title: 'Fraca ou redundante',
            code: 'WEAK_OR_REDUNDANT',
            description: 'Proposição classificada pela confrontação automática (E) como reformulação de um único registro ou sem síntese transversal nova.',
        },
        CONTESTED: {
            category: 'Confrontação automática',
            title: 'Contestada',
            code: 'CONTESTED',
            description: 'Proposição que apresentou objeções ou fragilidades relevantes durante o exame crítico.',
        },
        NOT_EXAMINED: {
            category: 'Confrontação automática',
            title: 'Não examinada',
            code: 'NOT_EXAMINED',
            description: 'Candidata ainda não submetida à etapa de confrontação crítica independente.',
        },
        NON_CANONICAL: {
            category: 'Estatuto epistêmico',
            title: 'Objeto analítico (não canônico)',
            code: 'FORA DO ACERVO CANÔNICO',
            description: 'Projeção reconstruível gerada para apoiar a exploração e a leitura do acervo. Não altera, substitui nem integra o acervo canônico imutável.',
        },
        STRATEGY_A: {
            category: 'Estratégia EXP-003',
            title: 'Estratégia A — Leitura integral do acervo',
            code: 'Estratégia A',
            description: 'Submete todos os registros em conjunto ao modelo de linguagem para buscar sínteses transversais amplas.',
        },
        STRATEGY_B: {
            category: 'Estratégia EXP-003',
            title: 'Estratégia B — Vizinhança semântica',
            code: 'Estratégia B',
            description: 'Agrupa registros próximos no espaço vetorial (embeddings) para buscar abstrações locais entre conteúdos afins.',
        },
        STRATEGY_C: {
            category: 'Estratégia EXP-003',
            title: 'Estratégia C — Transversal distante',
            code: 'Estratégia C',
            description: 'Cruza registros propositalmente distantes no espaço vetorial para evitar bolhas de similaridade e revelar complementaridades.',
        },
        STRATEGY_D: {
            category: 'Estratégia EXP-003',
            title: 'Estratégia D — Incremental com estado',
            code: 'Estratégia D',
            description: 'Processa os registros sequencialmente mantendo um estado externo determinístico para evitar deriva de contexto.',
        },
        STRATEGY_E: {
            category: 'Estratégia EXP-003',
            title: 'Estratégia E — Confrontação crítica',
            code: 'Estratégia E',
            description: 'Etapa independente que examina cada descoberta candidata contra critérios rigorosos para filtrar pseudo-descobertas redundantes.',
        },
        EXISTING_RECORD_AT_FIRST_EVENT: {
            category: 'Trajetória do registro',
            title: 'Registro preexistente ao primeiro acontecimento',
            code: 'EXISTING_RECORD_AT_FIRST_EVENT',
            description: 'Indica que o registro já existia no acervo quando seu primeiro acontecimento foi gravado. A base preservada nesse instante não reconstrói sua história anterior.',
        },
        FORMULATION_REVISED: {
            category: 'Trajetória do registro',
            title: 'Formulação revista',
            code: 'FORMULATION_REVISED',
            description: 'Acontecimento que atualiza a formulação corrente na trajetória mantendo a identidade do registro e preservando intacta a formulação original.',
        },
        SHA_256: {
            category: 'Integridade documental',
            title: 'Verificação SHA-256',
            code: 'SHA-256',
            description: 'Impressão digital criptográfica que detecta qualquer alteração no texto preservado desde o recebimento. Não comprova autoria nem veracidade científica.',
        },
    };

    const NORMALIZED_INDEX = new Map(
        Object.keys(TERMS).map(k => [k.toUpperCase(), k])
    );

    let popoverEl = null;
    let activeTrigger = null;

    function resolveTerm(rawKey) {
        if (!rawKey) return null;
        const normalized = String(rawKey).trim().toUpperCase();
        const canonicalKey = NORMALIZED_INDEX.get(normalized);
        if (canonicalKey) {
            return { key: canonicalKey, ...TERMS[canonicalKey] };
        }
        return null;
    }

    function buildEntry(rawKey, options = {}) {
        const found = resolveTerm(rawKey);
        if (found) return found;
        const fallbackText = String(rawKey || '').trim() || 'Termo não especificado';
        return {
            key: fallbackText,
            category: options.category || 'Rótulo livre do modelo',
            title: fallbackText,
            code: fallbackText,
            description: options.fallbackDescription
                || 'Classificação livre atribuída durante a síntese analítica experimental (EXP-003), sem categoria fixa pré-definida no esquema.',
        };
    }

    function formatNature(rawNature) {
        if (!rawNature) return 'Não informada';
        const found = resolveTerm(rawNature);
        if (!found) return rawNature;
        if (found.title.toLowerCase() === String(rawNature).trim().toLowerCase()) {
            return found.title;
        }
        return `${found.title} (${rawNature})`;
    }

    function ensurePopover() {
        if (popoverEl) return popoverEl;
        const pop = document.createElement('div');
        pop.id = 'bb-glossary-popover';
        pop.className = 'glossary-popover';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('aria-modal', 'false');
        pop.hidden = true;

        const head = document.createElement('div');
        head.className = 'glossary-popover-head';
        const cat = document.createElement('span');
        cat.className = 'eyebrow glossary-popover-cat';
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'glossary-popover-close';
        closeBtn.setAttribute('aria-label', 'Fechar explicação');
        closeBtn.textContent = '×';
        closeBtn.addEventListener('click', () => closePopover({ restoreFocus: true }));
        head.append(cat, closeBtn);

        const title = document.createElement('strong');
        title.className = 'glossary-popover-title';
        const code = document.createElement('code');
        code.className = 'glossary-popover-code';
        const desc = document.createElement('p');
        desc.className = 'glossary-popover-desc';

        const foot = document.createElement('div');
        foot.className = 'glossary-popover-foot';
        const link = document.createElement('a');
        link.href = '#sobre';
        link.className = 'glossary-popover-link';
        link.textContent = 'Ver glossário completo em Sobre →';
        link.addEventListener('click', e => {
            e.preventDefault();
            closePopover({ restoreFocus: false });
            if (window.BBViews?.open) window.BBViews.open('sobre');
            else location.hash = 'sobre';
            requestAnimationFrame(() => {
                const target = document.getElementById('sobre-glossario');
                if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        });
        foot.append(link);

        pop.append(head, title, code, desc, foot);
        document.body.append(pop);

        document.addEventListener('click', e => {
            if (pop.hidden) return;
            if (pop.contains(e.target)) return;
            if (activeTrigger && activeTrigger.contains(e.target)) return;
            closePopover({ restoreFocus: false });
        });
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && !pop.hidden) {
                closePopover({ restoreFocus: true });
            }
        });
        window.addEventListener('resize', () => {
            if (!pop.hidden && activeTrigger) positionPopover(activeTrigger);
        });

        popoverEl = pop;
        return pop;
    }

    function positionPopover(trigger) {
        if (!popoverEl || !trigger) return;
        const rect = trigger.getBoundingClientRect();
        const popRect = popoverEl.getBoundingClientRect();
        const margin = 12;
        let top = rect.bottom + 8;
        if (top + popRect.height > window.innerHeight - margin) {
            top = Math.max(margin, rect.top - popRect.height - 8);
        }
        let left = rect.left;
        if (left + popRect.width > window.innerWidth - margin) {
            left = Math.max(margin, window.innerWidth - popRect.width - margin);
        }
        popoverEl.style.top = `${Math.round(top)}px`;
        popoverEl.style.left = `${Math.round(left)}px`;
    }

    function openPopover(trigger, entry) {
        const pop = ensurePopover();
        if (activeTrigger === trigger && !pop.hidden) {
            closePopover({ restoreFocus: false });
            return;
        }
        activeTrigger = trigger;
        pop.querySelector('.glossary-popover-cat').textContent = entry.category;
        pop.querySelector('.glossary-popover-title').textContent = entry.title;
        const codeEl = pop.querySelector('.glossary-popover-code');
        if (entry.code && entry.code !== entry.title) {
            codeEl.textContent = entry.code;
            codeEl.hidden = false;
        } else {
            codeEl.hidden = true;
        }
        pop.querySelector('.glossary-popover-desc').textContent = entry.description;
        pop.hidden = false;
        positionPopover(trigger);
    }

    function closePopover({ restoreFocus = false } = {}) {
        if (!popoverEl || popoverEl.hidden) return;
        popoverEl.hidden = true;
        const prev = activeTrigger;
        activeTrigger = null;
        if (restoreFocus && prev?.focus) prev.focus();
    }

    function createTermButton(rawKey, options = {}) {
        const entry = buildEntry(rawKey, options);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'glossary-term' + (options.className ? ' ' + options.className : '');
        btn.setAttribute('aria-haspopup', 'dialog');
        btn.title = `Explicação: ${entry.title}`;

        const label = options.label !== undefined ? options.label : entry.title;
        const textSpan = document.createElement('span');
        textSpan.textContent = label;
        btn.append(textSpan);

        if (options.showCode && entry.code && entry.code !== label) {
            const codeSpan = document.createElement('code');
            codeSpan.className = 'glossary-inline-code';
            codeSpan.textContent = entry.code;
            btn.append(' ', codeSpan);
        }

        const icon = document.createElement('span');
        icon.className = 'glossary-icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = 'ⓘ';
        btn.append(' ', icon);

        btn.addEventListener('click', e => {
            e.stopPropagation();
            openPopover(btn, entry);
        });
        return btn;
    }

    function renderGlossarySection(container) {
        if (!container) return;
        container.replaceChildren();
        const heading = document.createElement('h2');
        heading.textContent = 'Glossário de termos e conceitos do sistema';
        const intro = document.createElement('p');
        intro.className = 'muted';
        intro.textContent = 'Significado dos códigos, classificações e estratégias usados nas descobertas analíticas, na trajetória dos registros e na verificação de integridade.';

        const grid = document.createElement('div');
        grid.className = 'glossary-grid';
        for (const [key, item] of Object.entries(TERMS)) {
            const card = document.createElement('article');
            card.className = 'glossary-item';
            card.id = 'glossary-' + key.toLowerCase();

            const cat = document.createElement('span');
            cat.className = 'eyebrow';
            cat.textContent = item.category;

            const title = document.createElement('h3');
            title.textContent = item.title;

            const desc = document.createElement('p');
            desc.textContent = item.description;

            card.append(cat, title);
            if (item.code && item.code !== item.title) {
                const code = document.createElement('code');
                code.className = 'glossary-inline-code';
                code.textContent = item.code;
                card.append(code);
            }
            card.append(desc);
            grid.append(card);
        }
        container.append(heading, intro, grid);
    }

    function hydrateDeclarativeTerms(root = document) {
        for (const node of root.querySelectorAll('[data-glossary]')) {
            const key = node.dataset.glossary;
            const label = node.dataset.glossaryLabel || node.textContent;
            const btn = createTermButton(key, { label });
            node.replaceChildren(btn);
        }
    }

    window.BBGlossary = {
        TERMS,
        resolveTerm,
        formatNature,
        createTermButton,
        renderGlossarySection,
        hydrateDeclarativeTerms,
        closePopover,
    };

    document.addEventListener('DOMContentLoaded', () => {
        hydrateDeclarativeTerms(document);
        renderGlossarySection(document.getElementById('sobre-glossario'));
    });
})();
