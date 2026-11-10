# -*- coding: utf-8 -*-
"""
cantina_desktop.py

Painel do caixa/administrador da Cantina, em Python (Tkinter).

Usa a MESMA API do site (o back-end Flask). Por isso o que acontece aqui
aparece no site e vice-versa: quando o atendente muda um pedido para
"pronto" nesta tela, a senha aparece no painel de senhas do site.

Só usa a biblioteca padrão do Python (tkinter, urllib, json, threading),
então não precisa instalar nada além do próprio Python.

Como executar:

    1. Inicie o back-end (pasta BACK):   python app.py
    2. Em outro terminal (pasta DESKTOP): python cantina_desktop.py

Login padrão do administrador: admin@cantina.com / admin123
"""

import json
import os
import queue
import threading
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime
from tkinter import messagebox, ttk


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

URL_PADRAO = os.environ.get("CANTINA_API_URL", "http://127.0.0.1:5000")

INTERVALO_ATUALIZACAO_MS = 10_000

ROTULO_STATUS = {
    "recebido": "Recebido",
    "preparando": "Em preparo",
    "pronto": "Pronto",
    "entregue": "Entregue",
    "cancelado": "Cancelado",
}

ROTULO_PAGAMENTO = {"dinheiro": "Dinheiro", "pix": "Pix", "cartao": "Cartão"}

# status atual -> (próximo status, texto do botão)
PROXIMO_STATUS = {
    "recebido": ("preparando", "Iniciar preparo"),
    "preparando": ("pronto", "Marcar como pronto"),
    "pronto": ("entregue", "Marcar como entregue"),
}

# Cores (as mesmas do site)
COR_QUADRO = "#16302a"
COR_QUADRO_2 = "#1f423a"
COR_PAPEL = "#f3f5f1"
COR_SENHA = "#ffd23f"
COR_TOMATE = "#c93a22"
COR_MUSGO = "#2c6b4d"


def reais(valor):
    """6.5 -> 'R$ 6,50'."""
    texto = f"{float(valor):,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def hora_curta(texto):
    """'2026-10-19 14:32:10' -> '14:32'."""
    return (texto or "")[11:16]


# ============================================================================
# CLIENTE DA API
# ============================================================================

class ErroApi(Exception):

    def __init__(self, mensagem, status=0):
        super().__init__(mensagem)
        self.status = status


class ClienteApi:
    """Faz as chamadas HTTP à API e guarda o token de login."""

    def __init__(self, url):
        self.url = url.rstrip("/")
        self.token = None

    def chamar(self, metodo, caminho, corpo=None):

        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None

        requisicao = urllib.request.Request(
            self.url + caminho, data=dados, method=metodo
        )
        requisicao.add_header("Content-Type", "application/json")

        if self.token:
            requisicao.add_header("Authorization", "Bearer " + self.token)

        try:
            # 30 s: o Render pode demorar para "acordar" o servidor.
            with urllib.request.urlopen(requisicao, timeout=30) as resposta:
                texto = resposta.read().decode("utf-8")

        except urllib.error.HTTPError as e:
            mensagem = "Algo deu errado. Tente de novo."

            try:
                mensagem = json.loads(e.read().decode("utf-8")).get("erro", mensagem)
            except Exception:
                pass

            raise ErroApi(mensagem, e.code)

        except (urllib.error.URLError, OSError):
            raise ErroApi(
                "Não foi possível conectar ao servidor.\n"
                "Confira o endereço e se o back-end está ligado (python app.py).",
                0,
            )

        return json.loads(texto) if texto else None

    def get(self, caminho):
        return self.chamar("GET", caminho)

    def post(self, caminho, corpo=None):
        return self.chamar("POST", caminho, corpo if corpo is not None else {})

    def put(self, caminho, corpo):
        return self.chamar("PUT", caminho, corpo)

    def delete(self, caminho):
        return self.chamar("DELETE", caminho)


# ============================================================================
# JANELA PRINCIPAL
# ============================================================================

