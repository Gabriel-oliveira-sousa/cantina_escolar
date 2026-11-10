"use strict";

/* ==========================================================================
   api.js — código compartilhado por todas as páginas:
   comunicação com a API, sessão do usuário, cabeçalho, avisos e formatação.
   ========================================================================== */

const API_URL = (window.CANTINA_API_URL || "http://127.0.0.1:5000").replace(/\/+$/, "");
const CHAVE_SESSAO = "cantina_sessao";

const ROTULO_STATUS = {
  recebido: "Recebido",
  preparando: "Preparando",
  pronto: "Pronto para retirar",
  entregue: "Entregue",
  cancelado: "Cancelado",
};

const ROTULO_PAGAMENTO = { dinheiro: "Dinheiro", pix: "Pix", cartao: "Cartão" };

const SIMBOLO_CATEGORIA = {
  Salgados: "🥟",
  Lanches: "🥪",
  Refeições: "🍛",
  Bebidas: "🥤",
  Doces: "🍫",
};

/* ---------- Sessão (token guardado no navegador) ---------- */

const Sessao = {
  ler() {
    try {
      return JSON.parse(localStorage.getItem(CHAVE_SESSAO)) || null;
    } catch (e) {
      return null;
    }
  },
  salvar(token, usuario) {
    try {
      localStorage.setItem(CHAVE_SESSAO, JSON.stringify({ token, usuario }));
    } catch (e) { /* navegador bloqueou o armazenamento */ }
  },
  limpar() {
    try { localStorage.removeItem(CHAVE_SESSAO); } catch (e) { /* ignora */ }
  },
  get token() {
    const s = this.ler();
    return s ? s.token : null;
  },
  get usuario() {
    const s = this.ler();
    return s ? s.usuario : null;
  },
};

/* ---------- Chamadas à API ---------- */

class ErroApi extends Error {
  constructor(mensagem, status) {
    super(mensagem);
    this.status = status;
  }
}

/**
 * api("/api/produtos")
 * api("/api/login", { metodo: "POST", corpo: { email, senha } })
 * api("/api/produtos", { metodo: "POST", formulario: new FormData(...) })
 */
async function api(caminho, opcoes = {}) {
  const { metodo = "GET", corpo, formulario } = opcoes;
  const cabecalhos = {};
  let body;

  if (Sessao.token) cabecalhos["Authorization"] = "Bearer " + Sessao.token;

  if (formulario) {
    body = formulario;
  } else if (corpo !== undefined) {
    cabecalhos["Content-Type"] = "application/json";
    body = JSON.stringify(corpo);
  }

  let resposta;

  try {
    resposta = await fetch(API_URL + caminho, { method: metodo, headers: cabecalhos, body });
  } catch (e) {
    throw new ErroApi(
      "Não foi possível falar com o servidor. Confira se o back-end está ligado.", 0
    );
  }

  let dados = null;
  try { dados = await resposta.json(); } catch (e) { /* resposta sem JSON */ }

  if (!resposta.ok) {
    // Token vencido ou inválido: a sessão deixa de valer.
    if (resposta.status === 401 && Sessao.token) Sessao.limpar();

    throw new ErroApi(
      (dados && dados.erro) || "Algo deu errado. Tente de novo.",
      resposta.status
    );
  }

  return dados;
}

/** Trata um erro de API: 401 leva ao login, o resto vira aviso na tela. */
function tratarErro(e) {
  if (e instanceof ErroApi && e.status === 401) {
    irParaLogin();
    return;
  }
  avisar(e.message || "Algo deu errado.", "erro");
}

function irParaLogin(aviso) {
  const atual = location.pathname.split("/").pop() || "index.html";
  const extra = aviso ? "&aviso=" + aviso : "";
  location.href = "login.html?next=" + encodeURIComponent(atual) + extra;
}

/** Use no começo de páginas que exigem login. Retorna o usuário ou null. */
function exigirLogin() {
  const usuario = Sessao.usuario;

  if (!usuario || !Sessao.token) {
    irParaLogin("entrar");
    return null;
  }

  return usuario;
}

/* ---------- Utilitários ---------- */

