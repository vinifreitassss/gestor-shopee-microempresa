from src.database import fetch_all, fetch_one, get_connection, now_iso


def get_dashboard_summary(mes_referencia: str) -> dict:
    dre = get_dre(mes_referencia)
    pendencias = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM vendas_contabilizadas
        WHERE mes_referencia = ? AND lucro_incompleto = 1
        """,
        (mes_referencia,),
    )
    return {**dre, "custos_pendentes": pendencias["total"] if pendencias else 0}


def get_dre(mes_referencia: str) -> dict:
    vendas = fetch_one(
        """
        SELECT
            COALESCE(SUM(faturamento), 0) AS faturamento_bruto,
            COALESCE(SUM(imposto_valor), 0) AS impostos,
            COALESCE(SUM(comissao_valor), 0) AS comissao,
            COALESCE(SUM(taxa_fixa_valor), 0) AS taxa_fixa,
            COALESCE(SUM(COALESCE(custo_total, 0)), 0) AS custo_produtos,
            COALESCE(SUM(COALESCE(lucro, 0)), 0) AS lucro_bruto,
            COALESCE(SUM(unidades), 0) AS unidades,
            COALESCE(SUM(lucro_incompleto), 0) AS itens_incompletos
        FROM vendas_contabilizadas
        WHERE mes_referencia = ?
        """,
        (mes_referencia,),
    ) or {}

    despesas = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS despesas
        FROM despesas
        WHERE mes_referencia = ?
          AND COALESCE(incide_dre, 1) = 1
        """,
        (mes_referencia,),
    ) or {"despesas": 0}

    faturamento = float(vendas.get("faturamento_bruto", 0) or 0)
    lucro_bruto = float(vendas.get("lucro_bruto", 0) or 0)
    total_despesas = float(despesas.get("despesas", 0) or 0)
    lucro_final = lucro_bruto - total_despesas
    margem = (lucro_final / faturamento * 100) if faturamento else 0

    return {
        "mes_referencia": mes_referencia,
        "faturamento_bruto": faturamento,
        "impostos": float(vendas.get("impostos", 0) or 0),
        "comissao": float(vendas.get("comissao", 0) or 0),
        "taxa_fixa": float(vendas.get("taxa_fixa", 0) or 0),
        "custo_produtos": float(vendas.get("custo_produtos", 0) or 0),
        "lucro_bruto": lucro_bruto,
        "despesas": total_despesas,
        "lucro_final": lucro_final,
        "margem_liquida": margem,
        "unidades": int(vendas.get("unidades", 0) or 0),
        "itens_incompletos": int(vendas.get("itens_incompletos", 0) or 0),
    }


def get_product_ranking(mes_referencia: str) -> list[dict]:
    rows = fetch_all(
        """
        SELECT
            pp.nome AS produto_pai,
            COALESCE(SUM(v.faturamento), 0) AS faturamento,
            COALESCE(SUM(v.unidades), 0) AS unidades,
            COALESCE(SUM(COALESCE(v.custo_total, 0)), 0) AS custo_total,
            COALESCE(SUM(COALESCE(v.lucro, 0)), 0) AS lucro,
            COALESCE(SUM(v.lucro_incompleto), 0) AS pendencias
        FROM vendas_contabilizadas v
        JOIN produtos_pai pp ON pp.id = v.produto_pai_id
        WHERE v.mes_referencia = ?
        GROUP BY pp.id, pp.nome
        ORDER BY faturamento DESC
        LIMIT 100
        """,
        (mes_referencia,),
    )
    for row in rows:
        faturamento = float(row.get("faturamento") or 0)
        lucro = float(row.get("lucro") or 0)
        custo = float(row.get("custo_total") or 0)
        unidades = float(row.get("unidades") or 0)
        row["margem"] = (lucro / faturamento * 100) if faturamento else 0
        row["custo_sobre_faturamento"] = (custo / faturamento * 100) if faturamento else 0
        row["ticket_medio"] = (faturamento / unidades) if unidades else 0
        row["lucro_por_unidade"] = (lucro / unidades) if unidades else 0
    return rows


def get_expenses_by_category(mes_referencia: str) -> list[dict]:
    return fetch_all(
        """
        SELECT
            categoria,
            COALESCE(SUM(valor), 0) AS valor
        FROM despesas
        WHERE mes_referencia = ?
          AND COALESCE(incide_dre, 1) = 1
        GROUP BY categoria
        ORDER BY valor DESC
        """,
        (mes_referencia,),
    )


def get_cash_only_expenses_by_category(mes_referencia: str) -> list[dict]:
    return fetch_all(
        """
        SELECT
            categoria,
            COALESCE(SUM(valor), 0) AS valor
        FROM despesas
        WHERE mes_referencia = ?
          AND COALESCE(incide_dre, 1) = 0
        GROUP BY categoria
        ORDER BY valor DESC
        """,
        (mes_referencia,),
    )


