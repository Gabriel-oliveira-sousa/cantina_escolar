# -*- coding: utf-8 -*-
"""
banco_dados.py

Cria e configura o banco SQLite da Cantina.

Tabelas:
    - categorias
    - produtos
    - usuarios
    - carrinho_itens
    - pedidos
    - pedido_itens

Pode ser executado diretamente (python banco_dados.py) ou importado pelo
app.py, que chama inicializar_banco() ao iniciar o servidor.

Base: estrutura do projeto Dragon Suplementos (Guilherme Teles da Silva e
Arthur Uezu da Cruz), adaptada para a cantina.
"""

import os
import sqlite3

from werkzeug.security import generate_password_hash


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

# O caminho é absoluto (relativo a este arquivo) para o banco não mudar de
# lugar dependendo da pasta de onde o servidor é iniciado.
PASTA_BASE = os.path.dirname(os.path.abspath(__file__))

NOME_BANCO = os.environ.get(
    "CANTINA_DB",
    os.path.join(PASTA_BASE, "cantina.db")
)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@cantina.com")
ADMIN_SENHA = os.environ.get("ADMIN_SENHA", "admin123")


# ============================================================================
# CONEXÃO
# ============================================================================

def obter_conexao():
    """Abre uma conexão SQLite com chaves estrangeiras ativas."""

    conexao = sqlite3.connect(NOME_BANCO, timeout=10)
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.row_factory = sqlite3.Row

    return conexao


# ============================================================================
# TABELAS
# ============================================================================

def criar_tabelas(conexao):

    conexao.executescript("""
        CREATE TABLE IF NOT EXISTS categorias (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS produtos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nome          TEXT NOT NULL,
            descricao     TEXT,
            imagem        TEXT,
            preco         REAL NOT NULL CHECK (preco >= 0),
            estoque       INTEGER NOT NULL DEFAULT 0 CHECK (estoque >= 0),
            ativo         INTEGER NOT NULL DEFAULT 1,
            categoria_id  INTEGER,
            data_cadastro TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),

            FOREIGN KEY (categoria_id)
                REFERENCES categorias (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nome          TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            telefone      TEXT,
            turma         TEXT,
            tipo          TEXT NOT NULL DEFAULT 'aluno'
                          CHECK (tipo IN ('aluno', 'professor',
                                          'funcionario', 'admin')),
            senha_hash    TEXT NOT NULL,
            data_cadastro TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS carrinho_itens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            produto_id INTEGER NOT NULL,
            quantidade INTEGER NOT NULL CHECK (quantidade > 0),

            FOREIGN KEY (usuario_id)
                REFERENCES usuarios (id) ON DELETE CASCADE,
            FOREIGN KEY (produto_id)
                REFERENCES produtos (id) ON DELETE CASCADE,
            UNIQUE (usuario_id, produto_id)
        );

        CREATE TABLE IF NOT EXISTS pedidos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id      INTEGER NOT NULL,
            senha           INTEGER NOT NULL,
            status          TEXT NOT NULL DEFAULT 'recebido'
                            CHECK (status IN ('recebido', 'preparando',
                                              'pronto', 'entregue',
                                              'cancelado')),
            forma_pagamento TEXT NOT NULL DEFAULT 'dinheiro'
                            CHECK (forma_pagamento IN ('dinheiro', 'pix',
                                                       'cartao')),
            observacao      TEXT,
            total           REAL NOT NULL CHECK (total >= 0),
            criado_em       TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            atualizado_em   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),

            FOREIGN KEY (usuario_id)
                REFERENCES usuarios (id) ON DELETE CASCADE
        );

        -- O nome e o preço do produto são copiados para o item do pedido.
        -- Assim, mudar o preço (ou excluir o produto) depois não altera
        -- o histórico de pedidos antigos.
        CREATE TABLE IF NOT EXISTS pedido_itens (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id     INTEGER NOT NULL,
            produto_id    INTEGER,
            nome          TEXT NOT NULL,
            preco_unit    REAL NOT NULL,
            quantidade    INTEGER NOT NULL CHECK (quantidade > 0),

            FOREIGN KEY (pedido_id)
                REFERENCES pedidos (id) ON DELETE CASCADE,
            FOREIGN KEY (produto_id)
                REFERENCES produtos (id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_pedidos_usuario ON pedidos (usuario_id);
        CREATE INDEX IF NOT EXISTS idx_pedidos_status  ON pedidos (status);
    """)

    conexao.commit()


# ============================================================================
# DADOS INICIAIS
# ============================================================================

