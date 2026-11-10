"use strict";

/* Home: quadro de cardápio e painel de senhas. */

iniciarPagina("");

async function carregarQuadro() {
  const lista = document.getElementById("quadro-itens");

  try {
    const produtos = await api("/api/produtos");
    const disponiveis = produtos.filter((p) => p.disponivel);

    // Um item de cada categoria; se sobrar espaço, completa com os próximos.
    const escolhidos = [];
    const vistas = new Set();

    for (const p of disponiveis) {
      if (!vistas.has(p.categoria)) {
        vistas.add(p.categoria);
        escolhidos.push(p);
      }
    }

    for (const p of disponiveis) {
      if (escolhidos.length >= 6) break;
      if (!escolhidos.includes(p)) escolhidos.push(p);
    }

    if (!escolhidos.length) {
      lista.innerHTML = '<li class="vazio">Nenhum produto disponível agora.</li>';
      return;
    }

    lista.innerHTML = escolhidos.slice(0, 6).map((p) => `
      <li class="linha-giz">
        <span>${esc(p.nome)}</span>
        <span class="pontilhado" aria-hidden="true"></span>
        <span class="preco">${reais(p.preco)}</span>
      </li>`).join("");

  } catch (e) {
    lista.innerHTML = `<li class="vazio">${esc(e.message)}</li>`;
  }
}

function desenharSenhas(elemento, senhas, textoVazio) {
  elemento.innerHTML = senhas.length
    ? senhas.map((s) => `<span class="senha-mini">${s}</span>`).join("")
    : `<span class="vazio">${textoVazio}</span>`;
}

async function carregarSenhas() {
  const preparando = document.getElementById("senhas-preparando");
  const prontas = document.getElementById("senhas-prontas");

  try {
    const painel = await api("/api/painel-senhas");
    desenharSenhas(preparando, painel.preparando, "Nenhum pedido em preparo.");
    desenharSenhas(prontas, painel.prontos, "Nenhum pedido pronto agora.");

  } catch (e) {
    preparando.innerHTML = `<span class="vazio">${esc(e.message)}</span>`;
    prontas.innerHTML = "";
  }
}

carregarQuadro();
carregarSenhas();
setInterval(carregarSenhas, 8000);