def get_product_abc_curve(mes_referencia: str, metric: str = "lucro") -> list[dict]:
    allowed = {"lucro", "faturamento", "unidades"}
    metric = metric if metric in allowed else "lucro"
    rows = get_product_ranking(mes_referencia)
    rows = sorted(rows, key=lambda row: float(row.get(metric) or 0), reverse=True)
    positive_total = sum(max(float(row.get(metric) or 0), 0) for row in rows)

    cumulative = 0.0
    result = []
    for row in rows:
        value = float(row.get(metric) or 0)
        positive_value = max(value, 0)
        share = (positive_value / positive_total * 100) if positive_total else 0
        cumulative += share
        if value <= 0:
            abc_class = "Sem lucro" if metric == "lucro" else "C"
        elif cumulative <= 80:
            abc_class = "A"
        elif cumulative <= 95:
            abc_class = "B"
        else:
            abc_class = "C"
        result.append(
            {
                **row,
                "abc_valor": value,
                "abc_percentual": share,
                "abc_acumulado": min(cumulative, 100),
                "abc_classe": abc_class,
            }
        )
    return result


def get_operational_insights(mes_referencia: str) -> dict:
    dre = get_dre(mes_referencia)
    products = get_product_ranking(mes_referencia)
    expenses = get_expenses_by_category(mes_referencia)
    abc = get_product_abc_curve(mes_referencia, "lucro")

    def _max_by(key: str):
        return max(products, key=lambda row: float(row.get(key) or 0), default=None)

    def _min_by(key: str):
        return min(products, key=lambda row: float(row.get(key) or 0), default=None)

    products_with_revenue = [row for row in products if float(row.get("faturamento") or 0) > 0]
    products_with_positive_revenue = products_with_revenue or products
    loss_products = [row for row in products if float(row.get("lucro") or 0) < 0]
    low_margin_products = [row for row in products_with_revenue if float(row.get("margem") or 0) < 10]

    faturamento = float(dre.get("faturamento_bruto") or 0)
    despesas = float(dre.get("despesas") or 0)
    taxas_marketplace = float(dre.get("comissao") or 0) + float(dre.get("taxa_fixa") or 0)

    top_expense = max(expenses, key=lambda row: float(row.get("valor") or 0), default=None)
    abc_a = [row for row in abc if row["abc_classe"] == "A"]

    return {
        "produto_mais_lucrativo": _max_by("lucro"),
        "produto_menos_lucrativo": _min_by("lucro"),
        "maior_faturamento": _max_by("faturamento"),
        "produto_melhor_margem": max(products_with_positive_revenue, key=lambda row: float(row.get("margem") or 0), default=None),
        "produto_pior_margem": min(products_with_positive_revenue, key=lambda row: float(row.get("margem") or 0), default=None),
        "maior_custo_total": _max_by("custo_total"),
        "maior_custo_percentual": max(products_with_positive_revenue, key=lambda row: float(row.get("custo_sobre_faturamento") or 0), default=None),
        "mais_vendido_unidades": _max_by("unidades"),
        "melhor_lucro_por_unidade": _max_by("lucro_por_unidade"),
        "maior_despesa_categoria": top_expense,
        "despesas_sobre_faturamento": (despesas / faturamento * 100) if faturamento else 0,
        "taxas_sobre_faturamento": (taxas_marketplace / faturamento * 100) if faturamento else 0,
        "produtos_com_prejuizo": len(loss_products),
        "produtos_margem_baixa": len(low_margin_products),
        "produtos_abc_a": abc_a,
    }


def get_pending_costs(mes_referencia: str) -> list[dict]:
    return fetch_all(
        """
        SELECT
            pp.nome AS produto_pai,
            var.nome_variacao,
            var.sku,
            SUM(v.unidades) AS unidades,
            SUM(v.faturamento) AS faturamento
        FROM vendas_contabilizadas v
        JOIN produtos_pai pp ON pp.id = v.produto_pai_id
        JOIN variacoes var ON var.id = v.variacao_id
        WHERE v.mes_referencia = ? AND v.lucro_incompleto = 1
        GROUP BY pp.nome, var.nome_variacao, var.sku
        ORDER BY faturamento DESC
        """,
        (mes_referencia,),
    )


def close_month(mes_referencia: str) -> None:
    dre = get_dre(mes_referencia)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO fechamentos_mensais (
                mes_referencia, faturamento_bruto, impostos, comissao, taxa_fixa,
                custo_produtos, lucro_bruto, despesas, lucro_final, margem_liquida,
                status, fechado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'fechado', ?)
            ON CONFLICT(mes_referencia) DO UPDATE SET
                faturamento_bruto = excluded.faturamento_bruto,
                impostos = excluded.impostos,
                comissao = excluded.comissao,
                taxa_fixa = excluded.taxa_fixa,
                custo_produtos = excluded.custo_produtos,
                lucro_bruto = excluded.lucro_bruto,
                despesas = excluded.despesas,
                lucro_final = excluded.lucro_final,
                margem_liquida = excluded.margem_liquida,
                status = 'fechado',
                fechado_em = excluded.fechado_em
            """,
            (
                mes_referencia,
                dre["faturamento_bruto"],
                dre["impostos"],
                dre["comissao"],
                dre["taxa_fixa"],
                dre["custo_produtos"],
                dre["lucro_bruto"],
                dre["despesas"],
                dre["lucro_final"],
                dre["margem_liquida"],
                now_iso(),
            ),
        )


def current_month_reference() -> str:
    from datetime import date

    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"