class App(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title("Cantina - Painel do caixa")
        self.geometry("1040x660")
        self.minsize(900, 580)
        self.configure(bg=COR_PAPEL)

        self.api = None
        self.usuario = None

        # Fila para trazer resultados das chamadas (feitas em threads)
        # de volta para a thread da interface, que é a única que pode
        # mexer nos widgets.
        self.fila = queue.Queue()

        self._configurar_estilo()

        self.tela = None
        self.mostrar_login()

        self.after(100, self._processar_fila)

    # ---------- estilo ----------

    def _configurar_estilo(self):

        estilo = ttk.Style(self)
        estilo.theme_use("clam")

        estilo.configure(".", background=COR_PAPEL, font=("Segoe UI", 10))
        estilo.configure("TLabel", background=COR_PAPEL)
        estilo.configure("TFrame", background=COR_PAPEL)
        estilo.configure("TCheckbutton", background=COR_PAPEL)
        estilo.configure("TLabelframe", background=COR_PAPEL)
        estilo.configure("TLabelframe.Label", background=COR_PAPEL,
                         font=("Segoe UI", 10, "bold"))

        estilo.configure("Titulo.TLabel", font=("Segoe UI", 20, "bold"),
                         foreground=COR_QUADRO)
        estilo.configure("Subtitulo.TLabel", foreground="#54605a")
        estilo.configure("Erro.TLabel", foreground=COR_TOMATE)

        estilo.configure("TButton", padding=(12, 6))
        estilo.configure("Principal.TButton", background=COR_QUADRO,
                         foreground="white", padding=(14, 8),
                         font=("Segoe UI", 10, "bold"))
        estilo.map("Principal.TButton",
                   background=[("active", COR_QUADRO_2), ("disabled", "#c9d0c8")],
                   foreground=[("disabled", "#6c766f")])

        estilo.configure("Perigo.TButton", foreground=COR_TOMATE)

        estilo.configure("Treeview", rowheight=28, font=("Segoe UI", 10),
                         background="white", fieldbackground="white")
        estilo.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"),
                         background="#eaeee7", padding=6)

        estilo.configure("TNotebook", background=COR_PAPEL)
        estilo.configure("TNotebook.Tab", padding=(18, 8),
                         font=("Segoe UI", 10, "bold"))

        estilo.configure("Numero.TLabel", font=("Segoe UI", 20, "bold"),
                         background="white")
        estilo.configure("Cartao.TFrame", background="white", relief="solid",
                         borderwidth=1)

    # ---------- troca de telas ----------

    def _trocar_tela(self, nova):

        if self.tela is not None:
            self.tela.destroy()

        self.tela = nova
        self.tela.pack(fill="both", expand=True)

    def mostrar_login(self):

        # Ao voltar para o login, o token anterior deixa de valer.
        self.api = None
        self.usuario = None

        self._trocar_tela(TelaLogin(self))

    def mostrar_painel(self):

        self._trocar_tela(TelaPainel(self))

    # ---------- chamadas em segundo plano ----------

    def em_segundo_plano(self, tarefa, ao_terminar=None, ao_falhar=None):
        """
        Roda tarefa() em uma thread (a janela não trava enquanto o servidor
        responde) e chama ao_terminar(resultado) na thread da interface.
        """

        def trabalhar():
            try:
                resultado = tarefa()

            except Exception as erro:
                self.fila.put((ao_falhar or self.mostrar_erro, erro))

            else:
                if ao_terminar:
                    self.fila.put((ao_terminar, resultado))

        threading.Thread(target=trabalhar, daemon=True).start()

    def _processar_fila(self):

        try:
            while True:
                funcao, argumento = self.fila.get_nowait()

                try:
                    funcao(argumento)
                except tk.TclError:
                    pass  # o widget já foi fechado

        except queue.Empty:
            pass

        self.after(100, self._processar_fila)

    def mostrar_erro(self, erro):

        if isinstance(erro, ErroApi) and erro.status == 401:
            messagebox.showinfo("Sessão expirada", "Entre de novo para continuar.")
            self.mostrar_login()
            return

        messagebox.showerror("Cantina", str(erro))


# ============================================================================
# TELA DE LOGIN
# ============================================================================

