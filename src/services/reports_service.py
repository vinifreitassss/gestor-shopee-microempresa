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
    return fetch_all(
        """
        SELECT
            pp.nome AS produto_pai,
            COALESCE(SUM(v.faturamento), 0) AS faturamento,
            COALESCE(SUM(v.unidades), 0) AS unidades,
            COALESCE(SUM(COALESCE(v.lucro, 0)), 0) AS lucro
        FROM vendas_contabilizadas v
        JOIN produtos_pai pp ON pp.id = v.produto_pai_id
        WHERE v.mes_referencia = ?
        GROUP BY pp.id, pp.nome
        ORDER BY faturamento DESC
        LIMIT 20
        """,
        (mes_referencia,),
    )


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
