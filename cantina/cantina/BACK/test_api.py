# -*- coding: utf-8 -*-
"""
test_api.py

Testes automáticos da API da Cantina.

Não precisa iniciar o servidor: os testes usam o cliente de testes do Flask
e um banco temporário (o banco real não é tocado).

Como executar (dentro da pasta BACK):

    python -m unittest test_api -v
"""

import os
import tempfile
import unittest

# O banco temporário precisa ser definido ANTES de importar o app.
_pasta_temp = tempfile.mkdtemp()
os.environ["CANTINA_DB"] = os.path.join(_pasta_temp, "teste.db")
os.environ["UPLOAD_FOLDER"] = os.path.join(_pasta_temp, "uploads")

from app import app  # noqa: E402


class TesteBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.c = app.test_client()

    def login(self, email, senha):
        r = self.c.post("/api/login", json={"email": email, "senha": senha})
        self.assertEqual(r.status_code, 200, r.get_json())
        return {"Authorization": "Bearer " + r.get_json()["token"]}

    def admin(self):
        return self.login("admin@cantina.com", "admin123")

    def novo_aluno(self, nome="Aluno Teste"):
        email = f"{os.urandom(4).hex()}@teste.com"
        r = self.c.post("/api/usuarios", json={
            "nome": nome, "email": email, "senha": "123456",
            "tipo": "aluno", "turma": "2º DSN"
        })
        self.assertEqual(r.status_code, 201, r.get_json())
        return {"Authorization": "Bearer " + r.get_json()["token"]}

    def produto(self, **extra):
        dados = {"nome": "Produto " + os.urandom(3).hex(),
                 "preco": 5, "estoque": 10, "categoria": "Salgados"}
        dados.update(extra)
        r = self.c.post("/api/produtos", json=dados, headers=self.admin())
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def estoque(self, produto_id):
        return self.c.get(f"/api/produtos/{produto_id}").get_json()["estoque"]


class TesteGeral(TesteBase):

    def test_rota_inicial(self):
        r = self.c.get("/")
        self.assertEqual(r.get_json()["status"], "online")

    def test_categorias_iniciais(self):
        nomes = [c["nome"] for c in self.c.get("/api/categorias").get_json()]
        self.assertIn("Salgados", nomes)
        self.assertIn("Bebidas", nomes)

    def test_produtos_de_exemplo(self):
        produtos = self.c.get("/api/produtos").get_json()
        self.assertGreater(len(produtos), 10)


class TesteUsuarios(TesteBase):

    def test_cadastro_e_login(self):
        r = self.c.post("/api/usuarios", json={
            "nome": "Maria", "email": "maria@teste.com", "senha": "abcdef"})
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("senha_hash", r.get_json()["usuario"])

        self.login("maria@teste.com", "abcdef")

    def test_email_duplicado(self):
        dados = {"nome": "X", "email": "dup@teste.com", "senha": "123456"}
        self.c.post("/api/usuarios", json=dados)
        r = self.c.post("/api/usuarios", json=dados)
        self.assertEqual(r.status_code, 409)

    def test_senha_curta_e_email_invalido(self):
        r = self.c.post("/api/usuarios", json={
            "nome": "X", "email": "x@teste.com", "senha": "123"})
        self.assertEqual(r.status_code, 400)

        r = self.c.post("/api/usuarios", json={
            "nome": "X", "email": "sem-arroba", "senha": "123456"})
        self.assertEqual(r.status_code, 400)

    def test_nao_deixa_virar_admin_pelo_cadastro(self):
        r = self.c.post("/api/usuarios", json={
            "nome": "Esperto", "email": "esperto@teste.com",
            "senha": "123456", "tipo": "admin"})
        self.assertEqual(r.status_code, 400)

    def test_login_errado(self):
        r = self.c.post("/api/login", json={
            "email": "admin@cantina.com", "senha": "errada"})
        self.assertEqual(r.status_code, 401)

    def test_token_invalido(self):
        r = self.c.get("/api/me", headers={"Authorization": "Bearer lixo"})
        self.assertEqual(r.status_code, 401)


