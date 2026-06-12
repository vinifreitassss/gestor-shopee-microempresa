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
            ) AS custo_unitario
        FROM variacoes var
        JOIN produtos_pai pp ON pp.id = var.produto_pai_id
        WHERE var.ativo = 1
        ORDER BY pp.nome, var.nome_variacao
        """
    )


def save_variation_cost(variacao_id: int, custo_unitario: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE custos_variacao SET ativo = 0 WHERE variacao_id = ?",
            (variacao_id,),
        )
        conn.execute(
            """
            INSERT INTO custos_variacao (variacao_id, custo_unitario, origem_custo, ativo, criado_em)
            VALUES (?, ?, 'manual', 1, ?)
            """,
            (variacao_id, custo_unitario, now_iso()),
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
