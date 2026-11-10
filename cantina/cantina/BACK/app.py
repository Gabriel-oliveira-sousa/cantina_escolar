# -*- coding: utf-8 -*-
"""
app.py

API REST da Cantina (Flask + SQLite).

Base: projeto Dragon Suplementos (Guilherme Teles da Silva e Arthur Uezu da
Cruz, com auxílio de Gustavo Moraes e Mateus Valente), adaptado para a
cantina com: login por token, controle de acesso (aluno x administrador),
pedidos com baixa de estoque, senha de retirada e painel de senhas.
"""

import os
import re
import sqlite3
import uuid
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from banco_dados import PASTA_BASE, inicializar_banco, obter_conexao


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

app = Flask(__name__)

# Atrás do proxy do Render, isso faz o Flask enxergar o https corretamente.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Imagens de produto: até 2 MB.
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

CORS(app)

PASTA_UPLOADS = os.environ.get(
    "UPLOAD_FOLDER",
    os.path.join(PASTA_BASE, "uploads")
)
os.makedirs(PASTA_UPLOADS, exist_ok=True)

EXTENSOES_IMAGEM = {"png", "jpg", "jpeg", "webp", "gif"}

# Chave que assina os tokens de login. Em produção, defina SECRET_KEY.
SECRET_KEY = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")
TOKEN_VALIDADE_SEGUNDOS = 12 * 60 * 60  # 12 horas

serializador = URLSafeTimedSerializer(SECRET_KEY, salt="cantina-login")

TIPOS_CADASTRO_PUBLICO = ("aluno", "professor", "funcionario")
FORMAS_PAGAMENTO = ("dinheiro", "pix", "cartao")
ESTOQUE_BAIXO = 5

# De qual status um pedido pode ir para qual.
TRANSICOES_STATUS = {
    "recebido": {"preparando", "pronto", "cancelado"},
    "preparando": {"pronto", "cancelado"},
    "pronto": {"entregue", "cancelado"},
    "entregue": set(),
    "cancelado": set(),
}

STATUS_ABERTOS = ("recebido", "preparando", "pronto")

REGEX_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

inicializar_banco()


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def erro(mensagem, status=400):
    return jsonify({"erro": mensagem}), status


def dados_requisicao():
    """Aceita JSON (Tkinter, testes) ou formulário (envio de imagem)."""

    dados = request.get_json(silent=True)

    if isinstance(dados, dict):
        return dados

    return request.form.to_dict()


def url_imagem(arquivo):

    if not arquivo:
        return None

    return f"{request.url_root.rstrip('/')}/uploads/{arquivo}"


def produto_para_dict(linha):

    estoque = linha["estoque"]
    ativo = bool(linha["ativo"])

    return {
        "id": linha["id"],
        "nome": linha["nome"],
        "descricao": linha["descricao"],
        "preco": linha["preco"],
        "estoque": estoque,
        "ativo": ativo,
        "disponivel": ativo and estoque > 0,
        "categoria_id": linha["categoria_id"],
        "categoria": linha["categoria_nome"],
        "imagem_url": url_imagem(linha["imagem"]),
        "data_cadastro": linha["data_cadastro"],
    }


def usuario_para_dict(linha):

    return {
        "id": linha["id"],
        "nome": linha["nome"],
        "email": linha["email"],
        "telefone": linha["telefone"],
        "turma": linha["turma"],
        "tipo": linha["tipo"],
        "data_cadastro": linha["data_cadastro"],
    }


SQL_PRODUTO = """
    SELECT p.*, c.nome AS categoria_nome
    FROM produtos p
    LEFT JOIN categorias c ON p.categoria_id = c.id
"""


def buscar_produto(conexao, produto_id):

    return conexao.execute(
        SQL_PRODUTO + " WHERE p.id = ?",
        (produto_id,)
    ).fetchone()


def numero_positivo(valor, nome, inteiro=False):
    """Converte e valida um número >= 0. Retorna (valor, mensagem_de_erro)."""

    try:
        numero = int(valor) if inteiro else float(valor)

    except (ValueError, TypeError):
        tipo = "um número inteiro" if inteiro else "um número"
        return None, f"O campo '{nome}' deve ser {tipo}"

    if numero < 0:
        return None, f"O campo '{nome}' não pode ser negativo"

    return numero, None


def salvar_imagem(arquivo):
    """Salva a imagem enviada. Retorna (nome_do_arquivo, erro)."""

    if arquivo is None or arquivo.filename == "":
        return None, None

    extensao = arquivo.filename.rsplit(".", 1)[-1].lower()

    if "." not in arquivo.filename or extensao not in EXTENSOES_IMAGEM:
        return None, "Formato de imagem inválido (use png, jpg, webp ou gif)"

    nome = f"{uuid.uuid4().hex}_{secure_filename(arquivo.filename)}"
    arquivo.save(os.path.join(PASTA_UPLOADS, nome))

    return nome, None


