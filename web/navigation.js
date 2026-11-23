'use strict';
(() => {
    const routes = {
        acervo: 'Acervo de achados',
        documentos: 'Documentos',
        recebimento: 'Receber documentos',
        elaboracao: 'Elaborar registro',
        integridade: 'Integridade e origem',
        sobre: 'Sobre o BB-CORE',
    };
    let current = null;

    function render({focus = true} = {}) {
        const fragment = location.hash.slice(1);
        // O salto de acessibilidade não troca a funcionalidade em uso.
        if (fragment === 'main' && current) return;
        const view = Object.hasOwn(routes, fragment) ? fragment : 'acervo';
        if (view === current) return;
        current = view;
        if (view === 'elaboracao') document.getElementById('elaboration-nav').hidden = false;
        for (const panel of document.querySelectorAll('[data-view]')) {
            panel.hidden = panel.dataset.view !== view;
        }
        for (const link of document.querySelectorAll('.sidebar nav a')) {
            const active = link.hash === '#' + view;
            link.classList.toggle('active', active);
            if (active) link.setAttribute('aria-current', 'page');
            else link.removeAttribute('aria-current');
        }
        document.getElementById('page-name').textContent = routes[view];
        document.title = 'BB-CORE · ' + routes[view];
        if (focus) {
            const panel = document.querySelector('[data-view="' + view + '"]');
            const heading = panel.querySelector('h1, h2');
            heading.tabIndex = -1;
            heading.focus({preventScroll: true});
            window.scrollTo({top: 0, behavior: 'instant'});
        }
        document.dispatchEvent(new CustomEvent('bb-view-changed', {detail: view}));
    }

    window.BBViews = {
        open(view) {
            if (!Object.hasOwn(routes, view)) return;
            if (location.hash === '#' + view) render();
            else { location.hash = view; render(); }
        },
        current: () => current,
    };
    window.addEventListener('hashchange', () => render());
    render({focus: false});
})();
