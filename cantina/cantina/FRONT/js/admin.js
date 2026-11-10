"use strict";

/* Administração: pedidos, produtos e resumo. O servidor confere de novo
   a permissão em cada chamada; esta tela só esconde o que não é do usuário. */

iniciarPagina("admin");

const usuario = exigirLogin();

const SECOES = ["pedidos", "produtos", "resumo"];

const PROXIMO_STATUS = {
  recebido: ["preparando", "Iniciar preparo"],
  preparando: ["pronto", "Marcar como pronto"],
  pronto: ["entregue", "Marcar como entregue"],
};

const COLUNAS = [
  ["recebido", "Recebidos"],
  ["preparando", "Em preparo"],
  ["pronto", "Prontos"],
];

let categorias = [];
let produtos = [];
let produtoEmEdicao = null;
let temporizador = null;

/* ---------- Abas ---------- */

function mostrarSecao(nome) {
  for (const s of SECOES) {
    document.getElementById("aba-" + s).setAttribute("aria-selected", s === nome);
    document.getElementById("secao-" + s).hidden = s !== nome;
  }

  clearInterval(temporizador);

  if (nome === "pedidos") {
    carregarPedidos();
    temporizador = setInterval(carregarPedidos, 8000);
  } else if (nome === "produtos") {
    carregarProdutos();
  } else {
    carregarResumo();
  }
}

/* ---------- Pedidos ---------- */

function cartaoPedido(p) {
  const proximo = PROXIMO_STATUS[p.status];

  const itens = p.itens.map((i) => `<li>${i.quantidade}x ${esc(i.nome)}</li>`).join("");

  return `
    <article class="cartao-pedido">
      <div class="topo-cartao">
        <span class="senha-grande">${p.senha}</span>
        <span class="meta">${formatarData(p.criado_em)}</span>
      </div>
      <strong>${esc(p.cliente)}${p.turma ? ` (${esc(p.turma)})` : ""}</strong>
      <ul>${itens}</ul>
      ${p.observacao ? `<span class="meta">Obs.: ${esc(p.observacao)}</span>` : ""}
      <span class="meta">${ROTULO_PAGAMENTO[p.forma_pagamento]}, ${reais(p.total)}</span>
      <div class="acoes">
        ${proximo
          ? `<button class="botao botao-pequeno" type="button" data-status="${proximo[0]}" data-pedido="${p.id}">${proximo[1]}</button>`
          : ""}
        <button class="botao botao-perigo botao-pequeno" type="button" data-status="cancelado" data-pedido="${p.id}">Cancelar</button>
      </div>
    </article>`;
}

function linhaEncerrado(p) {
  return `
    <tr>
      <td>${p.senha}</td>
      <td>${esc(p.cliente)}</td>
      <td><span class="status ${p.status}">${ROTULO_STATUS[p.status]}</span></td>
      <td class="num">${reais(p.total)}</td>
      <td>${formatarData(p.atualizado_em)}</td>
    </tr>`;
}

async function carregarPedidos() {
  const colunas = document.getElementById("colunas-pedidos");
  const encerrados = document.getElementById("pedidos-encerrados");

  try {
    const [abertos, hoje] = await Promise.all([
      api("/api/pedidos?status=abertos"),
      api("/api/pedidos?data=hoje"),
    ]);

    // Do mais antigo para o mais novo: quem pediu primeiro é atendido primeiro.
    abertos.sort((a, b) => a.id - b.id);

    colunas.innerHTML = COLUNAS.map(([status, titulo]) => {
      const doStatus = abertos.filter((p) => p.status === status);

      return `
        <section class="coluna" aria-label="${titulo}">
          <h3>${titulo} <span>${doStatus.length}</span></h3>
          ${doStatus.length
            ? doStatus.map(cartaoPedido).join("")
            : '<p class="vazio">Nenhum pedido.</p>'}
        </section>`;
    }).join("");

    const fechados = hoje.filter((p) => p.status === "entregue" || p.status === "cancelado");

    encerrados.innerHTML = fechados.length
      ? `<div class="tabela-rolagem"><table>
           <thead><tr><th>Senha</th><th>Cliente</th><th>Status</th><th class="num">Total</th><th>Atualizado</th></tr></thead>
           <tbody>${fechados.map(linhaEncerrado).join("")}</tbody>
         </table></div>`
      : '<p class="vazio">Nenhum pedido encerrado hoje.</p>';

  } catch (e) {
    if (e.status === 401 || e.status === 403) return tratarAcesso(e);
    mostrarFalhaDeConexao(colunas, e.message);
  }
}

