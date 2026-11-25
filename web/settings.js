'use strict';
(() => {
    const byId = id => document.getElementById(id);
    let currentPayload = null;

    function setSettingsNotice(msg, kind = 'info') {
        const el = byId('settings-notice');
        if (!el) return;
        if (!msg) {
            el.hidden = true;
            el.textContent = '';
            el.className = 'analytics-status-bar';
            return;
        }
        el.hidden = false;
        el.textContent = msg;
        el.className = `analytics-status-bar ${kind}`;
    }

    function populateForm(data) {
        currentPayload = data;
        const cfg = data.config;
        if (byId('cfg-profile')) byId('cfg-profile').value = cfg.profile;
        if (byId('cfg-investigator-model')) byId('cfg-investigator-model').value = cfg.investigator_model;
        if (byId('cfg-embed-model')) byId('cfg-embed-model').value = cfg.embed_model;
        if (byId('cfg-ref-temp')) byId('cfg-ref-temp').value = String(cfg.reference_temperature);
        if (byId('cfg-exp-temp')) byId('cfg-exp-temp').value = String(cfg.exploratory_temperature);
        if (byId('cfg-seed')) byId('cfg-seed').value = String(cfg.seed);
        if (byId('cfg-context-window')) byId('cfg-context-window').value = String(cfg.context_window);
        if (byId('cfg-conf-model')) byId('cfg-conf-model').value = cfg.confrontation_model;
        if (byId('cfg-conf-temp')) byId('cfg-conf-temp').value = String(cfg.confrontation_temperature);
        if (byId('cfg-conf-seed')) byId('cfg-conf-seed').value = String(cfg.confrontation_seed);
        if (byId('cfg-exp-reps')) byId('cfg-exp-reps').value = String(cfg.exploratory_repetitions);

        const enabled = new Set(cfg.enabled_strategies || []);
        for (const cb of document.querySelectorAll('input[name="cfg-strategy"]')) {
            cb.checked = enabled.has(cb.value);
        }

        const versionLine = byId('cfg-version-meta');
        if (versionLine) {
            versionLine.textContent = `Versão ${data.version} · atualizada em ${new Date(data.updated_at).toLocaleString('pt-BR')}`;
        }

        const histBox = byId('cfg-history-list');
        if (histBox) {
            histBox.replaceChildren();
            for (const h of data.history || []) {
                const row = document.createElement('div');
                row.className = 'cfg-history-item';
                const c = h.config || {};
                row.textContent = `v${h.version} · ${new Date(h.changed_at).toLocaleString('pt-BR')} · ${h.change_note || ''} (perfil=${c.profile}, T_ref=${c.reference_temperature}, T_exp=${c.exploratory_temperature}, seed=${c.seed})`;
                histBox.append(row);
            }
        }
    }

    async function loadSettings() {
        try {
            const res = await fetch('/api/settings/investigation', {credentials: 'same-origin'});
            if (!res.ok) throw Error(`Erro ao carregar configurações (${res.status})`);
            const data = await res.json();
            populateForm(data);
        } catch (err) {
            setSettingsNotice(err.message, 'error');
        }
    }

    function readFormPayload() {
        const strategies = [...document.querySelectorAll('input[name="cfg-strategy"]:checked')].map(el => el.value);
        return {
            profile: byId('cfg-profile')?.value || 'reference',
            investigator_model: byId('cfg-investigator-model')?.value.trim() || '',
            embed_model: byId('cfg-embed-model')?.value.trim() || '',
            reference_temperature: Number(byId('cfg-ref-temp')?.value),
            exploratory_temperature: Number(byId('cfg-exp-temp')?.value),
            seed: Number.parseInt(byId('cfg-seed')?.value || '42', 10),
            context_window: Number.parseInt(byId('cfg-context-window')?.value || '16384', 10),
            confrontation_model: byId('cfg-conf-model')?.value.trim() || '',
            confrontation_temperature: Number(byId('cfg-conf-temp')?.value),
            confrontation_seed: Number.parseInt(byId('cfg-conf-seed')?.value || '42', 10),
            exploratory_repetitions: Number.parseInt(byId('cfg-exp-reps')?.value || '3', 10),
            enabled_strategies: strategies,
        };
    }

    async function saveSettings(e) {
        e.preventDefault();
        const saveBtn = byId('cfg-save-btn');
        if (saveBtn) saveBtn.disabled = true;
        setSettingsNotice('Salvando configurações…', 'info');
        try {
            const payload = readFormPayload();
            const res = await fetch('/api/settings/investigation', {
                method: 'PUT',
                credentials: 'same-origin',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw Error(data.message || `Erro ao salvar (${res.status})`);
            populateForm(data);
            setSettingsNotice(`Configurações salvas (v${data.version}). Aplicadas às próximas execuções.`, 'success');
        } catch (err) {
            setSettingsNotice(err.message, 'error');
        } finally {
            if (saveBtn) saveBtn.disabled = false;
        }
    }

    async function resetSettings() {
        const resetBtn = byId('cfg-reset-btn');
        if (resetBtn) resetBtn.disabled = true;
        setSettingsNotice('Restaurando padrões…', 'info');
        try {
            const res = await fetch('/api/settings/investigation/reset', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {'Content-Type': 'application/json'},
                body: '{}',
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw Error(data.message || `Erro ao restaurar (${res.status})`);
            populateForm(data);
            setSettingsNotice(`Valores padrão restaurados (v${data.version}).`, 'success');
        } catch (err) {
            setSettingsNotice(err.message, 'error');
        } finally {
            if (resetBtn) resetBtn.disabled = false;
        }
    }

    function initTabs() {
        const tabBtns = document.querySelectorAll('.settings-tab');
        const panels = document.querySelectorAll('.settings-tabpanel');
        for (const btn of tabBtns) {
            btn.addEventListener('click', () => {
                const target = btn.dataset.tab;
                for (const b of tabBtns) {
                    const active = b.dataset.tab === target;
                    b.classList.toggle('active', active);
                    b.setAttribute('aria-selected', active ? 'true' : 'false');
                }
                for (const p of panels) {
                    p.hidden = p.dataset.tabPanel !== target;
                }
            });
        }
    }

    document.addEventListener('DOMContentLoaded', initTabs);
    document.addEventListener('bb-session-ready', loadSettings);
    document.addEventListener('bb-view-changed', e => {
        if (e.detail === 'configuracoes' && !currentPayload) loadSettings();
    });
    byId('settings-investigation-form')?.addEventListener('submit', saveSettings);
    byId('cfg-reset-btn')?.addEventListener('click', resetSettings);
})();