class TelaLogin(ttk.Frame):

    def __init__(self, app):
        super().__init__(app)
        self.app = app

        caixa = ttk.Frame(self)
        caixa.place(relx=0.5, rely=0.46, anchor="center")

        ttk.Label(caixa, text="Cantina", style="Titulo.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(caixa, text="Painel do caixa e administração",
                  style="Subtitulo.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 18))

        self.url = tk.StringVar(value=URL_PADRAO)
        self.email = tk.StringVar(value="admin@cantina.com")
        self.senha = tk.StringVar()

        campos = (
            ("Endereço da API", self.url, ""),
            ("E-mail", self.email, ""),
            ("Senha", self.senha, "*"),
        )

        for linha, (rotulo, variavel, mascara) in enumerate(campos, start=2):
            ttk.Label(caixa, text=rotulo).grid(
                row=linha, column=0, sticky="w", pady=6, padx=(0, 14))

            entrada = ttk.Entry(caixa, textvariable=variavel, width=36, show=mascara)
            entrada.grid(row=linha, column=1, pady=6)

            if rotulo == "Senha":
                self.entrada_senha = entrada

            entrada.bind("<Return>", lambda _e: self.entrar())

        self.mensagem = ttk.Label(caixa, text="", style="Erro.TLabel",
                                  wraplength=360, justify="left")
        self.mensagem.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.botao = ttk.Button(caixa, text="Entrar", style="Principal.TButton",
                                command=self.entrar)
        self.botao.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(14, 0))

        self.entrada_senha.focus_set()

    def entrar(self):

        email = self.email.get().strip()
        senha = self.senha.get()

        if not email or not senha:
            self.mensagem.config(text="Informe e-mail e senha.")
            return

        self.mensagem.config(text="")
        self.botao.config(state="disabled", text="Entrando...")

        cliente = ClienteApi(self.url.get().strip() or URL_PADRAO)

        def tarefa():
            resposta = cliente.post("/api/login", {"email": email, "senha": senha})

            if resposta["usuario"]["tipo"] != "admin":
                raise ErroApi("Esta tela é só para o administrador da cantina.", 403)

            cliente.token = resposta["token"]
            return cliente, resposta["usuario"]

        def sucesso(resultado):
            self.app.api, self.app.usuario = resultado
            self.app.mostrar_painel()

        def falha(erro):
            self.mensagem.config(text=str(erro))
            self.botao.config(state="normal", text="Entrar")

        self.app.em_segundo_plano(tarefa, sucesso, falha)


# ============================================================================
# TELA PRINCIPAL (abas)
# ============================================================================

class TelaPainel(ttk.Frame):

    def __init__(self, app):
        super().__init__(app)
        self.app = app

        # Faixa superior
        faixa = tk.Frame(self, bg=COR_QUADRO)
        faixa.pack(fill="x")

        tk.Label(faixa, text="Cantina", bg=COR_QUADRO, fg="white",
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=16, pady=10)

        ttk.Button(faixa, text="Sair", command=app.mostrar_login).pack(
            side="right", padx=16)

        tk.Label(faixa, text=f"Olá, {app.usuario['nome']}", bg=COR_QUADRO,
                 fg="#b9cbc1").pack(side="right")

        # Barra de status
        self.status = tk.StringVar(value="")
        tk.Label(self, textvariable=self.status, anchor="w", bg="#e9eee6",
                 fg="#54605a", padx=12, pady=4).pack(side="bottom", fill="x")

        # Abas
        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=12, pady=12)

        self.aba_pedidos = AbaPedidos(self.abas, self)
        self.aba_produtos = AbaProdutos(self.abas, self)
        self.aba_resumo = AbaResumo(self.abas, self)

        self.abas.add(self.aba_pedidos, text="Pedidos")
        self.abas.add(self.aba_produtos, text="Produtos")
        self.abas.add(self.aba_resumo, text="Resumo")

        self.abas.bind("<<NotebookTabChanged>>", self._trocou_aba)

        self.aba_pedidos.carregar()
        self._agendar_atualizacao()

    @property
    def api(self):
        return self.app.api

    def avisar(self, texto):
        self.status.set(texto)

    def _trocou_aba(self, _evento):

        aba = self.abas.nametowidget(self.abas.select())
        aba.carregar()

    def _agendar_atualizacao(self):
        """Atualiza a lista de pedidos sozinha (se a aba estiver aberta)."""

        self._tarefa = self.after(INTERVALO_ATUALIZACAO_MS, self._atualizar_sozinho)

    def _atualizar_sozinho(self):

        if self.aba_pedidos.automatico.get() and \
                self.abas.nametowidget(self.abas.select()) is self.aba_pedidos:
            self.aba_pedidos.carregar(silencioso=True)

        self._agendar_atualizacao()

    def destroy(self):

        try:
            self.after_cancel(self._tarefa)
        except Exception:
            pass

        super().destroy()