CATEGORIAS_INICIAIS = [
    "Salgados",
    "Lanches",
    "Refeições",
    "Bebidas",
    "Doces",
]

# (nome, descrição, preço, estoque, categoria)
# Preços de exemplo: ajuste pelo painel de administração.
PRODUTOS_INICIAIS = [
    ("Coxinha", "Frango desfiado com catupiry, frita na hora.", 6.50, 40, "Salgados"),
    ("Pão de queijo", "Porção com 3 unidades, saindo do forno.", 4.00, 50, "Salgados"),
    ("Esfiha de carne", "Massa macia com recheio de carne temperada.", 6.00, 30, "Salgados"),
    ("Enroladinho de salsicha", "Massa assada com salsicha inteira.", 5.50, 30, "Salgados"),
    ("Pastel de queijo", "Pastel grande, massa fina e crocante.", 7.00, 25, "Salgados"),

    ("Misto quente", "Pão de forma, queijo e presunto na chapa.", 6.50, 30, "Lanches"),
    ("Hambúrguer", "Pão, hambúrguer, queijo, alface e tomate.", 12.00, 20, "Lanches"),
    ("Sanduíche natural", "Frango, cenoura ralada, alface e maionese.", 8.00, 20, "Lanches"),
    ("Pão na chapa", "Pão francês com manteiga.", 4.50, 30, "Lanches"),

    ("Prato do dia", "Arroz, feijão, proteína do dia e salada.", 16.00, 25, "Refeições"),
    ("Macarrão ao molho", "Macarrão com molho de tomate e queijo ralado.", 14.00, 15, "Refeições"),

    ("Suco natural", "Laranja, 300 ml, sem adição de açúcar.", 6.00, 30, "Bebidas"),
    ("Refrigerante lata", "Lata 350 ml, sabores variados.", 5.50, 40, "Bebidas"),
    ("Água mineral", "Garrafa 500 ml, sem gás.", 3.00, 60, "Bebidas"),
    ("Achocolatado", "Caixinha 200 ml.", 4.50, 30, "Bebidas"),

    ("Brigadeiro", "Unidade, chocolate granulado.", 3.00, 40, "Doces"),
    ("Brownie", "Brownie de chocolate com nozes.", 6.00, 20, "Doces"),
    ("Bolo de pote", "Camadas de bolo de cenoura e brigadeiro.", 8.00, 15, "Doces"),
    ("Barra de cereal", "Barra de aveia com mel.", 3.50, 35, "Doces"),
]


def inserir_dados_iniciais(conexao):
    """Insere categorias, produtos de exemplo e o administrador (uma vez)."""

    conexao.executemany(
        "INSERT OR IGNORE INTO categorias (nome) VALUES (?)",
        [(nome,) for nome in CATEGORIAS_INICIAIS]
    )

    # Produtos de exemplo só entram se a tabela estiver vazia, para não
    # recriar produtos que o administrador apagou de propósito.
    total_produtos = conexao.execute(
        "SELECT COUNT(*) FROM produtos"
    ).fetchone()[0]

    if total_produtos == 0:

        ids_categorias = {
            linha["nome"]: linha["id"]
            for linha in conexao.execute("SELECT id, nome FROM categorias")
        }

        conexao.executemany(
            """
            INSERT INTO produtos
                (nome, descricao, preco, estoque, categoria_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (nome, descricao, preco, estoque, ids_categorias[categoria])
                for nome, descricao, preco, estoque, categoria
                in PRODUTOS_INICIAIS
            ]
        )

    admin_existe = conexao.execute(
        "SELECT id FROM usuarios WHERE tipo = 'admin' LIMIT 1"
    ).fetchone()

    if admin_existe is None:

        conexao.execute(
            """
            INSERT INTO usuarios (nome, email, tipo, senha_hash)
            VALUES (?, ?, 'admin', ?)
            """,
            ("Administrador", ADMIN_EMAIL, generate_password_hash(ADMIN_SENHA))
        )

        print(
            f"Administrador criado: {ADMIN_EMAIL} "
            "(troque a senha padrão antes de hospedar!)"
        )

    conexao.commit()


# ============================================================================
# INICIALIZAÇÃO
# ============================================================================

def inicializar_banco():

    conexao = obter_conexao()

    criar_tabelas(conexao)
    inserir_dados_iniciais(conexao)

    conexao.close()


if __name__ == "__main__":

    inicializar_banco()

    print(f"Banco pronto em: {NOME_BANCO}")
