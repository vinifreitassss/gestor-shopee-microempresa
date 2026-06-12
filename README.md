# Gestor Shopee Microempresa

App desktop local, em Python, para importar planilhas da Shopee, cadastrar custos, despesas e montar um mini DRE mensal da microempresa.

## Objetivo

O app foi pensado para uma gestão pragmática:

- importar planilhas diárias, mensais ou personalizadas da Shopee;
- usar variações vendidas para cálculo financeiro;
- usar produto pai para agrupamento, gráficos e visão comercial;
- calcular lucro com imposto, comissão Shopee, taxa fixa por unidade e custo do produto;
- mostrar alerta de custo pendente somente para variações que venderam no período;
- cadastrar despesas e despesas recorrentes;
- montar DRE mensal com faturamento, impostos, comissão, taxa, custos, despesas e lucro final;
- salvar tudo localmente no PC com SQLite.

## Stack

- Python
- CustomTkinter
- SQLite
- Pandas
- OpenPyXL
- Matplotlib

## Como rodar

### 1. Baixe o projeto

Pelo GitHub:

```bash
git clone https://github.com/vinifreitassss/gestor-shopee-microempresa.git
cd gestor-shopee-microempresa
```

Ou baixe em `Code > Download ZIP`.

### 2. Crie um ambiente virtual

No Windows:

```bash
py -m venv .venv
.venv\Scripts\activate
```

No Linux/Mac:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Rode o app

```bash
py main.py
```

Ou:

```bash
python main.py
```

## Banco de dados

O banco SQLite fica salvo automaticamente em:

```text
~/.gestor_shopee_microempresa/gestor.db
```

No Windows, isso costuma ficar em algo como:

```text
C:\Users\SEU_USUARIO\.gestor_shopee_microempresa\gestor.db
```

## Regra de lucro

A regra padrão inicial é:

```text
Lucro = faturamento
      - 9% de imposto
      - 22% de comissão Shopee
      - R$ 5,00 por unidade vendida
      - custo do produto vendido
```

Esses percentuais e a taxa são editáveis na aba **Configurações**.

## Produto pai x variação

Regra do sistema:

```text
Produto pai = agrupamento, gráfico e visão comercial.
Variação = cálculo real de venda, custo, taxa e lucro.
```

Se uma linha da planilha for produto pai, ela não entra no cálculo financeiro para evitar duplicidade.

## Planilha Shopee

O importador procura automaticamente a aba com nome parecido com:

```text
Produtos com Melhor Desempenho
```

Colunas usadas:

- Produto;
- ID do item;
- Nome da variação;
- ID da variação;
- SKU da variação;
- Vendas/Pedido pago;
- Unidades/Pedido pago.

O app tenta reconhecer nomes parecidos de coluna para tolerar variações no relatório.

## Situação atual

Esta é a primeira estrutura do MVP. Ela já possui:

- estrutura do banco;
- telas principais;
- leitura inicial da planilha;
- prévia das variações vendidas;
- cadastro simples de custos;
- cadastro de despesas;
- DRE mensal;
- dashboard básico.

Próximos passos naturais:

1. melhorar validação visual da importação;
2. implementar comparação entre diárias e consolidação mensal;
3. adicionar gráficos de pizza por produto pai;
4. criar módulo de insumos/estoque e ficha técnica de produto fabricado;
5. criar botão de impressão/exportação do DRE.