# ============================================================================
# ABA: PEDIDOS
# ============================================================================

class AbaPedidos(ttk.Frame):

    FILTROS = {"Em aberto": "?status=abertos", "Todos de hoje": "?data=hoje"}

    def __init__(self, pai, painel):
        super().__init__(pai, padding=12)
        self.painel = painel
        self.pedidos = {}
        self.carregando = False

        # Barra de ferramentas
        barra = ttk.Frame(self)
        barra.pack(fill="x", pady=(0, 10))

        ttk.Label(barra, text="Mostrar:").pack(side="left")

        self.filtro = ttk.Combobox(barra, values=list(self.FILTROS), state="readonly",
                                   width=16)
        self.filtro.current(0)
        self.filtro.pack(side="left", padx=8)
        self.filtro.bind("<<ComboboxSelected>>", lambda _e: self.carregar())

        ttk.Button(barra, text="Atualizar", command=self.carregar).pack(side="left")

        self.automatico = tk.BooleanVar(value=True)
        ttk.Checkbutton(barra, text="Atualizar sozinho a cada 10 s",
                        variable=self.automatico).pack(side="left", padx=14)

        # Lista + detalhes
        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True)

        # uniform força a proporção 3:2 entre a lista e os detalhes, para
        # as colunas da lista nunca ficarem cortadas.
        corpo.columnconfigure(0, weight=3, uniform="pedidos")
        corpo.columnconfigure(1, weight=2, uniform="pedidos")
        corpo.rowconfigure(0, weight=1)

        colunas = (
            ("senha", "Senha", 60, "center"),
            ("cliente", "Cliente", 190, "w"),
            ("status", "Status", 100, "w"),
            ("total", "Total", 90, "e"),
            ("hora", "Hora", 60, "center"),
        )

        self.tabela = ttk.Treeview(corpo, columns=[c[0] for c in colunas],
                                   show="headings", selectmode="browse")

        for chave, titulo, largura, alinhamento in colunas:
            self.tabela.heading(chave, text=titulo)
            self.tabela.column(chave, width=largura, anchor=alinhamento)

        self.tabela.tag_configure("pronto", background="#dcefe4")
        self.tabela.tag_configure("preparando", background="#fff0b3")
        self.tabela.tag_configure("encerrado", foreground="#8a948d")

        self.tabela.grid(row=0, column=0, sticky="nsew")
        self.tabela.bind("<<TreeviewSelect>>", lambda _e: self.mostrar_detalhes())

        rolagem = ttk.Scrollbar(corpo, orient="vertical", command=self.tabela.yview)
        self.tabela.configure(yscrollcommand=rolagem.set)
        rolagem.grid(row=0, column=0, sticky="nse")

        lateral = ttk.LabelFrame(corpo, text="Detalhes do pedido", padding=12)
        lateral.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        lateral.rowconfigure(0, weight=1)
        lateral.columnconfigure(0, weight=1)

        self.detalhes = tk.Text(lateral, height=10, width=30, wrap="word", relief="flat",
                                bg="white", font=("Segoe UI", 10), padx=8, pady=8,
                                state="disabled")
        self.detalhes.grid(row=0, column=0, sticky="nsew")
        self.detalhes.tag_configure("senha", font=("Segoe UI", 28, "bold"),
                                    background=COR_SENHA)
        self.detalhes.tag_configure("negrito", font=("Segoe UI", 10, "bold"))
        self.detalhes.tag_configure("suave", foreground="#54605a")

        self.botao_avancar = ttk.Button(lateral, text="Avançar status",
                                        style="Principal.TButton", state="disabled",
                                        command=self.avancar)
        self.botao_avancar.grid(row=1, column=0, sticky="ew", pady=(12, 6))

        self.botao_cancelar = ttk.Button(lateral, text="Cancelar pedido",
                                         style="Perigo.TButton", state="disabled",
                                         command=self.cancelar)
        self.botao_cancelar.grid(row=2, column=0, sticky="ew")

    # ---------- dados ----------

    def carregar(self, silencioso=False):

        if self.carregando:
            return

        self.carregando = True
        consulta = self.FILTROS[self.filtro.get()]
        api = self.painel.api

        def tarefa():
            pedidos = api.get("/api/pedidos" + consulta)
            pedidos.sort(key=lambda p: p["id"])  # mais antigo primeiro
            return pedidos

        def sucesso(pedidos):
            self.carregando = False
            self._preencher(pedidos)
            self.painel.avisar(
                f"Pedidos atualizados às {datetime.now():%H:%M:%S}. "
                f"{len(pedidos)} na lista."
            )

        def falha(erro):
            self.carregando = False

            if silencioso and not (isinstance(erro, ErroApi) and erro.status == 401):
                self.painel.avisar("Sem conexão com o servidor. Tentando de novo...")
            else:
                self.painel.app.mostrar_erro(erro)

        self.painel.app.em_segundo_plano(tarefa, sucesso, falha)

    def _preencher(self, pedidos):

        selecionado = self.tabela.selection()
        selecionado = selecionado[0] if selecionado else None

        self.pedidos = {str(p["id"]): p for p in pedidos}
        self.tabela.delete(*self.tabela.get_children())

        for p in pedidos:
            tags = (p["status"],) if p["status"] in ("pronto", "preparando") else ()

            if p["status"] in ("entregue", "cancelado"):
                tags = ("encerrado",)

            self.tabela.insert("", "end", iid=str(p["id"]), tags=tags, values=(
                p["senha"], p["cliente"], ROTULO_STATUS[p["status"]],
                reais(p["total"]), hora_curta(p["criado_em"]),
            ))

        if selecionado in self.pedidos:
            self.tabela.selection_set(selecionado)

        self.mostrar_detalhes()

    def _pedido_selecionado(self):

        selecao = self.tabela.selection()
        return self.pedidos.get(selecao[0]) if selecao else None

    def mostrar_detalhes(self):

        pedido = self._pedido_selecionado()

        self.detalhes.config(state="normal")
        self.detalhes.delete("1.0", "end")

        if pedido is None:
            self.detalhes.insert("end", "Selecione um pedido na lista.", "suave")
            self.botao_avancar.config(state="disabled", text="Avançar status")
            self.botao_cancelar.config(state="disabled")

        else:
            self.detalhes.insert("end", f" {pedido['senha']} ", "senha")
            self.detalhes.insert(
                "end", f"   {ROTULO_STATUS[pedido['status']]}\n\n", "negrito")

            turma = f" ({pedido['turma']})" if pedido["turma"] else ""
            self.detalhes.insert("end", f"{pedido['cliente']}{turma}\n", "negrito")
            self.detalhes.insert("end", f"Feito às {hora_curta(pedido['criado_em'])}\n\n",
                                 "suave")

            for item in pedido["itens"]:
                self.detalhes.insert(
                    "end", f"{item['quantidade']}x {item['nome']}   "
                           f"{reais(item['subtotal'])}\n")

            if pedido["observacao"]:
                self.detalhes.insert("end", f"\nObservação: {pedido['observacao']}\n")

            self.detalhes.insert(
                "end",
                f"\n{ROTULO_PAGAMENTO[pedido['forma_pagamento']]} na retirada\n",
                "suave")
            self.detalhes.insert("end", f"Total: {reais(pedido['total'])}", "negrito")

            proximo = PROXIMO_STATUS.get(pedido["status"])

            if proximo:
                self.botao_avancar.config(state="normal", text=proximo[1])
                self.botao_cancelar.config(state="normal")
            else:
                self.botao_avancar.config(state="disabled", text="Pedido encerrado")
                self.botao_cancelar.config(state="disabled")

        self.detalhes.config(state="disabled")

    # ---------- ações ----------

    def _mudar_status(self, pedido, novo, mensagem):

        api = self.painel.api

        self.painel.app.em_segundo_plano(
            lambda: api.put(f"/api/pedidos/{pedido['id']}/status", {"status": novo}),
            lambda _r: (self.painel.avisar(mensagem), self.carregar()),
            lambda erro: (self.painel.app.mostrar_erro(erro), self.carregar()),
        )

    def avancar(self):

        pedido = self._pedido_selecionado()
        proximo = PROXIMO_STATUS.get(pedido["status"]) if pedido else None

        if proximo:
            self._mudar_status(
                pedido, proximo[0], f"Pedido {pedido['senha']}: {proximo[1].lower()}.")

    def cancelar(self):

        pedido = self._pedido_selecionado()

        if pedido and messagebox.askyesno(
                "Cancelar pedido",
                f"Cancelar o pedido {pedido['senha']}?\n"
                "Os itens voltam para o estoque."):
            self._mudar_status(pedido, "cancelado", f"Pedido {pedido['senha']} cancelado.")


