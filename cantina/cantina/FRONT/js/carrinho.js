"use strict";

/* Carrinho: ajustar quantidades e enviar o pedido. */

iniciarPagina("carrinho");

const usuario = exigirLogin();
const area = document.getElementById("area-carrinho");

let carrinhoAtual = { itens: [], total: 0 };

function desenharLinha(item) {
  const alerta = item.disponivel
    ? ""
    : `<span class="alerta">Só restam ${item.estoque} em estoque. Diminua a quantidade ou remova o item.</span>`;

  return `
    <div class="linha-carrinho">
      <span class="nome">${esc(item.nome)}</span>
      <div class="quantidade" role="group" aria-label="Quantidade de ${esc(item.nome)}">
        <button type="button" data-menos="${item.id}" data-qtd="${item.quantidade}" aria-label="Diminuir">−</button>
        <span aria-live="polite">${item.quantidade}</span>
        <button type="button" data-mais="${item.id}" data-qtd="${item.quantidade}" aria-label="Aumentar">+</button>
      </div>
      <span class="preco subtotal">${reais(item.subtotal)}</span>
      <button class="link-remover" type="button" data-remover="${item.id}">Remover</button>
      ${alerta}
    </div>`;
}

function desenhar() {
  const { itens, total } = carrinhoAtual;

  atualizarSeloCarrinho(itens.reduce((s, i) => s + i.quantidade, 0));

  if (!itens.length) {
    area.innerHTML = `
      <div class="estado-vazio">
        <p>Seu carrinho está vazio. Escolha algo no cardápio para começar.</p>
        <a class="botao" href="cardapio.html">Ver cardápio</a>
      </div>`;
    return;
  }

  const temProblema = itens.some((i) => !i.disponivel);

  area.innerHTML = `
    <div class="carrinho-grade">
      <div>${itens.map(desenharLinha).join("")}</div>

      <form class="resumo" id="form-pedido" novalidate>
        <fieldset>
          <legend>Como vai pagar na retirada?</legend>
          <label class="opcao"><input type="radio" name="pagamento" value="dinheiro" checked> Dinheiro</label>
          <label class="opcao"><input type="radio" name="pagamento" value="pix"> Pix</label>
          <label class="opcao"><input type="radio" name="pagamento" value="cartao"> Cartão</label>
        </fieldset>

        <div class="campo">
          <label for="observacao">Observação (opcional)</label>
          <textarea id="observacao" maxlength="200" placeholder="Ex.: sem cebola, suco sem gelo"></textarea>
        </div>

        <div class="resumo-total">
          <span>Total</span>
          <span class="valor">${reais(total)}</span>
        </div>

        <p class="mensagem-erro" id="erro-pedido" role="alert" hidden></p>

        <button class="botao botao-senha" type="submit" ${temProblema ? "disabled" : ""}>Enviar pedido</button>
        <button class="link-remover" type="button" id="limpar">Esvaziar carrinho</button>
      </form>
    </div>`;
}

async function carregar() {
  try {
    carrinhoAtual = await api("/api/carrinho");
    desenhar();

  } catch (e) {
    if (e.status === 401) return tratarErro(e);
    mostrarFalhaDeConexao(area, e.message);
  }
}

async function alterarCarrinho(chamada) {
  try {
    carrinhoAtual = await chamada();
    desenhar();

  } catch (e) {
    tratarErro(e);
  }
}

function mostrarConfirmacao(pedido) {
  atualizarSeloCarrinho(0);

  const pagamento = ROTULO_PAGAMENTO[pedido.forma_pagamento];

  document.getElementById("conteudo-carrinho").innerHTML = `
    <div class="confirmacao">
      <h1>Pedido enviado</h1>
      <div class="senha-ticket">
        <div class="rotulo">Sua senha</div>
        <div class="numero">${pedido.senha}</div>
      </div>
      <p>Total de ${reais(pedido.total)}, para pagar em ${esc(pagamento.toLowerCase())} na retirada.
         Quando a senha ${pedido.senha} aparecer como pronta, mostre-a no balcão.</p>
      <div class="acoes">
        <a class="botao" href="pedidos.html">Acompanhar pedido</a>
        <a class="botao botao-fantasma" href="cardapio.html">Voltar ao cardápio</a>
      </div>
    </div>`;
}

area.addEventListener("click", (evento) => {
  const alvo = evento.target.closest("button");
  if (!alvo) return;

  if (alvo.dataset.mais) {
    alterarCarrinho(() => api(`/api/carrinho/${alvo.dataset.mais}`, {
      metodo: "PUT", corpo: { quantidade: Number(alvo.dataset.qtd) + 1 },
    }));

  } else if (alvo.dataset.menos) {
    alterarCarrinho(() => api(`/api/carrinho/${alvo.dataset.menos}`, {
      metodo: "PUT", corpo: { quantidade: Number(alvo.dataset.qtd) - 1 },
    }));

  } else if (alvo.dataset.remover) {
    alterarCarrinho(() => api(`/api/carrinho/${alvo.dataset.remover}`, { metodo: "DELETE" }));

  } else if (alvo.id === "limpar") {
    if (confirm("Remover todos os itens do carrinho?")) {
      alterarCarrinho(() => api("/api/carrinho", { metodo: "DELETE" }));
    }
  }
});

area.addEventListener("submit", async (evento) => {
  evento.preventDefault();

  const botao = evento.target.querySelector("button[type=submit]");
  const caixaErro = document.getElementById("erro-pedido");

  caixaErro.hidden = true;
  botao.disabled = true;

  try {
    const pedido = await api("/api/pedidos", {
      metodo: "POST",
      corpo: {
        forma_pagamento: evento.target.pagamento.value,
        observacao: document.getElementById("observacao").value,
      },
    });

    mostrarConfirmacao(pedido);

  } catch (e) {
    if (e.status === 401) return tratarErro(e);

    caixaErro.textContent = e.message;
    caixaErro.hidden = false;
    botao.disabled = false;

    // Se o estoque mudou, recarrega para mostrar o que está disponível.
    if (e.status === 409) carregar();
  }
});

if (usuario) carregar();