class TesteProdutos(TesteBase):

    def test_aluno_nao_cria_produto(self):
        r = self.c.post("/api/produtos", headers=self.novo_aluno(), json={
            "nome": "Hack", "preco": 1, "estoque": 1})
        self.assertEqual(r.status_code, 403)

    def test_sem_login_nao_cria_produto(self):
        r = self.c.post("/api/produtos", json={"nome": "Hack", "preco": 1})
        self.assertEqual(r.status_code, 401)

    def test_validacoes(self):
        h = self.admin()
        for corpo in (
            {"nome": "", "preco": 1},
            {"nome": "A", "preco": -1},
            {"nome": "A", "preco": "abc"},
            {"nome": "A", "preco": 1, "estoque": -3},
            {"nome": "A", "preco": 1, "categoria": "Inexistente"},
        ):
            r = self.c.post("/api/produtos", json=corpo, headers=h)
            self.assertEqual(r.status_code, 400, corpo)

    def test_editar_inclui_estoque(self):
        p = self.produto()
        r = self.c.put(f"/api/produtos/{p['id']}", headers=self.admin(),
                       json={"estoque": 99, "preco": 7.5})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["estoque"], 99)
        self.assertEqual(r.get_json()["preco"], 7.5)

    def test_produto_inativo_some_da_lista_publica(self):
        p = self.produto()
        self.c.put(f"/api/produtos/{p['id']}", headers=self.admin(),
                   json={"ativo": False})
        ids = [x["id"] for x in self.c.get("/api/produtos").get_json()]
        self.assertNotIn(p["id"], ids)

        todos = self.c.get("/api/produtos?todos=1", headers=self.admin())
        self.assertIn(p["id"], [x["id"] for x in todos.get_json()])

    def test_excluir(self):
        p = self.produto()
        r = self.c.delete(f"/api/produtos/{p['id']}", headers=self.admin())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get(f"/api/produtos/{p['id']}").status_code, 404)

    def test_busca(self):
        self.produto(nome="Tapioca recheada")
        achados = self.c.get("/api/produtos?busca=tapioca").get_json()
        self.assertEqual(len(achados), 1)


