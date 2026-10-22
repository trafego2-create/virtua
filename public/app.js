"use strict";
// Virtua — telas do sistema de cobranças (sem framework; rota pelo #)

const $ = (s, el = document) => el.querySelector(s);
const tela = $("#tela");
let EU = null;

const ROTULO = {
  ativa_em_dia: "Ativa · em dia", ativa_em_atraso: "Ativa · em atraso", inadimplencia_antiga: "Inadimplência antiga",
  paga: "Paga", vencida: "Vencida", a_vencer: "A vencer", renegociada: "Renegociada", cancelada: "Cancelada",
  administrador: "Administrador", gestor: "Gestor", financeiro: "Financeiro", consulta: "Consulta",
};
const PODE_EDITAR = () => ["administrador", "financeiro"].includes(EU.perfil);

// ---------- utilidades ----------
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const brl = v => Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const dataBR = v => (v ? String(v).slice(0, 10).split("-").reverse().join("/") : "");
const quando = v => (v ? new Date(v).toLocaleString("pt-BR") : "");
const selo = s => `<span class="selo s-${esc(s)}">${esc(ROTULO[s] || s)}</span>`;
const hoje = () => new Date().toISOString().slice(0, 10);

async function api(metodo, url, corpo) {
  const r = await fetch(url, {
    method: metodo,
    headers: { "x-virtua": "1", ...(corpo ? { "content-type": "application/json" } : {}) },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  if (r.status === 401 && url !== "/api/login") { EU = null; iniciar(); throw new Error("Faça login"); }
  if (!r.ok) {
    let msg = "Erro " + r.status;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* sem corpo */ }
    throw new Error(typeof msg === "string" ? msg : "Dados inválidos");
  }
  return r.status === 204 ? null : r.json();
}

function avisar(msg) {
  const a = $("#aviso");
  a.textContent = msg;
  a.classList.add("mostra");
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => a.classList.remove("mostra"), 2600);
}

