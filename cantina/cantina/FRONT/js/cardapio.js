"use strict";

/* Cardápio: lista por categoria, busca e botão de adicionar ao carrinho. */

iniciarPagina("cardapio");

const estado = {
  produtos: [],
  categorias: [],
  categoriaAtiva: "todas",
  busca: "",
};

const areaCardapio = document.getElementById("cardapio");
const areaChips = document.getElementById("chips");
const campoBusca = document.getElementById("busca");

function textoEstoque(p) {
  if (!p.disponivel) return '<span class="etiqueta-estoque zerado">Esgotado</span>';
  if (p.estoque <= 5) {
    return `<span class="etiqueta-estoque">Restam ${p.estoque}</span>`;
  }
  return "";
}

function desenharItem(p) {
  const foto = p.imagem_url
    ? `<img src="${esc(p.imagem_url)}" alt="" loading="lazy">`
    : simboloDe(p.categoria);

  return `
    <li class="item${p.disponivel ? "" : " esgotado"}">
      <div class="item-foto" aria-hidden="true">${foto}</div>
      <div class="item-corpo">
        <h3>${esc(p.nome)}</h3>
        ${p.descricao ? `<p>${esc(p.descricao)}</p>` : ""}
        ${textoEstoque(p)}
      </div>
      <span class="pontilhado" aria-hidden="true"></span>
      <span class="preco">${reais(p.preco)}</span>
      <button class="botao botao-pequeno" type="button"
              data-adicionar="${p.id}" data-nome="${esc(p.nome)}"
              ${p.disponivel ? "" : "disabled"}>
        ${p.disponivel ? "Adicionar" : "Esgotado"}
      </button>
    </li>`;
}

function desenharChips() {
  const opcoes = [["todas", "Todas"], ...estado.categorias.map((c) => [String(c.id), c.nome])];

  areaChips.innerHTML = opcoes.map(([id, nome]) =>
    `<button class="chip" type="button" data-categoria="${id}"
             aria-pressed="${id === estado.categoriaAtiva}">${esc(nome)}</button>`
  ).join("");
}

function desenharCardapio() {
  const termo = estado.busca.trim().toLowerCase();

  const filtrados = estado.produtos.filter((p) => {
    if (estado.categoriaAtiva !== "todas" && String(p.categoria_id) !== estado.categoriaAtiva) {
      return false;
    }
    if (!termo) return true;
    return (p.nome + " " + (p.descricao || "")).toLowerCase().includes(termo);
  });

  if (!filtrados.length) {
    areaCardapio.innerHTML = termo
      ? `<p class="vazio">Nenhum item encontrado para "${esc(estado.busca)}". Tente outra palavra ou limpe a busca.</p>`
      : '<p class="vazio">Nenhum produto nesta categoria.</p>';
    return;
  }

  // Agrupa na ordem das categorias; produtos sem categoria vão para "Outros".
  const grupos = estado.categorias
    .map((c) => ({ nome: c.nome, itens: filtrados.filter((p) => p.categoria_id === c.id) }));

  const semCategoria = filtrados.filter((p) => !p.categoria_id);
  if (semCategoria.length) grupos.push({ nome: "Outros", itens: semCategoria });

  areaCardapio.innerHTML = grupos
    .filter((g) => g.itens.length)
    .map((g) => `
      <section class="secao-cardapio" aria-labelledby="cat-${esc(g.nome)}">
        <h2 id="cat-${esc(g.nome)}">${esc(g.nome)}</h2>
        <ul class="itens">${g.itens.map(desenharItem).join("")}</ul>
      </section>`)
    .join("");
}

async function carregar() {
  try {
    const [categorias, produtos] = await Promise.all([
      api("/api/categorias"),
      api("/api/produtos"),
    ]);

    estado.categorias = categorias;
    estado.produtos = produtos;

    desenharChips();
    desenharCardapio();

  } catch (e) {
    mostrarFalhaDeConexao(areaCardapio, e.message);
  }
}

async function adicionar(botao) {
  if (!Sessao.usuario) {
    location.href = "login.html?next=cardapio.html&aviso=entrar";
    return;
  }

  botao.disabled = true;

  try {
    const carrinho = await api("/api/carrinho", {
      metodo: "POST",
      corpo: { produto_id: Number(botao.dataset.adicionar), quantidade: 1 },
    });

    atualizarSeloCarrinho(carrinho.itens.reduce((s, i) => s + i.quantidade, 0));
    avisar(`${botao.dataset.nome} foi para o carrinho.`);

  } catch (e) {
    tratarErro(e);

  } finally {
    botao.disabled = false;
  }
}

areaCardapio.addEventListener("click", (evento) => {
  const botao = evento.target.closest("[data-adicionar]");
  if (botao) adicionar(botao);
});

areaChips.addEventListener("click", (evento) => {
  const chip = evento.target.closest("[data-categoria]");
  if (!chip) return;

  estado.categoriaAtiva = chip.dataset.categoria;
  desenharChips();
  desenharCardapio();
});

campoBusca.addEventListener("input", () => {
  estado.busca = campoBusca.value;
  desenharCardapio();
});

carregar();
