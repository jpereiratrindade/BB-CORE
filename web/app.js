'use strict';
const $ = id => document.getElementById(id);
const Reader = (() => {
    const dialog = $('reader-dialog');
    const scroll = dialog.querySelector('.reader-scroll');
    let opener = null;
    let version = 0;

    function close({restoreFocus = true} = {}) {
        version++;
        if (!dialog.open) return;
        dialog.close();
        document.body.classList.remove('reader-open');
        if (restoreFocus && opener?.isConnected && opener.getClientRects().length) {
            opener.focus({preventScroll: true});
        }
        opener = null;
    }

    $('reader-close').addEventListener('click', () => close());
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    dialog.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const controls = [...dialog.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])')]
            .filter(control => control.getClientRects().length);
        const first = controls[0];
        const last = controls.at(-1);
        if (!first) { event.preventDefault(); return; }
        if (event.shiftKey && (document.activeElement === first || document.activeElement === $('reader-title'))) {
            event.preventDefault(); last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault(); first.focus();
        }
    });
    document.addEventListener('bb-view-changed', () => close({restoreFocus: false}));
    return {
        open(panel, title, trigger) {
            const ticket = ++version;
            if (!dialog.open) {
                const candidate = trigger instanceof HTMLElement ? trigger : document.activeElement;
                opener = candidate && !dialog.contains(candidate) && candidate.getClientRects().length
                    ? candidate : document.querySelector('.sidebar a[aria-current="page"]');
            }
            for (const content of dialog.querySelectorAll('[data-reader-panel]')) content.hidden = content.id !== panel;
            $('reader-kind').textContent = panel === 'detail' ? 'REGISTRO INTELECTUAL' : 'FONTE DOCUMENTAL';
            $('reader-title').textContent = title;
            if (!dialog.open) dialog.showModal();
            document.body.classList.add('reader-open');
            scroll.scrollTop = 0;
            $('reader-title').focus({preventScroll: true});
            return ticket;
        },
        current: ticket => dialog.open && ticket === version,
        title: title => { $('reader-title').textContent = title; },
        close,
    };
})();
const statuses = {INFERRED_CANDIDATE:'Proposta para revisão',REPORTED:'Relato atribuído',DISPUTED:'Em contestação',WITHDRAWN:'Retirado'};
const names = {work_state:'Estado do trabalho',formulation_origin:'Origem da formulação',confirmed_by_declared:'Confirmado por (declarado)',confirmed_at:'Confirmação registrada em',supersedes_id:'Revisa o registro',external_id:'Identificador',document_version:'Versão do documento',record_kind:'Tipo de registro',review_state_declared:'Estado declarado',coverage:'Abrangência',related_document:'Documento relacionado',desired_destination:'Destinação desejada',noese_registration_verified:'Registro no NOESE verificado',missing:'Lacunas',why_matters:'Por que preservar',origin:'Origem',conversation_date_declared:'Data declarada da conversa',conversation_id:'Identificador da conversa',authorship_verified:'Autoria verificada',trigger:'Gatilho',previous_position:'Posição anterior',turning_point:'Ponto de mudança'};
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function value(x){const labels={CONCEPTUAL_FINDING:'Achado conceitual',METHODOLOGICAL_DECISION:'Decisão metodológica',OPEN_QUESTION:'Questão aberta',EMPIRICAL_REPORT:'Relato empírico',PROPOSED:'Proposta',ADOPTED:'Decisão adotada no trabalho',OPEN:'Em aberto',REPORTED:'Relato atribuído',HUMAN_FORMULATION:'Formulação humana',DOCUMENT_EXCERPT:'Trecho documental'};if(typeof x==='string'&&labels[x])return labels[x];if(x==='conceptual_finding_and_methodological_decision')return 'Achado conceitual e decisão metodológica';if(x===null)return 'Não informado';if(typeof x==='boolean')return x?'Sim':'Não';if(Array.isArray(x))return x.map(value).join('\n');if(typeof x==='object')return Object.entries(x).map(([k,v])=>(names[k]||k)+': '+value(v)).join('\n');return String(x);}
function fields(data){const dl=node('dl');for(const [k,v] of Object.entries(data||{})){dl.append(node('dt',names[k]||k),node('dd',value(v)));}return dl;}
function date(x){return new Date(x).toLocaleString('pt-BR');}
async function get(path){const r=await fetch(path,{credentials:'same-origin'});if(!r.ok)throw Error(r.status===401?'A sessão expirou. Recarregue a página para consultar novamente.':'Não foi possível consultar o acervo ('+r.status+').');return r.json();}
function section(container,title,text){container.append(node('h4',title),node('p',text));}
async function show(record,button){const ticket=Reader.open('detail',record.title||'Carregando registro…',button);$('detail').replaceChildren(node('p','Recuperando contexto…'));try{const d=await get('/api/insights/'+encodeURIComponent(record.id)+'/context');if(!Reader.current(ticket))return;Reader.title(d.title);const box=$('detail');box.replaceChildren();box.append(node('span',d.elaboration?value(d.elaboration.kind)+' · '+value(d.elaboration.work_state):(statuses[d.status]||d.status),'tag'),node('h3',d.title));if(d.elaboration){box.append(fields({record_kind:d.elaboration.kind,work_state:d.elaboration.work_state,formulation_origin:d.elaboration.formulation_origin,confirmed_by_declared:d.elaboration.confirmed_by_declared,confirmed_at:d.elaboration.confirmed_at,supersedes_id:d.elaboration.supersedes_id}));}box.append(fields({external_id:d.context.external_id||d.id,document_version:d.context.document_version||d.version}));if(d.elaboration){const revise=node('button','Preparar revisão deste registro','button outline');revise.type='button';revise.addEventListener('click',()=>{Reader.close({restoreFocus:false});document.dispatchEvent(new CustomEvent('bb-revise-record',{detail:d}));});box.append(revise);}section(box,'Formulação preservada',d.claim);if(d.context.why_matters)section(box,'Por que preservar',d.context.why_matters);box.append(node('h4','Gênese da elaboração'),fields(d.genesis));const context={...d.context};delete context.why_matters;delete context.external_id;delete context.document_version;box.append(node('h4','Contexto e referências'),fields(context));section(box,'Alcance e limitações',d.limitations);box.append(node('h4','Fontes preservadas'));for(const s of d.sources){box.append(node('p',s.origin),node('blockquote',s.quote));if(s.version_id){const source=node('button','Abrir documento de origem','button outline');source.type='button';source.addEventListener('click',()=>{Reader.close({restoreFocus:false});document.dispatchEvent(new CustomEvent('bb-open-document',{detail:s.version_id}));});box.append(source);}const details=node('details');details.append(node('summary','Ler fonte integral'),node('pre',s.body));box.append(details);const hash=node('details');hash.append(node('summary','Identificação da fonte'),node('pre','SHA-256: '+s.sha256+'\nAutoria declarada: '+(s.author||'Não informada')+'\nFonte: '+(s.coverage==='USER_SUPPLIED_FULL'?'Documento integral fornecido':s.coverage)));box.append(hash);}if(d.relations.length)section(box,'Relações candidatas',value(d.relations));const technical=node('details');technical.append(node('summary','Dados completos do registro'),node('pre',JSON.stringify(d,null,2)));box.append(technical);box.append(node('p',d.integrity==='VERIFIED_LOCAL_BYTES'?'Texto recuperado e integridade local verificada.':'Contexto recuperado.','muted'));}catch(e){if(Reader.current(ticket))$('detail').replaceChildren(node('p',e.message));}}
let generation=0;
async function load(){const current=++generation;$('refresh').disabled=true;$('notice').textContent='Consultando acervo…';try{const q=$('query').value.trim();const data=await get('/api/insights'+(q?'?q='+encodeURIComponent(q):''));if(current!==generation)return;$('items').replaceChildren();if(!data.items.length){$('items').append(node('p',q?'Nenhum registro encontrado para esta busca.':'Nenhum achado registrado no acervo.'));$('notice').textContent=q?'Tente outros termos do título ou da formulação.':'O acervo está pronto para receber registros.';return;}for(const x of data.items){const b=node('button',undefined,'item');b.type='button';b.setAttribute('aria-haspopup','dialog');b.append(node('span',x.kind?value(x.kind)+' · '+value(x.work_state):(statuses[x.status]||x.status),'tag'),node('strong',x.title),node('small','Registrado em '+date(x.created_at)),node('span','Abrir registro ↗','card-action'));b.addEventListener('click',()=>show(x,b));$('items').append(b);}$('notice').textContent=data.items.length+' registro(s) nesta consulta.';}catch(e){$('notice').textContent=e.message;}finally{if(current===generation)$('refresh').disabled=false;}}
async function start(){try{const session=await fetch('/api/local-session',{method:'POST',credentials:'same-origin'});if(!session.ok)throw Error('Consulta disponível apenas pelo endereço local deste computador.');document.dispatchEvent(new Event('bb-session-ready'));const h=await get('/health');$('connection').textContent=h.status==='READY'?'● Serviço disponível':'Verificar serviço';$('integrity').textContent=h.storage.integrity==='VERIFIED'?'Verificada':'Verificar';$('source-count').textContent=(h.storage.sources_checked+(h.storage.document_contents_checked||0))+' fonte(s) · '+(h.storage.hash_mismatches+(h.storage.document_hash_mismatches||0))+' divergência(s) · '+(h.storage.document_anchor_failures||0)+' falha(s) de âncora';const data=await get('/api/insights');$('count').textContent=data.items.length+(data.items.length===30?'+':'');$('count-note').textContent=data.items.length===30?'Exibindo os 30 registros mais recentes':'Achados preservados no acervo';await load();}catch(e){$('connection').textContent='Consulta indisponível';$('connection').classList.add('error');$('notice').textContent=e.message;}}
$('search-form').addEventListener('submit',e=>{e.preventDefault();load();});$('refresh').addEventListener('click',start);start();