// Diálogo genérico: campos = [{nome, rotulo, tipo, valor, opcoes}] → resolve com os valores ou null
function perguntar(titulo, campos, botao = "Salvar", ao_enviar) {
  const d = $("#dialogo"), f = $("#dialogo-form");
  f.innerHTML = `<h3>${esc(titulo)}</h3>` + campos.map(c => {
    if (c.tipo === "texto-fixo") return `<p class="sub">${c.html}</p>`;
    const id = "f_" + c.nome;
    let ctrl;
    if (c.tipo === "select") ctrl = `<select id="${id}" name="${c.nome}">${c.opcoes.map(([v, t]) => `<option value="${esc(v)}"${v === c.valor ? " selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
    else if (c.tipo === "textarea") ctrl = `<textarea id="${id}" name="${c.nome}" rows="3">${esc(c.valor)}</textarea>`;
    else ctrl = `<input id="${id}" name="${c.nome}" type="${c.tipo || "text"}" value="${esc(c.valor ?? "")}"${c.tipo === "number" ? ' step="0.01"' : ""}>`;
    return `<label class="campo"><span>${esc(c.rotulo)}</span>${ctrl}</label>`;
  }).join("") + `<div class="erro-msg"></div><div class="acoes"><button class="btn" value="cancelar" formnovalidate>Cancelar</button><button class="btn prim" value="ok">${esc(botao)}</button></div>`;
  return new Promise(resolve => {
    f.onsubmit = async ev => {
      if (ev.submitter?.value !== "ok") { d.close(); resolve(null); return; }
      ev.preventDefault();
      const vals = Object.fromEntries(new FormData(f));
      try {
        if (ao_enviar) await ao_enviar(vals);
        d.close();
        resolve(vals);
      } catch (e) { $(".erro-msg", f).textContent = e.message; }
    };
    d.onclose = () => resolve(null);
    d.showModal();
    f.querySelector("input,select,textarea")?.focus();
  });
}

// ---------- login ----------
async function iniciar() {
  const r = await api("GET", "/api/me");
  if (!r.usuario) {
    $("#topo").hidden = true;
    return r.primeiro_acesso ? telaPrimeiroAcesso() : telaLogin();
  }
  EU = r.usuario;
  $("#topo").hidden = false;
  $("#eu-nome").textContent = `${EU.nome} · ${ROTULO[EU.perfil]}`;
  rotear();
}

function telaLogin() {
  tela.innerHTML = `<form class="login" id="f-login"><h1>Cobranças</h1><p class="sub">Entre com seu e-mail e senha.</p>
    <label class="campo"><span>E-mail</span><input name="email" type="email" autocomplete="username" required></label>
    <label class="campo"><span>Senha</span><input name="senha" type="password" autocomplete="current-password" required></label>
    <label><input type="checkbox" name="lembrar"> Manter conectado neste computador</label>
    <div class="erro-msg"></div><button class="btn prim">Entrar</button></form>`;
  $("#f-login").onsubmit = async ev => {
    ev.preventDefault();
    const v = Object.fromEntries(new FormData(ev.target));
    try { await api("POST", "/api/login", { ...v, lembrar: !!v.lembrar }); iniciar(); }
    catch (e) { $(".erro-msg", ev.target).textContent = e.message; }
  };
}

function telaPrimeiroAcesso() {
  tela.innerHTML = `<form class="login" id="f-pa"><h1>Primeiro acesso</h1><p class="sub">Crie a conta da administradora do sistema.</p>
    <label class="campo"><span>Nome</span><input name="nome" required></label>
    <label class="campo"><span>E-mail</span><input name="email" type="email" required></label>
    <label class="campo"><span>Senha (mínimo 8 caracteres)</span><input name="senha" type="password" minlength="8" required></label>
    <div class="erro-msg"></div><button class="btn prim">Criar e entrar</button></form>`;
  $("#f-pa").onsubmit = async ev => {
    ev.preventDefault();
    try { await api("POST", "/api/primeiro-acesso", Object.fromEntries(new FormData(ev.target))); iniciar(); }
    catch (e) { $(".erro-msg", ev.target).textContent = e.message; }
  };
}

$("#btn-sair").onclick = async () => { await api("POST", "/api/logout"); EU = null; location.hash = ""; iniciar(); };
$("#btn-senha").onclick = () => perguntar("Trocar senha", [
  { nome: "atual", rotulo: "Senha atual", tipo: "password" },
  { nome: "nova", rotulo: "Senha nova (mínimo 8 caracteres)", tipo: "password" },
], "Trocar", v => api("POST", "/api/senha", v)).then(v => v && avisar("Senha trocada"));

// ---------- rotas ----------
function rotear() {
  if (!EU) return;
  const [, rota, arg] = (location.hash || "#/clientes").split("/");
  const itens = [["clientes", "Clientes"]];
  if (EU.perfil === "administrador") itens.push(["configuracoes", "Configurações"], ["usuarios", "Usuários"]);
  if (["administrador", "gestor"].includes(EU.perfil)) itens.push(["historico", "Histórico"]);
  $("#menu").innerHTML = itens.map(([r, t]) => `<a href="#/${r}" class="${(rota === r || (rota === "cliente" && r === "clientes")) ? "ativo" : ""}">${t}</a>`).join("");
  const telas = { clientes: telaClientes, cliente: () => telaFicha(decodeURIComponent(arg || "")),
    configuracoes: telaConfig, usuarios: telaUsuarios, historico: telaHistorico };
  (telas[rota] || telaClientes)().catch(e => { tela.innerHTML = `<p class="vazio">${esc(e.message)}</p>`; });
}
window.addEventListener("hashchange", rotear);

// ---------- clientes ----------
const filtro = { q: "", carteira: "ativa", ordem: "vencido", pagina: 1 };

async function telaClientes() {
  const r = await api("GET", "/api/resumo");
  const c = r.carteira;
  const ativa = (c.ativa_em_dia || 0) + (c.ativa_em_atraso || 0);
  const todos = ativa + (c.inadimplencia_antiga || 0);
  tela.innerHTML = `<h1>Clientes</h1><p class="sub">Carteira migrada do Virtua.</p>
    <div class="cartoes">
      <div class="cartao"><div class="rot">A receber</div><div class="val">${brl(r.a_receber)}</div></div>
      <div class="cartao"><div class="rot">Recebido (total)</div><div class="val">${brl(r.recebido)}</div></div>
      <div class="cartao"><div class="rot">Atrasado de ${r.ano}</div><div class="val">${brl(r.vencido_ano)}</div></div>
      <div class="cartao"><div class="rot">Atrasado (total)</div><div class="val">${brl(r.vencido)}</div></div>
      <div class="cartao"><div class="rot">A vencer</div><div class="val">${brl(r.a_vencer)}</div></div>
    </div>
    <div class="barra"><div class="chips" id="chips">
      ${[["ativa", "Carteira ativa", ativa], ["ativa_em_dia", "Em dia", c.ativa_em_dia], ["ativa_em_atraso", "Em atraso", c.ativa_em_atraso],
         ["inadimplencia_antiga", "Inadimplência antiga", c.inadimplencia_antiga], ["", "Todos", todos]]
        .map(([v, t, n]) => `<button class="chip${filtro.carteira === v ? " ativo" : ""}" data-v="${v}">${t}<small>${(n || 0).toLocaleString("pt-BR")}</small></button>`).join("")}
    </div></div>
    <div class="barra">
      <input type="search" id="busca" placeholder="Buscar por nome, CPF, e-mail, telefone ou contrato" value="${esc(filtro.q)}">
      <select id="ordem">${[["vencido", "Maior valor atrasado"], ["atraso", "Mais dias de atraso"], ["pagamento", "Pagamento mais recente"], ["nome", "Nome"]]
        .map(([v, t]) => `<option value="${v}"${filtro.ordem === v ? " selected" : ""}>${t}</option>`).join("")}</select>
      ${PODE_EDITAR() ? '<button class="btn prim" id="novo-cliente">Novo cliente</button>' : ""}
    </div>
    <div id="lista"></div>`;
  $("#chips").onclick = ev => { const b = ev.target.closest(".chip"); if (!b) return; filtro.carteira = b.dataset.v; filtro.pagina = 1; telaClientes(); };
  let t;
  $("#busca").oninput = ev => { clearTimeout(t); t = setTimeout(() => { filtro.q = ev.target.value; filtro.pagina = 1; carregarLista(); }, 300); };
  $("#ordem").onchange = ev => { filtro.ordem = ev.target.value; filtro.pagina = 1; carregarLista(); };
  if ($("#novo-cliente")) $("#novo-cliente").onclick = novoCliente;
  carregarLista();
}

async function carregarLista() {
  const p = new URLSearchParams(filtro);
  const r = await api("GET", "/api/clientes?" + p);
  const paginas = Math.max(1, Math.ceil(r.total / r.por_pagina));
  $("#lista").innerHTML = r.clientes.length ? `<div class="rolar"><table class="tabela"><thead><tr>
      <th>Cliente</th><th>CPF/CNPJ</th><th>Carteira</th><th class="num">Em aberto</th><th class="num">Atrasado</th><th class="num">Parc. vencidas</th><th class="num">Dias de atraso</th><th>Último pagamento</th>
    </tr></thead><tbody>${r.clientes.map(c => `<tr class="clica" data-c="${esc(c.codigo)}">
      <td><strong>${esc(c.nome)}</strong><br><small class="sub">${esc(c.email || "sem e-mail")}</small></td>
      <td>${esc(c.cpf_cnpj)}</td><td>${selo(c.carteira)}</td>
      <td class="num">${brl(c.total_em_aberto)}</td><td class="num">${brl(c.total_vencido)}</td>
      <td class="num">${c.parcelas_vencidas}</td><td class="num">${c.maior_atraso || ""}</td><td>${dataBR(c.ultimo_pagamento)}</td></tr>`).join("")}
    </tbody></table></div>
    <div class="pag">${r.total.toLocaleString("pt-BR")} clientes · página ${r.pagina} de ${paginas}
      <button class="btn peq" id="ant"${r.pagina <= 1 ? " disabled" : ""}>Anterior</button>
      <button class="btn peq" id="prox"${r.pagina >= paginas ? " disabled" : ""}>Próxima</button></div>`
    : `<p class="vazio">Nenhum cliente encontrado.</p>`;
  $("#lista tbody")?.addEventListener("click", ev => { const tr = ev.target.closest("tr[data-c]"); if (tr) location.hash = "#/cliente/" + encodeURIComponent(tr.dataset.c); });
  if ($("#ant")) $("#ant").onclick = () => { filtro.pagina--; carregarLista(); };
  if ($("#prox")) $("#prox").onclick = () => { filtro.pagina++; carregarLista(); };
}

async function novoCliente() {
  let codigo;
  await perguntar("Novo cliente", [
    { nome: "nome", rotulo: "Nome / Razão social" }, { nome: "cpf_cnpj", rotulo: "CPF / CNPJ" },
    { nome: "email", rotulo: "E-mail", tipo: "email" }, { nome: "telefone", rotulo: "Telefone" }, { nome: "uf", rotulo: "UF" },
  ], "Criar", async v => { codigo = (await api("POST", "/api/clientes", v)).codigo; });
  if (codigo) location.hash = "#/cliente/" + encodeURIComponent(codigo);
}

// ---------- ficha do cliente ----------
let abaFicha = "parcelas";
let filtroParcelas = "abertas";

async function telaFicha(codigo) {
  const r = await api("GET", "/api/clientes/" + encodeURIComponent(codigo));
  const c = r.cliente;
  const pode = PODE_EDITAR();
  tela.innerHTML = `<p><a href="#/clientes">← Clientes</a></p>
    <div class="cab-ficha"><div><h1>${esc(c.nome)}</h1>
      <p class="sub">${esc(c.cpf_cnpj)} · código ${esc(c.codigo)} · ${selo(c.carteira)}</p></div>
      ${pode ? `<div class="barra"><button class="btn" id="ed-cli">Editar contato</button><button class="btn prim" id="novo-ct">Novo contrato</button></div>` : ""}</div>
    <div class="grade2 cartao" style="margin-bottom:16px">
      <div class="campo"><span>E-mail</span>${esc(c.email || "—")}</div><div class="campo"><span>Telefone</span>${esc(c.telefone || "—")}</div>
      <div class="campo"><span>UF</span>${esc(c.uf || "—")}</div><div class="campo"><span>Observação</span>${esc(c.observacao || "—")}</div>
    </div>
    <div class="cartoes">
      <div class="cartao"><div class="rot">Total contratado</div><div class="val">${brl(c.total_contratado)}</div></div>
      <div class="cartao"><div class="rot">Total recebido</div><div class="val">${brl(c.total_recebido)}</div></div>
      <div class="cartao"><div class="rot">Em aberto</div><div class="val">${brl(c.total_em_aberto)}</div></div>
      <div class="cartao"><div class="rot">Atrasado</div><div class="val">${brl(c.total_vencido)}</div></div>
    </div>
    <div class="abas" id="abas">
      ${[["parcelas", `Parcelas (${r.parcelas.length})`], ["contratos", `Contratos (${r.contratos.length})`], ["acordos", `Acordos (${r.acordos.length})`]]
        .concat(["administrador", "gestor"].includes(EU.perfil) ? [["historico", "Histórico de alterações"]] : [])
        .map(([a, t]) => `<button data-a="${a}" class="${abaFicha === a ? "ativo" : ""}">${t}</button>`).join("")}
    </div><div id="aba"></div>`;
  $("#abas").onclick = ev => { const b = ev.target.closest("button"); if (!b) return; abaFicha = b.dataset.a; telaFicha(codigo); };
  if (pode) {
    $("#ed-cli").onclick = () => perguntar("Editar contato", [
      { nome: "nome", rotulo: "Nome", valor: c.nome }, { nome: "email", rotulo: "E-mail", tipo: "email", valor: c.email },
      { nome: "telefone", rotulo: "Telefone", valor: c.telefone }, { nome: "uf", rotulo: "UF", valor: c.uf },
      { nome: "observacao", rotulo: "Observação", tipo: "textarea", valor: c.observacao },
    ], "Salvar", v => api("PATCH", "/api/clientes/" + encodeURIComponent(codigo), v)).then(v => v && (avisar("Contato atualizado"), telaFicha(codigo)));
    $("#novo-ct").onclick = () => perguntar("Novo contrato", [
      { nome: "produto", rotulo: "Produto" }, { nome: "valor_total", rotulo: "Valor total (R$)", tipo: "number" },
      { nome: "qtde_parcelas", rotulo: "Quantidade de parcelas", tipo: "number", valor: 1 },
      { nome: "primeiro_vencimento", rotulo: "Primeiro vencimento", tipo: "date", valor: hoje() },
    ], "Criar contrato", v => api("POST", `/api/clientes/${encodeURIComponent(codigo)}/contratos`, v))
      .then(v => v && (avisar("Contrato criado"), abaFicha = "parcelas", telaFicha(codigo)));
  }
  const aba = $("#aba");
  if (abaFicha === "contratos") aba.innerHTML = tabelaContratos(r.contratos);
  else if (abaFicha === "acordos") aba.innerHTML = tabelaAcordos(r.acordos);
  else if (abaFicha === "historico") aba.innerHTML = listaHistorico(r.historico);
  else desenharParcelas(aba, r.parcelas, codigo);
}

function tabelaContratos(ks) {
  if (!ks.length) return `<p class="vazio">Nenhum contrato.</p>`;
  return `<div class="rolar"><table class="tabela"><thead><tr><th>Contrato</th><th>Produto</th><th>Lote</th><th>Origem</th><th class="num">Parcelas</th><th class="num">Recebido</th></tr></thead><tbody>
    ${ks.map(k => `<tr><td>${esc(k.conta)}</td><td>${esc(k.produto || "")}</td><td>${esc(k.lote || "")}</td><td>${esc(k.origem)}</td><td class="num">${k.parcelas}</td><td class="num">${brl(k.recebido)}</td></tr>`).join("")}
    </tbody></table></div>`;
}

function tabelaAcordos(as) {
  if (!as.length) return `<p class="vazio">Nenhum acordo.</p>`;
  return `<div class="rolar"><table class="tabela"><thead><tr><th>Acordo</th><th>Data</th><th>Contrato</th><th class="num">Original</th><th class="num">Desconto</th><th class="num">Total</th><th class="num">Parcelas</th><th>Vencimentos renegociados</th></tr></thead><tbody>
    ${as.map(a => `<tr><td>${esc(a.nr_acordo)}</td><td>${dataBR(a.data_acordo)}</td><td>${esc(a.conta || "")}</td><td class="num">${brl(a.valor_original)}</td><td class="num">${brl(a.valor_desconto)}</td><td class="num">${brl(a.valor_total)}</td><td class="num">${esc(a.qtde_parcelas ?? "")}</td><td>${esc((a.vencimentos_renegociados || "").replaceAll(",", ", "))}</td></tr>`).join("")}
    </tbody></table></div>`;
}

function desenharParcelas(el, ps, codigo) {
  const filtros = { abertas: p => ["vencida", "a_vencer"].includes(p.status), vencidas: p => p.status === "vencida", pagas: p => p.status === "paga", todas: () => true };
  const lista = ps.filter(filtros[filtroParcelas]);
  const pode = PODE_EDITAR();
  el.innerHTML = `<div class="chips" style="margin-bottom:10px" id="fp">${[["abertas", "Em aberto"], ["vencidas", "Vencidas"], ["pagas", "Pagas"], ["todas", "Todas"]]
      .map(([v, t]) => `<button class="chip${filtroParcelas === v ? " ativo" : ""}" data-v="${v}">${t}<small>${ps.filter(filtros[v]).length}</small></button>`).join("")}</div>
    ${lista.length ? `<div class="rolar"><table class="tabela"><thead><tr><th>Vencimento</th><th>Contrato / acordo</th><th class="num">Parcela</th><th class="num">Valor</th><th class="num">Com juros e multa</th><th>Situação</th><th>Pagamento</th>${pode ? "<th></th>" : ""}</tr></thead><tbody>
      ${lista.map(p => `<tr><td>${dataBR(p.vencimento)}${p.dias_atraso ? `<br><small class="sub">${p.dias_atraso} dias de atraso</small>` : ""}</td>
        <td>${p.nr_acordo ? "Acordo " + esc(p.nr_acordo) : esc(p.conta || "")}</td><td class="num">${esc(p.nr_parcela ?? "")}</td>
        <td class="num">${brl(p.valor_previsto)}</td><td class="num">${p.status === "vencida" ? brl(p.valor_atualizado) : ""}</td>
        <td>${selo(p.status)}${p.retirar_da_cobranca ? '<br><small class="sub">retirar da cobrança</small>' : ""}</td>
        <td>${p.pago_em ? `${dataBR(p.pago_em)}<br><small class="sub">${brl(p.valor_pago)}</small>` : ""}</td>
        ${pode ? `<td>${botoesParcela(p)}</td>` : ""}</tr>`).join("")}
      </tbody></table></div>` : `<p class="vazio">Nenhuma parcela neste filtro.</p>`}`;
  $("#fp").onclick = ev => { const b = ev.target.closest(".chip"); if (!b) return; filtroParcelas = b.dataset.v; desenharParcelas(el, ps, codigo); };
  el.querySelectorAll("button[data-acao]").forEach(b => b.onclick = () => acaoParcela(ps.find(p => p.id == b.dataset.id), b.dataset.acao, codigo));
}

function botoesParcela(p) {
  const b = (acao, t, cls = "") => `<button class="btn peq ${cls}" data-acao="${acao}" data-id="${p.id}">${t}</button> `;
  if (p.situacao === "aberta") return b("baixar", "Dar baixa", "prim") + b("editar", "Editar") + b("cancelar", "Cancelar", "perigo");
  if (p.situacao === "paga") return b("estornar", "Estornar", "perigo");
  if (p.situacao === "cancelada") return b("reabrir", "Reabrir");
  return "";
}

async function acaoParcela(p, acao, codigo) {
  const url = "/api/parcelas/" + p.id;
  let ok;
  if (acao === "baixar") {
    ok = await perguntar("Dar baixa na parcela", [
      { tipo: "texto-fixo", html: `Vencimento ${dataBR(p.vencimento)} · valor ${brl(p.valor_previsto)}${p.status === "vencida" ? ` · com juros e multa ${brl(p.valor_atualizado)}` : ""}` },
      { nome: "pago_em", rotulo: "Data do pagamento", tipo: "date", valor: hoje() },
      { nome: "valor_pago", rotulo: "Valor pago (R$)", tipo: "number", valor: p.status === "vencida" ? p.valor_atualizado : p.valor_previsto },
    ], "Dar baixa", v => api("PATCH", url, { acao, ...v }));
  } else if (acao === "editar") {
    ok = await perguntar("Editar parcela", [
      { nome: "vencimento", rotulo: "Vencimento", tipo: "date", valor: p.vencimento },
      { nome: "valor_previsto", rotulo: "Valor (R$)", tipo: "number", valor: p.valor_previsto },
    ], "Salvar", v => api("PATCH", url, { acao, ...v }));
  } else {
    const txt = { estornar: "Estornar o pagamento desta parcela? Ela volta a ficar em aberto.", cancelar: "Cancelar esta parcela? Ela deixa de ser cobrada.", reabrir: "Reabrir esta parcela cancelada?" }[acao];
    ok = await perguntar("Confirmar", [{ tipo: "texto-fixo", html: esc(txt) }], "Confirmar", () => api("PATCH", url, { acao }));
  }
  if (ok) { avisar("Parcela atualizada"); telaFicha(codigo); }
}

const TABELA_NOME = { clientes: "Cliente", parcelas: "Parcela", contratos: "Contrato", acordos: "Acordo", usuarios: "Usuário", config: "Configuração", carteira: "Carteira" };
function diferenca(h) {
  if (h.acao === "carga") return `<pre>${esc(JSON.stringify(h.depois))}</pre>`;
  if (!h.antes || !h.depois) return "";
  const mud = Object.keys(h.depois).filter(k => !["atualizado_em", "criado_em"].includes(k) && JSON.stringify(h.antes[k]) !== JSON.stringify(h.depois[k]));
  return `<pre>${mud.map(k => `${esc(k)}: ${esc(h.antes[k] ?? "—")} → ${esc(h.depois[k] ?? "—")}`).join("\n")}</pre>`;
}
function listaHistorico(hs) {
  if (!hs.length) return `<p class="vazio">Nenhuma alteração registrada ainda.</p>`;
  return `<div class="rolar"><table class="tabela hist"><thead><tr><th>Quando</th><th>Quem</th><th>O quê</th></tr></thead><tbody>
    ${hs.map(h => `<tr><td>${quando(h.em)}</td><td>${esc(h.usuario)}</td><td>${esc(TABELA_NOME[h.tabela] || h.tabela)} ${esc(h.registro)} · ${esc(h.acao)}${diferenca(h)}</td></tr>`).join("")}
    </tbody></table></div>`;
}

// ---------- configurações ----------
async function telaConfig() {
  const cfg = await api("GET", "/api/config");
  const tipo = { corte_carteira_ativa: "date", multa_pct: "number", juros_mes_pct: "number" };
  tela.innerHTML = `<h1>Configurações</h1><p class="sub">Regras usadas em todo o sistema. Toda mudança fica registrada no histórico.</p>
    <div class="cartao" style="display:flex;flex-direction:column;gap:14px;max-width:560px">
    ${cfg.map(c => `<form class="campo" data-chave="${esc(c.chave)}"><span>${esc(c.descricao)}</span>
      <div class="barra" style="margin:0"><input name="valor" type="${tipo[c.chave] || "text"}" step="0.01" value="${esc(c.valor)}"><button class="btn">Salvar</button></div>
      <small class="sub">Última alteração: ${quando(c.atualizado_em)}</small></form>`).join("")}</div>`;
  tela.querySelectorAll("form[data-chave]").forEach(f => f.onsubmit = async ev => {
    ev.preventDefault();
    try { await api("PUT", "/api/config/" + f.dataset.chave, { valor: f.valor.value }); avisar("Configuração salva"); telaConfig(); }
    catch (e) { avisar(e.message); }
  });
}

// ---------- usuários ----------
async function telaUsuarios() {
  const us = await api("GET", "/api/usuarios");
  const perfis = ["administrador", "gestor", "financeiro", "consulta"].map(p => [p, ROTULO[p]]);
  tela.innerHTML = `<div class="cab-ficha"><div><h1>Usuários</h1><p class="sub">Administrador: tudo · Gestor: consulta e histórico · Financeiro: edita clientes e parcelas · Consulta: só visualiza.</p></div>
    <button class="btn prim" id="novo-u">Novo usuário</button></div>
    <div class="rolar"><table class="tabela"><thead><tr><th>Nome</th><th>E-mail</th><th>Perfil</th><th>Situação</th><th></th></tr></thead><tbody>
    ${us.map(u => `<tr><td>${esc(u.nome)}</td><td>${esc(u.email)}</td><td>${esc(ROTULO[u.perfil])}</td><td>${u.ativo ? "Ativo" : "Desativado"}</td>
      <td><button class="btn peq" data-ed="${u.id}">Alterar</button></td></tr>`).join("")}</tbody></table></div>`;
  $("#novo-u").onclick = () => perguntar("Novo usuário", [
    { nome: "nome", rotulo: "Nome" }, { nome: "email", rotulo: "E-mail", tipo: "email" },
    { nome: "perfil", rotulo: "Perfil", tipo: "select", opcoes: perfis, valor: "financeiro" },
    { nome: "senha", rotulo: "Senha inicial (mínimo 8 caracteres)", tipo: "password" },
  ], "Criar", v => api("POST", "/api/usuarios", v)).then(v => v && (avisar("Usuário criado"), telaUsuarios()));
  tela.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => {
    const u = us.find(x => x.id == b.dataset.ed);
    perguntar("Alterar " + u.nome, [
      { nome: "perfil", rotulo: "Perfil", tipo: "select", opcoes: perfis, valor: u.perfil },
      { nome: "ativo", rotulo: "Situação", tipo: "select", opcoes: [["1", "Ativo"], ["", "Desativado"]], valor: u.ativo ? "1" : "" },
      { nome: "senha", rotulo: "Nova senha (deixe vazio para manter)", tipo: "password" },
    ], "Salvar", v => api("PATCH", "/api/usuarios/" + u.id, { perfil: v.perfil, ativo: !!v.ativo, senha: v.senha || undefined }))
      .then(v => v && (avisar("Usuário atualizado"), telaUsuarios()));
  });
}

// ---------- histórico geral ----------
async function telaHistorico() {
  const hs = await api("GET", "/api/auditoria");
  tela.innerHTML = `<h1>Histórico de alterações</h1><p class="sub">As 100 alterações mais recentes em todo o sistema.</p>${listaHistorico(hs)}`;
}

iniciar();