class TesteCarrinhoEPedidos(TesteBase):

    def test_carrinho_exige_login(self):
        self.assertEqual(self.c.get("/api/carrinho").status_code, 401)

    def test_nao_coloca_mais_que_o_estoque(self):
        p = self.produto(estoque=3)
        h = self.novo_aluno()
        r = self.c.post("/api/carrinho", headers=h,
                        json={"produto_id": p["id"], "quantidade": 4})
        self.assertEqual(r.status_code, 409)

    def test_somar_itens_no_carrinho(self):
        p = self.produto(estoque=10, preco=4)
        h = self.novo_aluno()
        self.c.post("/api/carrinho", headers=h,
                    json={"produto_id": p["id"], "quantidade": 2})
        r = self.c.post("/api/carrinho", headers=h,
                        json={"produto_id": p["id"], "quantidade": 1})
        carrinho = r.get_json()
        self.assertEqual(carrinho["itens"][0]["quantidade"], 3)
        self.assertEqual(carrinho["total"], 12)

    def test_fluxo_completo_do_pedido(self):
        p = self.produto(estoque=10, preco=6.5)
        aluno = self.novo_aluno()
        adm = self.admin()

        self.c.post("/api/carrinho", headers=aluno,
                    json={"produto_id": p["id"], "quantidade": 2})

        r = self.c.post("/api/pedidos", headers=aluno,
                        json={"forma_pagamento": "pix", "observacao": "sem gelo"})
        self.assertEqual(r.status_code, 201, r.get_json())
        pedido = r.get_json()

        self.assertEqual(pedido["total"], 13)
        self.assertEqual(pedido["status"], "recebido")
        self.assertEqual(pedido["itens"][0]["quantidade"], 2)
        self.assertEqual(self.estoque(p["id"]), 8)

        # carrinho foi esvaziado
        self.assertEqual(self.c.get("/api/carrinho", headers=aluno)
                         .get_json()["itens"], [])

        # painel público mostra a senha sem dados pessoais
        painel = self.c.get("/api/painel-senhas").get_json()
        self.assertIn(pedido["senha"], painel["preparando"])

        # admin avança o status
        for novo in ("preparando", "pronto", "entregue"):
            r = self.c.put(f"/api/pedidos/{pedido['id']}/status",
                           headers=adm, json={"status": novo})
            self.assertEqual(r.status_code, 200, r.get_json())
            self.assertEqual(r.get_json()["status"], novo)

        # depois de entregue não volta
        r = self.c.put(f"/api/pedidos/{pedido['id']}/status",
                       headers=adm, json={"status": "preparando"})
        self.assertEqual(r.status_code, 409)

    def test_carrinho_vazio_nao_gera_pedido(self):
        r = self.c.post("/api/pedidos", headers=self.novo_aluno(), json={})
        self.assertEqual(r.status_code, 400)

    def test_cancelar_devolve_estoque(self):
        p = self.produto(estoque=5)
        aluno = self.novo_aluno()
        self.c.post("/api/carrinho", headers=aluno,
                    json={"produto_id": p["id"], "quantidade": 3})
        pedido = self.c.post("/api/pedidos", headers=aluno, json={}).get_json()
        self.assertEqual(self.estoque(p["id"]), 2)

        r = self.c.post(f"/api/pedidos/{pedido['id']}/cancelar", headers=aluno)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.estoque(p["id"]), 5)

    def test_cliente_nao_cancela_pedido_em_preparo(self):
        p = self.produto()
        aluno = self.novo_aluno()
        self.c.post("/api/carrinho", headers=aluno,
                    json={"produto_id": p["id"], "quantidade": 1})
        pedido = self.c.post("/api/pedidos", headers=aluno, json={}).get_json()
        self.c.put(f"/api/pedidos/{pedido['id']}/status",
                   headers=self.admin(), json={"status": "preparando"})

        r = self.c.post(f"/api/pedidos/{pedido['id']}/cancelar", headers=aluno)
        self.assertEqual(r.status_code, 409)

    def test_usuario_nao_ve_pedido_de_outro(self):
        p = self.produto()
        dono = self.novo_aluno()
        outro = self.novo_aluno()
        self.c.post("/api/carrinho", headers=dono,
                    json={"produto_id": p["id"], "quantidade": 1})
        pedido = self.c.post("/api/pedidos", headers=dono, json={}).get_json()

        r = self.c.get(f"/api/pedidos/{pedido['id']}", headers=outro)
        self.assertEqual(r.status_code, 404)

        ids = [x["id"] for x in
               self.c.get("/api/pedidos", headers=outro).get_json()]
        self.assertNotIn(pedido["id"], ids)

    def test_aluno_nao_muda_status(self):
        p = self.produto()
        aluno = self.novo_aluno()
        self.c.post("/api/carrinho", headers=aluno,
                    json={"produto_id": p["id"], "quantidade": 1})
        pedido = self.c.post("/api/pedidos", headers=aluno, json={}).get_json()
        r = self.c.put(f"/api/pedidos/{pedido['id']}/status",
                       headers=aluno, json={"status": "pronto"})
        self.assertEqual(r.status_code, 403)

    def test_estoque_acabou_antes_de_finalizar(self):
        p = self.produto(estoque=2)
        a, b = self.novo_aluno(), self.novo_aluno()
        self.c.post("/api/carrinho", headers=a,
                    json={"produto_id": p["id"], "quantidade": 2})
        self.c.post("/api/carrinho", headers=b,
                    json={"produto_id": p["id"], "quantidade": 2})

        self.assertEqual(self.c.post("/api/pedidos", headers=a, json={})
                         .status_code, 201)
        r = self.c.post("/api/pedidos", headers=b, json={})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.estoque(p["id"]), 0)

    def test_senhas_sequenciais(self):
        p = self.produto(estoque=10)
        senhas = []
        for _ in range(2):
            h = self.novo_aluno()
            self.c.post("/api/carrinho", headers=h,
                        json={"produto_id": p["id"], "quantidade": 1})
            senhas.append(self.c.post("/api/pedidos", headers=h, json={})
                          .get_json()["senha"])
        self.assertEqual(senhas[1], senhas[0] + 1)

    def test_preco_antigo_fica_no_historico(self):
        p = self.produto(preco=5)
        aluno = self.novo_aluno()
        self.c.post("/api/carrinho", headers=aluno,
                    json={"produto_id": p["id"], "quantidade": 1})
        pedido = self.c.post("/api/pedidos", headers=aluno, json={}).get_json()

        self.c.put(f"/api/produtos/{p['id']}", headers=self.admin(),
                   json={"preco": 50})

        r = self.c.get(f"/api/pedidos/{pedido['id']}", headers=aluno)
        self.assertEqual(r.get_json()["itens"][0]["preco_unit"], 5)
        self.assertEqual(r.get_json()["total"], 5)


class TesteDashboard(TesteBase):

    def test_so_admin(self):
        self.assertEqual(self.c.get("/api/dashboard").status_code, 401)
        r = self.c.get("/api/dashboard", headers=self.novo_aluno())
        self.assertEqual(r.status_code, 403)

    def test_estrutura(self):
        r = self.c.get("/api/dashboard", headers=self.admin())
        self.assertEqual(r.status_code, 200)
        dados = r.get_json()
        for chave in ("total_produtos", "pedidos_hoje", "faturamento_hoje",
                      "mais_vendidos", "estoque_baixo", "pedidos_por_status"):
            self.assertIn(chave, dados)


if __name__ == "__main__":
    unittest.main(verbosity=2)