# ============================================================================
# ABA: PRODUTOS
# ============================================================================

class AbaProdutos(ttk.Frame):

    def __init__(self, pai, painel):
        super().__init__(pai, padding=12)
        self.painel = painel
        self.produtos = {}
        self.categorias = {}          # nome -> id
        self.em_edicao = None         # id do produto selecionado (None = novo)

        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True)
        corpo.columnconfigure(0, weight=3)
        corpo.columnconfigure(1, weight=2)
        corpo.rowconfigure(0, weight=1)

        colunas = (
            ("nome", "Produto", 190, "w"),
            ("categoria", "Categoria", 100, "w"),
            ("preco", "Preço", 80, "e"),
            ("estoque", "Estoque", 70, "e"),
            ("situacao", "Situação", 90, "w"),
        )

        self.tabela = ttk.Treeview(corpo, columns=[c[0] for c in colunas],
                                   show="headings", selectmode="browse")

        for chave, titulo, largura, alinhamento in colunas:
            self.tabela.heading(chave, text=titulo)
            self.tabela.column(chave, width=largura, anchor=alinhamento)

        self.tabela.tag_configure("baixo", foreground="#8a5a00")
        self.tabela.tag_configure("zerado", foreground=COR_TOMATE)
        self.tabela.tag_configure("oculto", foreground="#8a948d")

        self.tabela.grid(row=0, column=0, sticky="nsew")
        self.tabela.bind("<<TreeviewSelect>>", lambda _e: self.selecionar())

        rolagem = ttk.Scrollbar(corpo, orient="vertical", command=self.tabela.yview)
        self.tabela.configure(yscrollcommand=rolagem.set)
        rolagem.grid(row=0, column=0, sticky="nse")

        # Formulário
        form = ttk.LabelFrame(corpo, text="Produto", padding=12)
        form.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        form.columnconfigure(1, weight=1)

        self.nome = tk.StringVar()
        self.categoria = tk.StringVar()
        self.preco = tk.StringVar()
        self.estoque = tk.StringVar(value="0")
        self.ativo = tk.BooleanVar(value=True)

        ttk.Label(form, text="Nome").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=self.nome).grid(row=0, column=1, sticky="ew")

        ttk.Label(form, text="Categoria").grid(row=1, column=0, sticky="w", pady=5)
        self.combo_categoria = ttk.Combobox(form, textvariable=self.categoria,
                                            state="readonly")
        self.combo_categoria.grid(row=1, column=1, sticky="ew")

        ttk.Label(form, text="Preço (R$)").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=self.preco).grid(row=2, column=1, sticky="ew")

        ttk.Label(form, text="Estoque").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Spinbox(form, from_=0, to=9999, textvariable=self.estoque,
                    width=8).grid(row=3, column=1, sticky="w")

        ttk.Label(form, text="Descrição").grid(row=4, column=0, sticky="nw", pady=5)
        self.descricao = tk.Text(form, height=4, width=28, wrap="word",
                                 font=("Segoe UI", 10), relief="solid", borderwidth=1)
        self.descricao.grid(row=4, column=1, sticky="ew")

        ttk.Checkbutton(form, text="Mostrar no cardápio",
                        variable=self.ativo).grid(row=5, column=1, sticky="w", pady=8)

        botoes = ttk.Frame(form)
        botoes.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        botoes.columnconfigure((0, 1), weight=1)

        ttk.Button(botoes, text="Salvar", style="Principal.TButton",
                   command=self.salvar).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(botoes, text="Novo produto",
                   command=self.novo).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.botao_excluir = ttk.Button(botoes, text="Excluir produto",
                                        style="Perigo.TButton", state="disabled",
                                        command=self.excluir)
        self.botao_excluir.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        ttk.Label(form, text="A imagem do produto é enviada pelo site\n"
                             "(Administração > Produtos).",
                  style="Subtitulo.TLabel").grid(row=7, column=0, columnspan=2,
                                                 sticky="w", pady=(14, 0))

    # ---------- dados ----------

    def carregar(self):

        api = self.painel.api

        def tarefa():
            return api.get("/api/categorias"), api.get("/api/produtos?todos=1")

        def sucesso(resultado):
            categorias, produtos = resultado

            self.categorias = {c["nome"]: c["id"] for c in categorias}
            self.combo_categoria.config(values=["Sem categoria"] + list(self.categorias))

            self._preencher(produtos)
            self.painel.avisar(f"{len(produtos)} produtos carregados.")

        self.painel.app.em_segundo_plano(tarefa, sucesso)

    def _preencher(self, produtos):

        manter = self.em_edicao

        self.produtos = {p["id"]: p for p in produtos}
        self.tabela.delete(*self.tabela.get_children())

        for p in produtos:
            tags = ()

            if not p["ativo"]:
                tags = ("oculto",)
            elif p["estoque"] == 0:
                tags = ("zerado",)
            elif p["estoque"] <= 5:
                tags = ("baixo",)

            self.tabela.insert("", "end", iid=str(p["id"]), tags=tags, values=(
                p["nome"], p["categoria"] or "Sem categoria", reais(p["preco"]),
                p["estoque"], "No cardápio" if p["ativo"] else "Oculto",
            ))

        if manter in self.produtos:
            self.tabela.selection_set(str(manter))
        else:
            self.novo()

    # ---------- formulário ----------

    def novo(self):

        self.em_edicao = None
        self.tabela.selection_remove(self.tabela.selection())

        self.nome.set("")
        self.categoria.set("Sem categoria")
        self.preco.set("")
        self.estoque.set("0")
        self.ativo.set(True)
        self.descricao.delete("1.0", "end")
        self.botao_excluir.config(state="disabled")

    def selecionar(self):

        selecao = self.tabela.selection()

        if not selecao:
            return

        p = self.produtos.get(int(selecao[0]))

        if p is None:
            return

        self.em_edicao = p["id"]

        self.nome.set(p["nome"])
        self.categoria.set(p["categoria"] or "Sem categoria")
        self.preco.set(f"{p['preco']:.2f}".replace(".", ","))
        self.estoque.set(str(p["estoque"]))
        self.ativo.set(bool(p["ativo"]))
        self.descricao.delete("1.0", "end")
        self.descricao.insert("1.0", p["descricao"] or "")
        self.botao_excluir.config(state="normal")

    def salvar(self):

        nome = self.nome.get().strip()

        if not nome:
            messagebox.showwarning("Produto", "Informe o nome do produto.")
            return

        try:
            preco = float(self.preco.get().strip().replace(",", "."))
            if preco < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Produto", "Informe um preço válido (ex.: 6,50).")
            return

        try:
            estoque = int(self.estoque.get())
            if estoque < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Produto", "O estoque deve ser um número inteiro, 0 ou mais.")
            return

        dados = {
            "nome": nome,
            "preco": preco,
            "estoque": estoque,
            "descricao": self.descricao.get("1.0", "end").strip(),
            "ativo": bool(self.ativo.get()),
            "categoria_id": self.categorias.get(self.categoria.get(), ""),
        }

        api = self.painel.api
        editando = self.em_edicao

        def tarefa():
            if editando:
                return api.put(f"/api/produtos/{editando}", dados)
            return api.post("/api/produtos", dados)

        def sucesso(produto):
            self.em_edicao = produto["id"]
            self.painel.avisar(f"Produto '{produto['nome']}' salvo.")
            self.carregar()

        self.painel.app.em_segundo_plano(tarefa, sucesso)

    def excluir(self):

        if not self.em_edicao:
            return

        produto = self.produtos[self.em_edicao]

        if not messagebox.askyesno(
                "Excluir produto",
                f"Excluir '{produto['nome']}'?\n"
                "Pedidos antigos continuam no histórico."):
            return

        api = self.painel.api
        produto_id = self.em_edicao

        def sucesso(_resultado):
            self.em_edicao = None
            self.painel.avisar(f"Produto '{produto['nome']}' excluído.")
            self.carregar()

        self.painel.app.em_segundo_plano(
            lambda: api.delete(f"/api/produtos/{produto_id}"), sucesso)


