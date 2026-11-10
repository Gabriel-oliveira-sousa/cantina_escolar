"use strict";

/* Meus pedidos: acompanhamento com atualização automática. */

iniciarPagina("pedidos");

const usuario = exigirLogin();
const lista = document.getElementById("lista-pedidos");

// Guarda o último status conhecido para avisar quando um pedido ficar pronto.
const statusAnteriores = new Map();

const ETAPAS = ["recebido", "preparando", "pronto", "entregue"];

function desenharEtapas(pedido) {
  if (pedido.status === "cancelado") return "";

  const posicao = ETAPAS.indexOf(pedido.status);

  return `<ol class="etapas" aria-label="Andamento do pedido">` +
    ETAPAS.map((etapa, i) => {
      const classes = [];
      if (i < posicao) classes.push("feito");
      if (i === posicao) classes.push("atual");
      if (i === posicao && i === ETAPAS.length - 1) classes.push("final");

      const atual = i === posicao ? ' aria-current="step"' : "";
      return `<li class="${classes.join(" ")}"${atual}>${ROTULO_STATUS[etapa].replace(" para retirar", "")}</li>`;
    }).join("") + "</ol>";
}

function desenharPedido(p) {
  const podeCancelar = p.status === "recebido";

  const itens = p.itens
    .map((i) => `<li>${i.quantidade}x ${esc(i.nome)} (${reais(i.subtotal)})</li>`)
    .join("");

  const dica = p.status === "pronto"
    ? '<p><strong>Seu pedido está pronto.</strong> Mostre a senha no balcão.</p>' : "";

  return `
    <article class="pedido ${p.status}">
      <div class="pedido-senha">
        <span class="rotulo">Senha</span>
        <span class="numero">${p.senha}</span>
      </div>
      <div class="pedido-corpo">
        <div class="pedido-linha">
          <span class="status ${p.status}">${ROTULO_STATUS[p.status]}</span>
          <span class="dica">${formatarData(p.criado_em)}</span>
        </div>
        ${dica}
        <ul class="pedido-itens">${itens}</ul>
        ${p.observacao ? `<p class="pedido-obs">Observação: ${esc(p.observacao)}</p>` : ""}
        <div class="pedido-linha">
          <span>${ROTULO_PAGAMENTO[p.forma_pagamento]} na retirada</span>
          <strong>${reais(p.total)}</strong>
        </div>
        ${desenharEtapas(p)}
        ${podeCancelar
          ? `<div><button class="botao botao-perigo botao-pequeno" type="button" data-cancelar="${p.id}">Cancelar pedido</button></div>`
          : ""}
      </div>
    </article>`;
}

function avisarMudancas(pedidos) {
  for (const p of pedidos) {
    const antes = statusAnteriores.get(p.id);

    if (antes && antes !== p.status && p.status === "pronto") {
      avisar(`Pedido ${p.senha} pronto. Retire no balcão.`);
    }

    statusAnteriores.set(p.id, p.status);
  }
}

async function carregar() {
  try {
    const pedidos = await api("/api/pedidos");

    avisarMudancas(pedidos);

    if (!pedidos.length) {
      lista.innerHTML = `
        <div class="estado-vazio">
          <p>Você ainda não fez nenhum pedido.</p>
          <a class="botao" href="cardapio.html">Ver cardápio</a>
        </div>`;
      return;
    }

    lista.innerHTML = pedidos.map(desenharPedido).join("");

  } catch (e) {
    if (e.status === 401) return tratarErro(e);
    mostrarFalhaDeConexao(lista, e.message);
  }
}

lista.addEventListener("click", async (evento) => {
  const botao = evento.target.closest("[data-cancelar]");
  if (!botao) return;

  if (!confirm("Cancelar este pedido?")) return;

  botao.disabled = true;

  try {
    await api(`/api/pedidos/${botao.dataset.cancelar}/cancelar`, { metodo: "POST" });
    avisar("Pedido cancelado.");
    carregar();

  } catch (e) {
    tratarErro(e);
    botao.disabled = false;
    carregar();
  }
});

if (usuario) {
  carregar();
  setInterval(carregar, 10000);
}
