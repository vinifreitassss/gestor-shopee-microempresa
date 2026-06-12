from src.database import fetch_all, get_connection, now_iso


def list_variations() -> list[dict]:
    return fetch_all(
        """
        SELECT
            var.id,
            pp.nome AS produto_pai,
            var.nome_variacao,
            var.sku,
            var.tipo_produto,
            (
                SELECT custo_unitario
                FROM custos_variacao cv
                WHERE cv.variacao_id = var.id AND cv.ativo = 1
                ORDER BY cv.criado_em DESC, cv.id DESC
                LIMIT 1
            ) AS custo_unitario,
            (
                SELECT origem_custo
                FROM custos_variacao cv
                WHERE cv.variacao_id = var.id AND cv.ativo = 1
                ORDER BY cv.criado_em DESC, cv.id DESC
                LIMIT 1
            ) AS origem_custo
        FROM variacoes var
        JOIN produtos_pai pp ON pp.id = var.produto_pai_id
        WHERE var.ativo = 1
        ORDER BY pp.nome, var.nome_variacao
        """
    )


def save_variation_cost(variacao_id: int, custo_unitario: float, origem_custo: str = "manual") -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE custos_variacao SET ativo = 0 WHERE variacao_id = ?",
            (variacao_id,),
        )
        conn.execute(
            """
            INSERT INTO custos_variacao (variacao_id, custo_unitario, origem_custo, ativo, criado_em)
            VALUES (?, ?, ?, 1, ?)
            """,
            (variacao_id, custo_unitario, origem_custo, now_iso()),
        )
        _recalculate_incomplete_sales(conn, variacao_id, custo_unitario)


def set_variation_product_type(variacao_id: int, tipo_produto: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE variacoes SET tipo_produto = ? WHERE id = ?",
            (tipo_produto, variacao_id),
        )


def _recalculate_incomplete_sales(conn, variacao_id: int, custo_unitario: float) -> None:
    rows = conn.execute(
        """
        SELECT id, unidades, faturamento, imposto_valor, comissao_valor, taxa_fixa_valor
        FROM vendas_contabilizadas
        WHERE variacao_id = ? AND lucro_incompleto = 1
        """,
        (variacao_id,),
    ).fetchall()

    for row in rows:
        custo_total = float(row["unidades"] or 0) * custo_unitario
        lucro = (
            float(row["faturamento"] or 0)
            - float(row["imposto_valor"] or 0)
            - float(row["comissao_valor"] or 0)
            - float(row["taxa_fixa_valor"] or 0)
            - custo_total
        )
        conn.execute(
            """
            UPDATE vendas_contabilizadas
            SET custo_unitario_usado = ?,
                custo_total = ?,
                lucro = ?,
                lucro_incompleto = 0
            WHERE id = ?
            """,
            (custo_unitario, custo_total, lucro, row["id"]),
        )


def list_importations() -> list[dict]:
    return fetch_all(
        """
        SELECT
            id,
            arquivo_nome,
            tipo_periodo,
            data_inicio,
            data_fim,
            mes_referencia,
            status,
            criado_em
        FROM importacoes
        ORDER BY criado_em DESC
        LIMIT 100
        """
    )
