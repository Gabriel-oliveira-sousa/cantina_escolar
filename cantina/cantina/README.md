# Cantina

Sistema de pedidos para a cantina da escola. O cliente escolhe os itens pelo site, envia o pedido, recebe uma **senha** e acompanha o andamento. O atendente gerencia pedidos e produtos pelo site ou por uma tela de computador feita em Python (Tkinter).

**Integrantes:** Arthur, Davi e Gabriel.

**Estrutura base:** projeto *Dragon Suplementos*, de Guilherme Teles da Silva e Arthur Uezu da Cruz (com auxílio de Gustavo Moraes e Mateus Valente). A divisão front/back, o uso de Flask + SQLite + Fetch API e a ideia de categorias, produtos, carrinho e dashboard vêm dele. O código da cantina foi reescrito e ampliado a partir dessa base.

## Partes do sistema

| Pasta | O que é | Tecnologia |
|---|---|---|
| `BACK/` | API REST e banco de dados | Python, Flask, SQLite |
| `FRONT/` | Site do cliente e painel de administração | HTML, CSS, JavaScript (Fetch API) |
| `DESKTOP/` | Tela do caixa/administrador | Python, Tkinter |

As três partes conversam pela **mesma API**. Quando o atendente marca um pedido como "pronto" no Tkinter, a senha aparece no painel de senhas do site.

```
Site (navegador)  ──┐
                    ├──►  API Flask  ──►  SQLite
Tkinter (desktop) ──┘
```

## O que o sistema faz

**Cliente (site)**
- Cadastro e login (senha guardada com hash; login por token)
- Cardápio por categoria, com busca e aviso de estoque baixo ou esgotado
- Carrinho com ajuste de quantidade
- Envio do pedido com forma de pagamento (dinheiro, Pix ou cartão, pagos na retirada) e observação
- Senha de retirada, numerada por dia
- "Meus pedidos" com andamento (recebido, preparando, pronto, entregue), atualização automática e cancelamento enquanto o pedido ainda está "recebido"
- Painel público de senhas na página inicial (só números, sem dados pessoais)

**Administrador (site e Tkinter)**
- Fila de pedidos: iniciar preparo, marcar como pronto, marcar como entregue, cancelar
- Cadastro, edição, ocultação e exclusão de produtos; controle de estoque
- Resumo: pedidos e faturamento do dia, mais vendidos, estoque baixo
- No site, também envio de foto do produto

**Regras que o back-end garante**
- Pedido baixa o estoque; cancelar devolve ao estoque
- Dois clientes não conseguem comprar a mesma última unidade (transação com trava)
- Preço e nome ficam gravados no pedido: mudar o preço depois não altera pedidos antigos
- Cada cliente só vê os próprios pedidos; só o administrador altera produtos e status
- Ninguém vira administrador pelo cadastro público

## Como rodar no seu computador

Precisa de Python 3.10 ou mais novo.

**1. Back-end**

```bash
cd BACK
pip install -r requirements.txt
python app.py
```

A API sobe em `http://127.0.0.1:5000`. Na primeira vez, o banco `cantina.db` é criado com categorias, 19 produtos de exemplo (preços fictícios) e o administrador:

- e-mail: `admin@cantina.com`
- senha: `admin123` (**troque antes de hospedar**, veja abaixo)

**2. Front-end**

Em outro terminal:

```bash
cd FRONT
python -m http.server 8080
```

Abra `http://localhost:8080`. O endereço da API está em `FRONT/js/config.js`.

**3. Tela Tkinter**

Em outro terminal, com o back-end ligado:

```bash
cd DESKTOP
python cantina_desktop.py
```

Entre com o login do administrador. No Linux, se faltar o Tkinter: `sudo apt install python3-tk`.

**4. Testes do back-end**

```bash
cd BACK
python -m unittest test_api -v
```

São 30 testes (cadastro, permissões, validações, carrinho, fluxo completo do pedido, estoque, cancelamento, dashboard). Usam um banco temporário.

## Hospedagem

**Back-end (Render)**
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app`
- Variáveis de ambiente: `SECRET_KEY` (um texto longo e aleatório), `ADMIN_SENHA` (a senha do administrador, usada na criação do banco) e, se quiser, `ADMIN_EMAIL`

**Front-end (Netlify)**
- Publique a pasta `FRONT`.
- Antes, edite `FRONT/js/config.js` e coloque o endereço do back-end hospedado.

**Tkinter**
- No campo "Endereço da API" da tela de login, coloque o endereço do back-end hospedado.

## Limitações conhecidas

- **Dados no Render grátis:** o disco do plano gratuito é temporário. O SQLite e as fotos enviadas podem ser apagados quando o serviço reinicia ou é publicado de novo. Para uso real, é preciso disco persistente ou outro banco (por exemplo PostgreSQL).
- **Sem pagamento online:** o cliente paga no balcão. O sistema só registra a forma escolhida.
- **Sem recuperação de senha** e sem confirmação de e-mail.
- **Atualização por consulta periódica** (a cada 8 a 10 segundos), não em tempo real.
- **Foto do produto** só pelo site; o Tkinter edita os demais campos.
- O token de login fica no navegador (`localStorage`) e vale por 12 horas.
- Os preços e produtos de exemplo são fictícios.

## Como o código está organizado

```
BACK/
  banco_dados.py   tabelas e dados iniciais
  app.py           rotas da API, login por token, regras dos pedidos
  test_api.py      testes automáticos
FRONT/
  *.html           uma página por tela
  css/style.css    estilos
  js/api.js        código compartilhado (API, sessão, cabeçalho, avisos)
  js/<pagina>.js   lógica de cada página
DESKTOP/
  cantina_desktop.py   tela Tkinter (cliente da API, login, 3 abas)
```