# ============================================================================
# ABA: RESUMO
# ============================================================================

class AbaResumo(ttk.Frame):

    def __init__(self, pai, painel):
        super().__init__(pai, padding=12)
        self.painel = painel

        topo = ttk.Frame(self)
        topo.pack(fill="x")

        self.numeros = {}

        for coluna, (chave, rotulo) in enumerate((
            ("pedidos_hoje", "Pedidos hoje"),
            ("faturamento_hoje", "Faturamento hoje"),
            ("pedidos_abertos", "Pedidos em aberto"),
            ("produtos_sem_estoque", "Produtos esgotados"),
        )):
            topo.columnconfigure(coluna, weight=1, uniform="cartao")

            cartao = ttk.Frame(topo, style="Cartao.TFrame", padding=14)
            cartao.grid(row=0, column=coluna, sticky="ew", padx=(0 if coluna == 0 else 10, 0))

            numero = ttk.Label(cartao, text="-", style="Numero.TLabel")
            numero.pack(anchor="w")

            ttk.Label(cartao, text=rotulo, background="white",
                      foreground="#54605a").pack(anchor="w")

            self.numeros[chave] = numero

        listas = ttk.Frame(self)
        listas.pack(fill="both", expand=True, pady=(18, 0))
        listas.columnconfigure((0, 1), weight=1, uniform="lista")
        listas.rowconfigure(0, weight=1)

        self.vendidos = self._criar_lista(listas, 0, "Mais vendidos", "Vendidos")
        self.baixo = self._criar_lista(listas, 1, "Estoque baixo (até 5)", "Estoque")

        ttk.Button(self, text="Atualizar", command=self.carregar).pack(
            anchor="e", pady=(10, 0))

    def _criar_lista(self, pai, coluna, titulo, rotulo_valor):

        moldura = ttk.LabelFrame(pai, text=titulo, padding=8)
        moldura.grid(row=0, column=coluna, sticky="nsew",
                     padx=(0 if coluna == 0 else 10, 0))
        moldura.rowconfigure(0, weight=1)
        moldura.columnconfigure(0, weight=1)

        tabela = ttk.Treeview(moldura, columns=("nome", "valor"), show="headings",
                              height=7)
        tabela.heading("nome", text="Produto")
        tabela.heading("valor", text=rotulo_valor)
        tabela.column("nome", width=200, anchor="w")
        tabela.column("valor", width=80, anchor="e")
        tabela.grid(row=0, column=0, sticky="nsew")

        return tabela

    def carregar(self):

        api = self.painel.api

        def sucesso(d):
            self.numeros["pedidos_hoje"].config(text=str(d["pedidos_hoje"]))
            self.numeros["faturamento_hoje"].config(text=reais(d["faturamento_hoje"]))
            self.numeros["pedidos_abertos"].config(text=str(d["pedidos_abertos"]))
            self.numeros["produtos_sem_estoque"].config(
                text=str(d["produtos_sem_estoque"]))

            self.vendidos.delete(*self.vendidos.get_children())
            for v in d["mais_vendidos"]:
                self.vendidos.insert("", "end", values=(v["nome"], v["vendidos"]))

            self.baixo.delete(*self.baixo.get_children())
            for p in d["estoque_baixo"]:
                self.baixo.insert("", "end", values=(p["nome"], p["estoque"]))

            self.painel.avisar(
                f"Resumo atualizado às {datetime.now():%H:%M:%S}. "
                f"Faturamento total: {reais(d['faturamento_total'])}.")

        self.painel.app.em_segundo_plano(lambda: api.get("/api/dashboard"), sucesso)


# ============================================================================
# EXECUÇÃO
# ============================================================================

if __name__ == "__main__":

    App().mainloop()
