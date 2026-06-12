from src.database import fetch_all, fetch_one, get_connection, now_iso


def add_input(
    nome: str,
    unidade_uso: str,
    quantidade_total_uso: float,
    custo_compra: float,
    uso_minimo_por_pedido: float,
    estoque_atual_uso: float,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO insumos (
                nome, unidade_uso, quantidade_total_uso, custo_compra,
                uso_minimo_por_pedido, estoque_atual_uso, ativo, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                nome,
                unidade_uso,
                quantidade_total_uso,
                custo_compra,
                uso_minimo_por_pedido,
                estoque_atual_uso,
                now_iso(),
            ),
        )


def update_input(
    input_id: int,
    nome: str,
    unidade_uso: str,
    quantidade_total_uso: float,
    custo_compra: float,
    uso_minimo_por_pedido: float,
    estoque_atual_uso: float,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE insumos
            SET nome = ?,
                unidade_uso = ?,
                quantidade_total_uso = ?,
                custo_compra = ?,
                uso_minimo_por_pedido = ?,
                estoque_atual_uso = ?
            WHERE id = ?
            """,
            (
                nome,
                unidade_uso,
                quantidade_total_uso,
                custo_compra,
                uso_minimo_por_pedido,
                estoque_atual_uso,
                input_id,
            ),
        )


def get_input(input_id: int) -> dict | None:
    row = fetch_one(
        """
        SELECT
            id,
            nome,
            unidade_uso,
            quantidade_total_uso,
            custo_compra,
            uso_minimo_por_pedido,
            estoque_atual_uso,
            criado_em
        FROM insumos
        WHERE id = ? AND ativo = 1
        """,
        (input_id,),
    )
    if not row:
        return None
    return _with_calculated_fields(row)


def list_inputs() -> list[dict]:
    rows = fetch_all(
        """
        SELECT
            id,
            nome,
            unidade_uso,
            quantidade_total_uso,
            custo_compra,
            uso_minimo_por_pedido,
            estoque_atual_uso,
            criado_em
        FROM insumos
        WHERE ativo = 1
        ORDER BY nome
        """
    )
    return [_with_calculated_fields(row) for row in rows]


def _with_calculated_fields(row: dict) -> dict:
    quantidade_total = float(row["quantidade_total_uso"] or 0)
    custo_compra = float(row["custo_compra"] or 0)
    uso_minimo = float(row["uso_minimo_por_pedido"] or 0)
    estoque_atual = float(row["estoque_atual_uso"] or 0)
    custo_por_unidade = custo_compra / quantidade_total if quantidade_total else 0
    custo_minimo = custo_por_unidade * uso_minimo
    valor_estoque = custo_por_unidade * estoque_atual
    return {
        **row,
        "custo_por_unidade_uso": custo_por_unidade,
        "custo_minimo_por_pedido": custo_minimo,
        "valor_estoque": valor_estoque,
    }


def update_input_stock(input_id: int, estoque_atual_uso: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE insumos SET estoque_atual_uso = ? WHERE id = ?",
            (estoque_atual_uso, input_id),
        )


def deactivate_input(input_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE insumos SET ativo = 0 WHERE id = ?", (input_id,))