# ============================================================================
# AUTENTICAÇÃO
# ============================================================================

def gerar_token(usuario_id):
    return serializador.dumps({"id": usuario_id})


def usuario_atual():
    """Lê o cabeçalho 'Authorization: Bearer <token>' e devolve o usuário."""

    cabecalho = request.headers.get("Authorization", "")

    if not cabecalho.startswith("Bearer "):
        return None

    token = cabecalho[len("Bearer "):].strip()

    try:
        dados = serializador.loads(token, max_age=TOKEN_VALIDADE_SEGUNDOS)

    except (BadSignature, SignatureExpired):
        return None

    conexao = obter_conexao()

    usuario = conexao.execute(
        "SELECT * FROM usuarios WHERE id = ?",
        (dados.get("id"),)
    ).fetchone()

    conexao.close()

    return usuario


def login_obrigatorio(funcao):

    @wraps(funcao)
    def envoltorio(*args, **kwargs):

        usuario = usuario_atual()

        if usuario is None:
            return erro("Faça login para continuar", 401)

        return funcao(usuario, *args, **kwargs)

    return envoltorio


def admin_obrigatorio(funcao):

    @wraps(funcao)
    def envoltorio(*args, **kwargs):

        usuario = usuario_atual()

        if usuario is None:
            return erro("Faça login para continuar", 401)

        if usuario["tipo"] != "admin":
            return erro("Acesso restrito ao administrador", 403)

        return funcao(usuario, *args, **kwargs)

    return envoltorio


# ============================================================================
# TRATAMENTO DE ERROS
# ============================================================================

@app.errorhandler(404)
def erro_404(e):
    return erro("Rota não encontrada", 404)


@app.errorhandler(405)
def erro_405(e):
    return erro("Método não permitido para esta rota", 405)


@app.errorhandler(413)
def erro_413(e):
    return erro("Arquivo muito grande (máximo 2 MB)", 413)


@app.errorhandler(500)
def erro_500(e):
    return erro("Erro interno do servidor", 500)


# ============================================================================
# ROTAS GERAIS
# ============================================================================

@app.route("/", methods=["GET"])
def rota_inicial():

    return jsonify({
        "nome": "Cantina API",
        "status": "online",
        "mensagem": "Back-end funcionando!"
    })


@app.route("/uploads/<path:arquivo>", methods=["GET"])
def servir_imagem(arquivo):
    return send_from_directory(PASTA_UPLOADS, arquivo)


# ============================================================================
# CATEGORIAS
# ============================================================================

@app.route("/api/categorias", methods=["GET"])
def listar_categorias():

    conexao = obter_conexao()

    linhas = conexao.execute(
        "SELECT id, nome FROM categorias ORDER BY id"
    ).fetchall()

    conexao.close()

    return jsonify([dict(linha) for linha in linhas])


@app.route("/api/categorias", methods=["POST"])
@admin_obrigatorio
def criar_categoria(admin):

    nome = (dados_requisicao().get("nome") or "").strip()

    if not nome:
        return erro("O campo 'nome' é obrigatório")

    conexao = obter_conexao()

    try:
        cursor = conexao.execute(
            "INSERT INTO categorias (nome) VALUES (?)",
            (nome,)
        )
        conexao.commit()

    except sqlite3.IntegrityError:
        conexao.close()
        return erro("Já existe uma categoria com esse nome", 409)

    nova_id = cursor.lastrowid
    conexao.close()

    return jsonify({"id": nova_id, "nome": nome}), 201


@app.route("/api/categorias/<int:categoria_id>", methods=["DELETE"])
@admin_obrigatorio
def excluir_categoria(admin, categoria_id):

    conexao = obter_conexao()

    existe = conexao.execute(
        "SELECT id FROM categorias WHERE id = ?",
        (categoria_id,)
    ).fetchone()

    if existe is None:
        conexao.close()
        return erro("Categoria não encontrada", 404)

    # Os produtos da categoria ficam "sem categoria" (ON DELETE SET NULL).
    conexao.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
    conexao.commit()
    conexao.close()

    return jsonify({"mensagem": "Categoria excluída com sucesso"})


# ============================================================================
# PRODUTOS
# ============================================================================

