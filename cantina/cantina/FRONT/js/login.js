"use strict";

/* Login e cadastro. */

iniciarPagina("");

const params = new URLSearchParams(location.search);

if (params.get("aviso") === "entrar") {
  document.getElementById("aviso-topo").hidden = false;
}

const abas = {
  entrar: {
    aba: document.getElementById("aba-entrar"),
    painel: document.getElementById("painel-entrar"),
  },
  cadastrar: {
    aba: document.getElementById("aba-cadastrar"),
    painel: document.getElementById("painel-cadastrar"),
  },
};

function mostrarAba(nome) {
  for (const [chave, { aba, painel }] of Object.entries(abas)) {
    const ativa = chave === nome;
    aba.setAttribute("aria-selected", ativa);
    painel.hidden = !ativa;
  }
}

abas.entrar.aba.addEventListener("click", () => mostrarAba("entrar"));
abas.cadastrar.aba.addEventListener("click", () => mostrarAba("cadastrar"));

/** Só aceita voltar para uma página do próprio site (ex.: "cardapio.html"). */
function destinoAposLogin(usuario) {
  const next = params.get("next");

  if (next && /^[a-z-]+\.html$/.test(next)) return next;

  return usuario.tipo === "admin" ? "admin.html" : "cardapio.html";
}

function mostrarErro(id, mensagem) {
  const caixa = document.getElementById(id);
  caixa.textContent = mensagem;
  caixa.hidden = !mensagem;
}

async function enviar(formulario, idErro, caminho, corpo) {
  const botao = formulario.querySelector("button[type=submit]");
  mostrarErro(idErro, "");
  botao.disabled = true;

  try {
    const resposta = await api(caminho, { metodo: "POST", corpo });

    Sessao.salvar(resposta.token, resposta.usuario);
    location.href = destinoAposLogin(resposta.usuario);

  } catch (e) {
    mostrarErro(idErro, e.message);
    botao.disabled = false;
  }
}

abas.entrar.painel.addEventListener("submit", (evento) => {
  evento.preventDefault();

  const email = document.getElementById("entrar-email").value.trim();
  const senha = document.getElementById("entrar-senha").value;

  if (!email || !senha) {
    mostrarErro("erro-entrar", "Informe e-mail e senha.");
    return;
  }

  enviar(abas.entrar.painel, "erro-entrar", "/api/login", { email, senha });
});

abas.cadastrar.painel.addEventListener("submit", (evento) => {
  evento.preventDefault();

  const nome = document.getElementById("cad-nome").value.trim();
  const email = document.getElementById("cad-email").value.trim();
  const senha = document.getElementById("cad-senha").value;

  if (!nome) return mostrarErro("erro-cadastrar", "Informe seu nome.");
  if (!email) return mostrarErro("erro-cadastrar", "Informe seu e-mail.");
  if (senha.length < 6) {
    return mostrarErro("erro-cadastrar", "A senha precisa ter no mínimo 6 caracteres.");
  }

  enviar(abas.cadastrar.painel, "erro-cadastrar", "/api/usuarios", {
    nome,
    email,
    senha,
    tipo: document.getElementById("cad-tipo").value,
    turma: document.getElementById("cad-turma").value.trim(),
    telefone: document.getElementById("cad-telefone").value.trim(),
  });
});

// Quem já está logado não precisa ver esta página.
if (Sessao.token && Sessao.usuario && !params.get("aviso")) {
  location.replace(destinoAposLogin(Sessao.usuario));
}