document.getElementById("colunas-pedidos").addEventListener("click", async (evento) => {
  const botao = evento.target.closest("[data-status]");
  if (!botao) return;

  const novo = botao.dataset.status;

  if (novo === "cancelado" && !confirm("Cancelar este pedido? Os itens voltam para o estoque.")) {
    return;
  }

  botao.disabled = true;

  try {
    await api(`/api/pedidos/${botao.dataset.pedido}/status`, {
      metodo: "PUT", corpo: { status: novo },
    });
    carregarPedidos();

  } catch (e) {
    tratarErro(e);
    carregarPedidos();
  }
});

/* ---------- Produtos ---------- */

function classeEstoque(p) {
  if (p.estoque === 0) return "estoque-zero";
  if (p.estoque <= 5) return "estoque-baixo";
  return "";
}

function linhaProduto(p) {
  return `
    <tr class="${p.ativo ? "" : "inativo"}">
      <td>${esc(p.nome)}</td>
      <td>${esc(p.categoria || "Sem categoria")}</td>
      <td class="num">${reais(p.preco)}</td>
      <td class="num ${classeEstoque(p)}">${p.estoque}</td>
      <td>${p.ativo ? "No cardápio" : "Oculto"}</td>
      <td>
        <div class="acoes-tabela">
          <button class="botao botao-fantasma botao-pequeno" type="button" data-editar="${p.id}">Editar</button>
          <button class="botao botao-fantasma botao-pequeno" type="button" data-alternar="${p.id}">${p.ativo ? "Ocultar" : "Mostrar"}</button>
          <button class="botao botao-perigo botao-pequeno" type="button" data-excluir="${p.id}">Excluir</button>
        </div>
      </td>
    </tr>`;
}

async function carregarProdutos() {
  const area = document.getElementById("tabela-produtos");

  try {
    [categorias, produtos] = await Promise.all([
      api("/api/categorias"),
      api("/api/produtos?todos=1"),
    ]);

    area.innerHTML = `
      <table>
        <thead><tr>
          <th>Produto</th><th>Categoria</th><th class="num">Preço</th>
          <th class="num">Estoque</th><th>Situação</th><th></th>
        </tr></thead>
        <tbody>${produtos.map(linhaProduto).join("")}</tbody>
      </table>`;

  } catch (e) {
    if (e.status === 401 || e.status === 403) return tratarAcesso(e);
    mostrarFalhaDeConexao(area, e.message);
  }
}

const dialogo = document.getElementById("dialogo-produto");
const formProduto = document.getElementById("form-produto");
const erroProduto = document.getElementById("erro-produto");

function abrirDialogo(produto) {
  produtoEmEdicao = produto || null;

  document.getElementById("titulo-dialogo").textContent =
    produto ? "Editar produto" : "Novo produto";

  document.getElementById("p-categoria").innerHTML =
    '<option value="">Sem categoria</option>' +
    categorias.map((c) => `<option value="${c.id}">${esc(c.nome)}</option>`).join("");

  document.getElementById("p-nome").value = produto ? produto.nome : "";
  document.getElementById("p-categoria").value = produto && produto.categoria_id ? produto.categoria_id : "";
  document.getElementById("p-preco").value = produto ? produto.preco : "";
  document.getElementById("p-estoque").value = produto ? produto.estoque : 0;
  document.getElementById("p-descricao").value = produto ? (produto.descricao || "") : "";
  document.getElementById("p-ativo").checked = produto ? produto.ativo : true;
  document.getElementById("p-imagem").value = "";

  erroProduto.hidden = true;
  dialogo.showModal();
}

document.getElementById("btn-novo-produto").addEventListener("click", () => abrirDialogo(null));
document.getElementById("btn-cancelar-produto").addEventListener("click", () => dialogo.close());

formProduto.addEventListener("submit", async (evento) => {
  evento.preventDefault();

  const nome = document.getElementById("p-nome").value.trim();
  const preco = document.getElementById("p-preco").value;

  if (!nome) return mostrarErroProduto("Informe o nome do produto.");
  if (preco === "" || Number(preco) < 0) return mostrarErroProduto("Informe um preço válido.");

  const estoque = document.getElementById("p-estoque").value;
  if (estoque === "" || Number(estoque) < 0) return mostrarErroProduto("Informe um estoque válido.");

  const dados = new FormData();
  dados.set("nome", nome);
  dados.set("preco", preco);
  dados.set("estoque", estoque);
  dados.set("categoria_id", document.getElementById("p-categoria").value);
  dados.set("descricao", document.getElementById("p-descricao").value.trim());
  dados.set("ativo", document.getElementById("p-ativo").checked ? "1" : "0");

  const imagem = document.getElementById("p-imagem").files[0];
  if (imagem) dados.set("imagem", imagem);

  try {
    await api(
      produtoEmEdicao ? `/api/produtos/${produtoEmEdicao.id}` : "/api/produtos",
      { metodo: produtoEmEdicao ? "PUT" : "POST", formulario: dados }
    );

    dialogo.close();
    avisar(produtoEmEdicao ? "Produto atualizado." : "Produto cadastrado.");
    carregarProdutos();

  } catch (e) {
    mostrarErroProduto(e.message);
  }
});