@app.route("/api/produtos", methods=["GET"])
def listar_produtos():
    """
    Público: devolve só produtos ativos.
    Administrador com ?todos=1: devolve também os inativos.
    Filtros opcionais: ?categoria=<id>  ?busca=<texto>
    """

    condicoes = []
    parametros = []

    quer_todos = request.args.get("todos") == "1"
    usuario = usuario_atual() if quer_todos else None

    if not (usuario is not None and usuario["tipo"] == "admin"):
        condicoes.append("p.ativo = 1")

    categoria = request.args.get("categoria")
    if categoria and categoria.isdigit():
        condicoes.append("p.categoria_id = ?")
        parametros.append(int(categoria))

    busca = (request.args.get("busca") or "").strip()
    if busca:
        condicoes.append("(p.nome LIKE ? OR p.descricao LIKE ?)")
        parametros += [f"%{busca}%", f"%{busca}%"]

    sql = SQL_PRODUTO

    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)

    sql += " ORDER BY p.categoria_id, p.nome"

    conexao = obter_conexao()
    linhas = conexao.execute(sql, parametros).fetchall()
    conexao.close()

    return jsonify([produto_para_dict(linha) for linha in linhas])


@app.route("/api/produtos/<int:produto_id>", methods=["GET"])
def obter_produto(produto_id):

    conexao = obter_conexao()
    linha = buscar_produto(conexao, produto_id)
    conexao.close()

    if linha is None:
        return erro("Produto não encontrado", 404)

    return jsonify(produto_para_dict(linha))


def resolver_categoria(conexao, dados):
    """
    Aceita 'categoria_id' (número) ou 'categoria' (nome).
    Retorna (id, erro). id None sem erro = sem categoria.
    """

    if dados.get("categoria_id") not in (None, ""):

        linha = conexao.execute(
            "SELECT id FROM categorias WHERE id = ?",
            (dados["categoria_id"],)
        ).fetchone()

    elif dados.get("categoria"):

        linha = conexao.execute(
            "SELECT id FROM categorias WHERE LOWER(nome) = LOWER(?)",
            (str(dados["categoria"]).strip(),)
        ).fetchone()

    else:
        return None, None

    if linha is None:
        return None, "A categoria informada não existe"

    return linha["id"], None