/** Escapa texto antes de colocar em HTML (evita injeção de código). */
function esc(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const formatadorReal = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function reais(valor) {
  return formatadorReal.format(Number(valor) || 0);
}

/** "2026-10-19 14:32:10" -> "14:32" (hoje) ou "19/10 14:32". */
function formatarData(texto) {
  if (!texto) return "";

  const [data, hora] = texto.split(" ");
  const [ano, mes, dia] = data.split("-");
  const hoje = new Date();
  const ehHoje =
    Number(ano) === hoje.getFullYear() &&
    Number(mes) === hoje.getMonth() + 1 &&
    Number(dia) === hoje.getDate();

  const horaCurta = (hora || "").slice(0, 5);

  return ehHoje ? `Hoje, ${horaCurta}` : `${dia}/${mes} ${horaCurta}`;
}

function simboloDe(categoria) {
  return SIMBOLO_CATEGORIA[categoria] || "🍽️";
}

function avisar(mensagem, tipo = "ok") {
  let area = document.getElementById("avisos");

  if (!area) {
    area = document.createElement("div");
    area.id = "avisos";
    area.className = "avisos";
    area.setAttribute("role", "status");
    area.setAttribute("aria-live", "polite");
    document.body.appendChild(area);
  }

  const aviso = document.createElement("div");
  aviso.className = "aviso " + tipo;
  aviso.textContent = mensagem;
  area.appendChild(aviso);

  setTimeout(() => aviso.remove(), tipo === "erro" ? 6000 : 3500);
}

/* ---------- Cabeçalho e rodapé ---------- */

function atualizarSeloCarrinho(quantidade) {
  const selo = document.getElementById("selo-carrinho");
  if (!selo) return;

  selo.textContent = quantidade;
  selo.hidden = !quantidade;
}

async function carregarSeloCarrinho() {
  if (!Sessao.token) return;

  try {
    const carrinho = await api("/api/carrinho");
    atualizarSeloCarrinho(carrinho.itens.reduce((s, i) => s + i.quantidade, 0));
  } catch (e) { /* o selo é só um detalhe */ }
}

function montarCabecalho(paginaAtual) {
  const topo = document.getElementById("topo");
  if (!topo) return;

  const usuario = Sessao.usuario;

  const links = [["cardapio.html", "Cardápio", "cardapio"]];

  if (usuario) links.push(["pedidos.html", "Meus pedidos", "pedidos"]);
  if (usuario && usuario.tipo === "admin") links.push(["admin.html", "Administração", "admin"]);

  links.push(["carrinho.html", "Carrinho", "carrinho"]);

  const itens = links.map(([href, texto, chave]) => {
    const atual = chave === paginaAtual ? ' aria-current="page"' : "";
    const selo = chave === "carrinho"
      ? ' <span class="selo" id="selo-carrinho" hidden>0</span>' : "";
    return `<a href="${href}"${atual}>${texto}${selo}</a>`;
  }).join("");

  const conta = usuario
    ? `<span class="ola">Olá, ${esc(usuario.nome.split(" ")[0])}</span>
       <button class="link" type="button" id="btn-sair">Sair</button>`
    : `<a class="botao botao-pequeno botao-fantasma" href="login.html">Entrar</a>`;

  topo.className = "topo";
  topo.innerHTML = `
    <div class="topo-interno">
      <a class="marca" href="index.html">Cantina</a>
      <nav class="menu" aria-label="Principal">${itens}${conta}</nav>
    </div>`;

  const botaoSair = document.getElementById("btn-sair");

  if (botaoSair) {
    botaoSair.addEventListener("click", () => {
      Sessao.limpar();
      location.href = "index.html";
    });
  }

  carregarSeloCarrinho();
}

function montarRodape() {
  const rodape = document.getElementById("rodape");
  if (!rodape) return;

  rodape.className = "rodape";
  rodape.innerHTML = "<p>Cantina, projeto escolar de Arthur, Davi e Gabriel. " +
    "Estrutura base: Dragon Suplementos, de Guilherme Teles da Silva e Arthur Uezu da Cruz.</p>";
}

/** Monta cabeçalho e rodapé. Chame uma vez por página. */
function iniciarPagina(paginaAtual) {
  montarCabecalho(paginaAtual);
  montarRodape();
}

/** Aviso de "back-end desligado" dentro de um elemento. */
function mostrarFalhaDeConexao(elemento, mensagem) {
  elemento.innerHTML =
    `<p class="mensagem-erro">${esc(mensagem)}</p>`;
}