function mostrarErroProduto(mensagem) {
  erroProduto.textContent = mensagem;
  erroProduto.hidden = false;
}

document.getElementById("tabela-produtos").addEventListener("click", async (evento) => {
  const botao = evento.target.closest("button");
  if (!botao) return;

  const id = Number(botao.dataset.editar || botao.dataset.alternar || botao.dataset.excluir);
  const produto = produtos.find((p) => p.id === id);
  if (!produto) return;

  try {
    if (botao.dataset.editar) {
      abrirDialogo(produto);

    } else if (botao.dataset.alternar) {
      await api(`/api/produtos/${id}`, { metodo: "PUT", corpo: { ativo: !produto.ativo } });
      avisar(produto.ativo ? "Produto oculto do cardápio." : "Produto de volta ao cardápio.");
      carregarProdutos();

    } else if (botao.dataset.excluir) {
      if (!confirm(`Excluir "${produto.nome}"? Pedidos antigos continuam no histórico.`)) return;

      await api(`/api/produtos/${id}`, { metodo: "DELETE" });
      avisar("Produto excluído.");
      carregarProdutos();
    }

  } catch (e) {
    tratarErro(e);
  }
});

/* ---------- Resumo ---------- */

async function carregarResumo() {
  const area = document.getElementById("conteudo-resumo");

  try {
    const d = await api("/api/dashboard");

    const bloco = (valor, rotulo) =>
      `<div class="numero-bloco"><span class="valor">${valor}</span><span class="rotulo">${rotulo}</span></div>`;

    const vendidos = d.mais_vendidos.length
      ? d.mais_vendidos.map((v) => `<li><span>${esc(v.nome)}</span><strong>${v.vendidos}</strong></li>`).join("")
      : '<li class="vazio">Ainda sem vendas.</li>';

    const baixo = d.estoque_baixo.length
      ? d.estoque_baixo.map((p) =>
          `<li><span>${esc(p.nome)}</span><strong class="${p.estoque === 0 ? "estoque-zero" : "estoque-baixo"}">${p.estoque}</strong></li>`
        ).join("")
      : '<li class="vazio">Nenhum produto com estoque baixo.</li>';

    const porStatus = Object.entries(d.pedidos_por_status).length
      ? Object.entries(d.pedidos_por_status).map(([s, q]) =>
          `<li><span>${ROTULO_STATUS[s] || esc(s)}</span><strong>${q}</strong></li>`).join("")
      : '<li class="vazio">Ainda sem pedidos.</li>';

    area.innerHTML = `
      <div class="resumo-grade">
        ${bloco(d.pedidos_hoje, "Pedidos hoje")}
        ${bloco(reais(d.faturamento_hoje), "Faturamento hoje")}
        ${bloco(d.pedidos_abertos, "Pedidos em aberto")}
        ${bloco(d.produtos_sem_estoque, "Produtos esgotados")}
      </div>
      <div class="duas-colunas">
        <section><h3>Mais vendidos</h3><ul class="lista-simples">${vendidos}</ul></section>
        <section><h3>Estoque baixo (até 5)</h3><ul class="lista-simples">${baixo}</ul></section>
        <section><h3>Pedidos por status</h3><ul class="lista-simples">${porStatus}</ul></section>
        <section><h3>Totais</h3><ul class="lista-simples">
          <li><span>Faturamento total</span><strong>${reais(d.faturamento_total)}</strong></li>
          <li><span>Produtos cadastrados</span><strong>${d.total_produtos}</strong></li>
          <li><span>Clientes cadastrados</span><strong>${d.total_usuarios}</strong></li>
        </ul></section>
      </div>`;

  } catch (e) {
    if (e.status === 401 || e.status === 403) return tratarAcesso(e);
    mostrarFalhaDeConexao(area, e.message);
  }
}

/* ---------- Acesso ---------- */

function tratarAcesso(e) {
  if (e.status === 401) return tratarErro(e);

  clearInterval(temporizador);

  document.getElementById("area-admin").innerHTML = `
    <div class="estado-vazio">
      <h1>Área restrita</h1>
      <p>Esta página é só para quem administra a cantina.</p>
      <a class="botao" href="cardapio.html">Voltar ao cardápio</a>
    </div>`;
}

for (const s of SECOES) {
  document.getElementById("aba-" + s).addEventListener("click", () => mostrarSecao(s));
}

if (usuario) {
  if (usuario.tipo !== "admin") {
    tratarAcesso({ status: 403 });
  } else {
    mostrarSecao("pedidos");
  }
}