@app.route("/api/produtos", methods=["POST"])
@admin_obrigatorio
def criar_produto(admin):

    dados = dados_requisicao()

    nome = (dados.get("nome") or "").strip()

    if not nome:
        return erro("O campo 'nome' é obrigatório")

    if len(nome) > 80:
        return erro("O nome pode ter no máximo 80 caracteres")

    if dados.get("preco") in (None, ""):
        return erro("O campo 'preco' é obrigatório")

    preco, mensagem = numero_positivo(dados.get("preco"), "preco")
    if mensagem:
        return erro(mensagem)

    estoque, mensagem = numero_positivo(
        dados.get("estoque", 0), "estoque", inteiro=True
    )
    if mensagem:
        return erro(mensagem)

    imagem, mensagem = salvar_imagem(request.files.get("imagem"))
    if mensagem:
        return erro(mensagem)

    conexao = obter_conexao()

    categoria_id, mensagem = resolver_categoria(conexao, dados)
    if mensagem:
        conexao.close()
        return erro(mensagem)

    cursor = conexao.execute(
        """
        INSERT INTO produtos
            (nome, descricao, imagem, preco, estoque, categoria_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (nome, dados.get("descricao"), imagem, preco, estoque, categoria_id)
    )
    conexao.commit()

    linha = buscar_produto(conexao, cursor.lastrowid)
    conexao.close()

    return jsonify(produto_para_dict(linha)), 201


@app.route("/api/produtos/<int:produto_id>", methods=["PUT"])
@admin_obrigatorio
def atualizar_produto(admin, produto_id):

    dados = dados_requisicao()

    conexao = obter_conexao()

    atual = conexao.execute(
        "SELECT * FROM produtos WHERE id = ?",
        (produto_id,)
    ).fetchone()

    if atual is None:
        conexao.close()
        return erro("Produto não encontrado", 404)

    nome = (dados.get("nome", atual["nome"]) or "").strip()

    if not nome:
        conexao.close()
        return erro("O campo 'nome' não pode ficar vazio")

    if len(nome) > 80:
        conexao.close()
        return erro("O nome pode ter no máximo 80 caracteres")

    preco, mensagem = numero_positivo(dados.get("preco", atual["preco"]), "preco")
    if mensagem:
        conexao.close()
        return erro(mensagem)

    estoque, mensagem = numero_positivo(
        dados.get("estoque", atual["estoque"]), "estoque", inteiro=True
    )
    if mensagem:
        conexao.close()
        return erro(mensagem)

    if "categoria_id" in dados or "categoria" in dados:
        categoria_id, mensagem = resolver_categoria(conexao, dados)
        if mensagem:
            conexao.close()
            return erro(mensagem)
    else:
        categoria_id = atual["categoria_id"]

    ativo = dados.get("ativo", atual["ativo"])
    ativo = 0 if str(ativo).lower() in ("0", "false", "off", "") else 1

    imagem, mensagem = salvar_imagem(request.files.get("imagem"))
    if mensagem:
        conexao.close()
        return erro(mensagem)

    if imagem is None:
        imagem = atual["imagem"]

    conexao.execute(
        """
        UPDATE produtos
        SET nome = ?, descricao = ?, imagem = ?, preco = ?,
            estoque = ?, ativo = ?, categoria_id = ?
        WHERE id = ?
        """,
        (
            nome,
            dados.get("descricao", atual["descricao"]),
            imagem, preco, estoque, ativo, categoria_id, produto_id
        )
    )
    conexao.commit()

    linha = buscar_produto(conexao, produto_id)
    conexao.close()

    return jsonify(produto_para_dict(linha))


@app.route("/api/produtos/<int:produto_id>", methods=["DELETE"])
@admin_obrigatorio
def excluir_produto(admin, produto_id):

    conexao = obter_conexao()

    existe = conexao.execute(
        "SELECT id FROM produtos WHERE id = ?",
        (produto_id,)
    ).fetchone()

    if existe is None:
        conexao.close()
        return erro("Produto não encontrado", 404)

    conexao.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
    conexao.commit()
    conexao.close()

    return jsonify({"mensagem": "Produto excluído com sucesso"})


# ============================================================================
# USUÁRIOS E LOGIN
# ============================================================================

@app.route("/api/usuarios", methods=["POST"])
def criar_usuario():

    dados = dados_requisicao()

    nome = (dados.get("nome") or "").strip()
    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""
    tipo = dados.get("tipo") or "aluno"
    telefone = (dados.get("telefone") or "").strip() or None
    turma = (dados.get("turma") or "").strip() or None

    if not nome:
        return erro("O campo 'nome' é obrigatório")

    if not REGEX_EMAIL.match(email):
        return erro("Informe um e-mail válido")

    if len(senha) < 6:
        return erro("A senha deve ter no mínimo 6 caracteres")

    # O tipo 'admin' nunca pode ser escolhido no cadastro público.
    if tipo not in TIPOS_CADASTRO_PUBLICO:
        return erro("Tipo de usuário inválido")

    conexao = obter_conexao()

    try:
        cursor = conexao.execute(
            """
            INSERT INTO usuarios
                (nome, email, telefone, turma, tipo, senha_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (nome, email, telefone, turma, tipo, generate_password_hash(senha))
        )
        conexao.commit()

    except sqlite3.IntegrityError:
        conexao.close()
        return erro("Já existe um usuário com esse e-mail", 409)

    linha = conexao.execute(
        "SELECT * FROM usuarios WHERE id = ?",
        (cursor.lastrowid,)
    ).fetchone()

    conexao.close()

    return jsonify({
        "mensagem": "Cadastro realizado com sucesso",
        "usuario": usuario_para_dict(linha),
        "token": gerar_token(linha["id"]),
    }), 201


@app.route("/api/login", methods=["POST"])
def login():

    dados = dados_requisicao()

    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""

    if not email or not senha:
        return erro("Informe e-mail e senha")

    conexao = obter_conexao()

    usuario = conexao.execute(
        "SELECT * FROM usuarios WHERE email = ?",
        (email,)
    ).fetchone()

    conexao.close()

    # A mesma mensagem para e-mail e senha errados evita revelar
    # quais e-mails estão cadastrados.
    if usuario is None or not check_password_hash(usuario["senha_hash"], senha):
        return erro("E-mail ou senha inválidos", 401)

    return jsonify({
        "mensagem": "Login realizado com sucesso",
        "usuario": usuario_para_dict(usuario),
        "token": gerar_token(usuario["id"]),
    })


@app.route("/api/me", methods=["GET"])
@login_obrigatorio
def perfil(usuario):
    return jsonify(usuario_para_dict(usuario))


@app.route("/api/usuarios", methods=["GET"])
@admin_obrigatorio
def listar_usuarios(admin):

    conexao = obter_conexao()

    linhas = conexao.execute(
        "SELECT * FROM usuarios ORDER BY id"
    ).fetchall()

    conexao.close()

    return jsonify([usuario_para_dict(linha) for linha in linhas])


# ============================================================================
# CARRINHO (do usuário logado)
# ============================================================================

def montar_carrinho(conexao, usuario_id):

    linhas = conexao.execute(
        """
        SELECT ci.id, ci.produto_id, ci.quantidade,
               p.nome, p.preco, p.estoque, p.ativo, p.imagem
        FROM carrinho_itens ci
        JOIN produtos p ON ci.produto_id = p.id
        WHERE ci.usuario_id = ?
        ORDER BY ci.id
        """,
        (usuario_id,)
    ).fetchall()

    itens = []
    total = 0.0

    for linha in linhas:

        subtotal = round(linha["preco"] * linha["quantidade"], 2)
        total += subtotal

        itens.append({
            "id": linha["id"],
            "produto_id": linha["produto_id"],
            "nome": linha["nome"],
            "preco": linha["preco"],
            "quantidade": linha["quantidade"],
            "subtotal": subtotal,
            "estoque": linha["estoque"],
            "imagem_url": url_imagem(linha["imagem"]),
            # Avisa o front se o item deixou de ser vendável.
            "disponivel": bool(linha["ativo"])
                          and linha["estoque"] >= linha["quantidade"],
        })

    return {"itens": itens, "total": round(total, 2)}


@app.route("/api/carrinho", methods=["GET"])
@login_obrigatorio
def obter_carrinho(usuario):

    conexao = obter_conexao()
    carrinho = montar_carrinho(conexao, usuario["id"])
    conexao.close()

    return jsonify(carrinho)


@app.route("/api/carrinho", methods=["POST"])
@login_obrigatorio
def adicionar_ao_carrinho(usuario):

    dados = dados_requisicao()

    try:
        produto_id = int(dados.get("produto_id"))
        quantidade = int(dados.get("quantidade", 1))

    except (ValueError, TypeError):
        return erro("Informe 'produto_id' e 'quantidade' válidos")

    if quantidade <= 0:
        return erro("A quantidade deve ser maior que 0")

    conexao = obter_conexao()

    produto = conexao.execute(
        "SELECT id, nome, estoque, ativo FROM produtos WHERE id = ?",
        (produto_id,)
    ).fetchone()

    if produto is None or not produto["ativo"]:
        conexao.close()
        return erro("Produto não encontrado", 404)

    item = conexao.execute(
        """
        SELECT id, quantidade FROM carrinho_itens
        WHERE usuario_id = ? AND produto_id = ?
        """,
        (usuario["id"], produto_id)
    ).fetchone()

    nova_quantidade = quantidade + (item["quantidade"] if item else 0)

    if nova_quantidade > produto["estoque"]:
        conexao.close()
        return erro(
            f"Estoque insuficiente para '{produto['nome']}' "
            f"(disponível: {produto['estoque']})",
            409
        )

    if item:
        conexao.execute(
            "UPDATE carrinho_itens SET quantidade = ? WHERE id = ?",
            (nova_quantidade, item["id"])
        )
    else:
        conexao.execute(
            """
            INSERT INTO carrinho_itens (usuario_id, produto_id, quantidade)
            VALUES (?, ?, ?)
            """,
            (usuario["id"], produto_id, quantidade)
        )

    conexao.commit()

    carrinho = montar_carrinho(conexao, usuario["id"])
    conexao.close()

    return jsonify(carrinho), 201


@app.route("/api/carrinho/<int:item_id>", methods=["PUT"])
@login_obrigatorio
def atualizar_item_carrinho(usuario, item_id):

    try:
        quantidade = int(dados_requisicao().get("quantidade"))

    except (ValueError, TypeError):
        return erro("O campo 'quantidade' deve ser um número inteiro")

    conexao = obter_conexao()

    item = conexao.execute(
        """
        SELECT ci.id, p.estoque, p.nome
        FROM carrinho_itens ci
        JOIN produtos p ON ci.produto_id = p.id
        WHERE ci.id = ? AND ci.usuario_id = ?
        """,
        (item_id, usuario["id"])
    ).fetchone()

    if item is None:
        conexao.close()
        return erro("Item do carrinho não encontrado", 404)

    if quantidade <= 0:
        conexao.execute("DELETE FROM carrinho_itens WHERE id = ?", (item_id,))

    elif quantidade > item["estoque"]:
        conexao.close()
        return erro(
            f"Estoque insuficiente para '{item['nome']}' "
            f"(disponível: {item['estoque']})",
            409
        )

    else:
        conexao.execute(
            "UPDATE carrinho_itens SET quantidade = ? WHERE id = ?",
            (quantidade, item_id)
        )

    conexao.commit()

    carrinho = montar_carrinho(conexao, usuario["id"])
    conexao.close()

    return jsonify(carrinho)


@app.route("/api/carrinho/<int:item_id>", methods=["DELETE"])
@login_obrigatorio
def remover_item_carrinho(usuario, item_id):

    conexao = obter_conexao()

    cursor = conexao.execute(
        "DELETE FROM carrinho_itens WHERE id = ? AND usuario_id = ?",
        (item_id, usuario["id"])
    )
    conexao.commit()

    if cursor.rowcount == 0:
        conexao.close()
        return erro("Item do carrinho não encontrado", 404)

    carrinho = montar_carrinho(conexao, usuario["id"])
    conexao.close()

    return jsonify(carrinho)


@app.route("/api/carrinho", methods=["DELETE"])
@login_obrigatorio
def limpar_carrinho(usuario):

    conexao = obter_conexao()

    conexao.execute(
        "DELETE FROM carrinho_itens WHERE usuario_id = ?",
        (usuario["id"],)
    )
    conexao.commit()
    conexao.close()

    return jsonify({"itens": [], "total": 0})


# ============================================================================
# PEDIDOS
# ============================================================================

def montar_pedido(conexao, linha, com_itens=True):

    pedido = {
        "id": linha["id"],
        "senha": linha["senha"],
        "status": linha["status"],
        "forma_pagamento": linha["forma_pagamento"],
        "observacao": linha["observacao"],
        "total": linha["total"],
        "criado_em": linha["criado_em"],
        "atualizado_em": linha["atualizado_em"],
        "usuario_id": linha["usuario_id"],
        "cliente": linha["cliente_nome"],
        "turma": linha["cliente_turma"],
    }

    if com_itens:

        itens = conexao.execute(
            """
            SELECT nome, preco_unit, quantidade
            FROM pedido_itens
            WHERE pedido_id = ?
            ORDER BY id
            """,
            (linha["id"],)
        ).fetchall()

        pedido["itens"] = [
            {
                "nome": item["nome"],
                "preco_unit": item["preco_unit"],
                "quantidade": item["quantidade"],
                "subtotal": round(item["preco_unit"] * item["quantidade"], 2),
            }
            for item in itens
        ]

    return pedido


SQL_PEDIDO = """
    SELECT pe.*, u.nome AS cliente_nome, u.turma AS cliente_turma
    FROM pedidos pe
    JOIN usuarios u ON pe.usuario_id = u.id
"""


@app.route("/api/pedidos", methods=["POST"])
@login_obrigatorio
def criar_pedido(usuario):
    """Transforma o carrinho do usuário em um pedido."""

    dados = dados_requisicao()

    forma_pagamento = dados.get("forma_pagamento", "dinheiro")

    if forma_pagamento not in FORMAS_PAGAMENTO:
        return erro("Forma de pagamento inválida")

    observacao = (dados.get("observacao") or "").strip()[:200] or None

    conexao = obter_conexao()

    # BEGIN IMMEDIATE trava o banco para escrita: dois pedidos simultâneos
    # não conseguem vender a mesma última unidade nem receber a mesma senha.
    conexao.execute("BEGIN IMMEDIATE")

    try:
        itens = conexao.execute(
            """
            SELECT ci.id, ci.produto_id, ci.quantidade,
                   p.nome, p.preco, p.estoque, p.ativo
            FROM carrinho_itens ci
            JOIN produtos p ON ci.produto_id = p.id
            WHERE ci.usuario_id = ?
            """,
            (usuario["id"],)
        ).fetchall()

        if not itens:
            conexao.rollback()
            conexao.close()
            return erro("Seu carrinho está vazio")

        for item in itens:

            if not item["ativo"] or item["estoque"] < item["quantidade"]:
                conexao.rollback()
                conexao.close()
                return erro(
                    f"'{item['nome']}' não tem estoque suficiente "
                    f"(disponível: {item['estoque']}). "
                    "Ajuste o carrinho e tente de novo.",
                    409
                )

        total = round(
            sum(item["preco"] * item["quantidade"] for item in itens), 2
        )

        senha = conexao.execute(
            """
            SELECT COALESCE(MAX(senha), 0) + 1
            FROM pedidos
            WHERE date(criado_em) = date('now', 'localtime')
            """
        ).fetchone()[0]

        cursor = conexao.execute(
            """
            INSERT INTO pedidos
                (usuario_id, senha, forma_pagamento, observacao, total)
            VALUES (?, ?, ?, ?, ?)
            """,
            (usuario["id"], senha, forma_pagamento, observacao, total)
        )

        pedido_id = cursor.lastrowid

        for item in itens:

            conexao.execute(
                """
                INSERT INTO pedido_itens
                    (pedido_id, produto_id, nome, preco_unit, quantidade)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    pedido_id, item["produto_id"], item["nome"],
                    item["preco"], item["quantidade"]
                )
            )

            conexao.execute(
                "UPDATE produtos SET estoque = estoque - ? WHERE id = ?",
                (item["quantidade"], item["produto_id"])
            )

        conexao.execute(
            "DELETE FROM carrinho_itens WHERE usuario_id = ?",
            (usuario["id"],)
        )

        conexao.commit()

    except Exception:
        conexao.rollback()
        conexao.close()
        raise

    linha = conexao.execute(
        SQL_PEDIDO + " WHERE pe.id = ?",
        (pedido_id,)
    ).fetchone()

    pedido = montar_pedido(conexao, linha)
    conexao.close()

    return jsonify(pedido), 201


@app.route("/api/pedidos", methods=["GET"])
@login_obrigatorio
def listar_pedidos(usuario):
    """
    Aluno/professor/funcionário: só os próprios pedidos.
    Administrador: todos. Filtros: ?status=abertos|<status>  ?data=hoje
    """

    condicoes = []
    parametros = []

    if usuario["tipo"] != "admin":
        condicoes.append("pe.usuario_id = ?")
        parametros.append(usuario["id"])

    status = request.args.get("status")

    if status == "abertos":
        condicoes.append("pe.status IN ('recebido', 'preparando', 'pronto')")

    elif status in TRANSICOES_STATUS:
        condicoes.append("pe.status = ?")
        parametros.append(status)

    if request.args.get("data") == "hoje":
        condicoes.append("date(pe.criado_em) = date('now', 'localtime')")

    sql = SQL_PEDIDO

    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)

    sql += " ORDER BY pe.id DESC LIMIT 200"

    conexao = obter_conexao()

    linhas = conexao.execute(sql, parametros).fetchall()
    pedidos = [montar_pedido(conexao, linha) for linha in linhas]

    conexao.close()

    return jsonify(pedidos)


@app.route("/api/pedidos/<int:pedido_id>", methods=["GET"])
@login_obrigatorio
def obter_pedido(usuario, pedido_id):

    conexao = obter_conexao()

    linha = conexao.execute(
        SQL_PEDIDO + " WHERE pe.id = ?",
        (pedido_id,)
    ).fetchone()

    if linha is None or (
        usuario["tipo"] != "admin" and linha["usuario_id"] != usuario["id"]
    ):
        conexao.close()
        return erro("Pedido não encontrado", 404)

    pedido = montar_pedido(conexao, linha)
    conexao.close()

    return jsonify(pedido)


def alterar_status(conexao, pedido_id, novo_status):
    """
    Muda o status respeitando TRANSICOES_STATUS. Ao cancelar, devolve os
    itens ao estoque. Retorna mensagem de erro ou None.
    """

    pedido = conexao.execute(
        "SELECT status FROM pedidos WHERE id = ?",
        (pedido_id,)
    ).fetchone()

    if novo_status not in TRANSICOES_STATUS[pedido["status"]]:
        return (
            f"Não é possível mudar de '{pedido['status']}' "
            f"para '{novo_status}'"
        )

    if novo_status == "cancelado":

        conexao.execute(
            """
            UPDATE produtos
            SET estoque = estoque + (
                SELECT quantidade FROM pedido_itens
                WHERE pedido_itens.pedido_id = ?
                  AND pedido_itens.produto_id = produtos.id
            )
            WHERE id IN (
                SELECT produto_id FROM pedido_itens
                WHERE pedido_id = ? AND produto_id IS NOT NULL
            )
            """,
            (pedido_id, pedido_id)
        )

    conexao.execute(
        """
        UPDATE pedidos
        SET status = ?, atualizado_em = datetime('now', 'localtime')
        WHERE id = ?
        """,
        (novo_status, pedido_id)
    )

    conexao.commit()

    return None


@app.route("/api/pedidos/<int:pedido_id>/status", methods=["PUT"])
@admin_obrigatorio
def atualizar_status_pedido(admin, pedido_id):

    novo_status = dados_requisicao().get("status")

    if novo_status not in TRANSICOES_STATUS:
        return erro("Status inválido")

    conexao = obter_conexao()

    existe = conexao.execute(
        "SELECT id FROM pedidos WHERE id = ?",
        (pedido_id,)
    ).fetchone()

    if existe is None:
        conexao.close()
        return erro("Pedido não encontrado", 404)

    mensagem = alterar_status(conexao, pedido_id, novo_status)

    if mensagem:
        conexao.close()
        return erro(mensagem, 409)

    linha = conexao.execute(
        SQL_PEDIDO + " WHERE pe.id = ?",
        (pedido_id,)
    ).fetchone()

    pedido = montar_pedido(conexao, linha)
    conexao.close()

    return jsonify(pedido)


@app.route("/api/pedidos/<int:pedido_id>/cancelar", methods=["POST"])
@login_obrigatorio
def cancelar_pedido(usuario, pedido_id):
    """O cliente só cancela enquanto o pedido ainda está 'recebido'."""

    conexao = obter_conexao()

    linha = conexao.execute(
        "SELECT usuario_id, status FROM pedidos WHERE id = ?",
        (pedido_id,)
    ).fetchone()

    if linha is None or (
        usuario["tipo"] != "admin" and linha["usuario_id"] != usuario["id"]
    ):
        conexao.close()
        return erro("Pedido não encontrado", 404)

    if usuario["tipo"] != "admin" and linha["status"] != "recebido":
        conexao.close()
        return erro(
            "O pedido já começou a ser preparado. "
            "Fale com o atendente da cantina para cancelar.",
            409
        )

    mensagem = alterar_status(conexao, pedido_id, "cancelado")

    if mensagem:
        conexao.close()
        return erro(mensagem, 409)

    conexao.close()

    return jsonify({"mensagem": "Pedido cancelado"})


# ============================================================================
# PAINEL DE SENHAS (público)
# ============================================================================

@app.route("/api/painel-senhas", methods=["GET"])
def painel_senhas():
    """Só os números das senhas de hoje, sem nenhum dado pessoal."""

    conexao = obter_conexao()

    linhas = conexao.execute(
        """
        SELECT senha, status FROM pedidos
        WHERE date(criado_em) = date('now', 'localtime')
          AND status IN ('recebido', 'preparando', 'pronto')
        ORDER BY senha
        """
    ).fetchall()

    conexao.close()

    return jsonify({
        "preparando": [
            l["senha"] for l in linhas
            if l["status"] in ("recebido", "preparando")
        ],
        "prontos": [l["senha"] for l in linhas if l["status"] == "pronto"],
    })


# ============================================================================
# DASHBOARD (administrador)
# ============================================================================

@app.route("/api/dashboard", methods=["GET"])
@admin_obrigatorio
def dashboard(admin):

    conexao = obter_conexao()

    def valor(sql, parametros=()):
        return conexao.execute(sql, parametros).fetchone()[0]

    hoje = "date(criado_em) = date('now', 'localtime')"

    resultado = {
        "total_produtos": valor("SELECT COUNT(*) FROM produtos"),
        "produtos_ativos": valor(
            "SELECT COUNT(*) FROM produtos WHERE ativo = 1"
        ),
        "produtos_sem_estoque": valor(
            "SELECT COUNT(*) FROM produtos WHERE ativo = 1 AND estoque = 0"
        ),
        "total_usuarios": valor(
            "SELECT COUNT(*) FROM usuarios WHERE tipo != 'admin'"
        ),
        "pedidos_hoje": valor(
            f"SELECT COUNT(*) FROM pedidos WHERE {hoje} "
            "AND status != 'cancelado'"
        ),
        "pedidos_abertos": valor(
            "SELECT COUNT(*) FROM pedidos "
            "WHERE status IN ('recebido', 'preparando', 'pronto')"
        ),
        # Faturamento = pedidos não cancelados.
        "faturamento_hoje": round(valor(
            f"SELECT COALESCE(SUM(total), 0) FROM pedidos WHERE {hoje} "
            "AND status != 'cancelado'"
        ), 2),
        "faturamento_total": round(valor(
            "SELECT COALESCE(SUM(total), 0) FROM pedidos "
            "WHERE status != 'cancelado'"
        ), 2),
    }

    resultado["pedidos_por_status"] = {
        linha["status"]: linha["quantidade"]
        for linha in conexao.execute(
            "SELECT status, COUNT(*) AS quantidade FROM pedidos "
            "GROUP BY status"
        )
    }

    resultado["mais_vendidos"] = [
        dict(linha) for linha in conexao.execute(
            """
            SELECT pi.nome, SUM(pi.quantidade) AS vendidos
            FROM pedido_itens pi
            JOIN pedidos pe ON pi.pedido_id = pe.id
            WHERE pe.status != 'cancelado'
            GROUP BY pi.nome
            ORDER BY vendidos DESC, pi.nome
            LIMIT 5
            """
        )
    ]

    resultado["estoque_baixo"] = [
        dict(linha) for linha in conexao.execute(
            """
            SELECT id, nome, estoque FROM produtos
            WHERE ativo = 1 AND estoque <= ?
            ORDER BY estoque, nome
            LIMIT 10
            """,
            (ESTOQUE_BAIXO,)
        )
    ]

    resultado["produtos_por_categoria"] = [
        dict(linha) for linha in conexao.execute(
            """
            SELECT c.nome AS categoria, COUNT(p.id) AS quantidade
            FROM categorias c
            LEFT JOIN produtos p ON p.categoria_id = c.id
            GROUP BY c.id, c.nome
            ORDER BY c.id
            """
        )
    ]

    conexao.close()

    return jsonify(resultado)


# ============================================================================
# EXECUÇÃO LOCAL
# ============================================================================

if __name__ == "__main__":

    # debug só liga se você pedir (DEBUG=1): nunca hospede com debug ligado.
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("DEBUG") == "1"
    )
