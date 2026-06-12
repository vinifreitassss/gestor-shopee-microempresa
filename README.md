# Gestor Shopee Microempresa

App desktop local, em Python, para importar planilhas da Shopee, cadastrar custos, despesas, insumos/estoque e montar um mini DRE mensal da microempresa.

## Objetivo

O app foi pensado para uma gestão pragmática:

- importar planilhas diárias, mensais ou personalizadas da Shopee;
- usar variações vendidas para cálculo financeiro;
- usar produto pai para agrupamento, gráficos e visão comercial;
- calcular lucro com imposto, comissão Shopee, taxa fixa por unidade e custo do produto;
- mostrar alerta de custo pendente somente para variações que venderam no período;
- cadastrar despesas e despesas recorrentes;
- cadastrar insumos com custo mínimo por pedido;
- acompanhar valor aproximado investido em estoque de insumos;
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

## Atualizando uma instalação existente

Se você já baixou antes via Git, rode dentro da pasta do projeto:

```bash
git pull
py main.py
```

Se baixou por ZIP, baixe o ZIP novamente e substitua a pasta antiga do app.

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

## Correção da variação

O importador diferencia explicitamente:

```text
ID da Variação = identificador interno da Shopee.
Nome da Variação = texto que aparece para você, usado no cadastro e no custo.
```

Se você já importou um período antes dessa correção, basta importar o mesmo período novamente e escolher **Substituir anterior**. O app atualiza o nome da variação existente.

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

## Insumos / Estoque

A aba **Insumos / Estoque** usa uma lógica simples e pragmática:

```text
Custo por unidade de uso = custo da compra / quantidade total na unidade de uso
Custo mínimo por pedido = custo por unidade de uso x mínimo usado por pedido
Valor em estoque = custo por unidade de uso x estoque atual
```

Exemplo:

```text
Fita amarela
Custo do rolo: R$ 8,27
Quantidade total na unidade de uso: 5000 cm
Mínimo usado por pedido: 90 cm

Custo mínimo por pedido = R$ 0,14886
```

Nesta primeira versão, o insumo ainda não está vinculado automaticamente às variações fabricadas. Essa será a próxima evolução da ficha técnica.

## Situação atual

Esta é a primeira estrutura do MVP. Ela já possui:

- estrutura do banco;
- telas principais;
- leitura inicial da planilha;
- prévia das variações vendidas;
- correção para usar nome da variação em vez do ID;
- cadastro simples de custos;
- cadastro de insumos/estoque;
- cálculo do custo mínimo do insumo por pedido;
- cadastro de despesas;
- DRE mensal;
- dashboard básico.

Próximos passos naturais:

1. vincular insumos às variações fabricadas por ficha técnica;
2. recalcular custo de produto fabricado automaticamente;
3. implementar comparação entre diárias e consolidação mensal;
4. adicionar gráficos de pizza por produto pai;
5. criar botão de impressão/exportação do DRE.
