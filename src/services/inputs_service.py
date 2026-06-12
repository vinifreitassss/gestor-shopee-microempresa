from src.database import fetch_all, fetch_one, get_connection, now_iso


def add_input(
    nome: str,
    unidade_uso: str,
    quantidade_total_uso: float,
    custo_compra: float,
    uso_minimo_por_pedido: float,
    estoque_atual_uso: float,
) -> None:
    """Cadastra uma matéria-prima.

    Observação importante sobre o banco legado:
    - custo_compra agora representa o CUSTO REFERÊNCIA por unidade de uso.
      Ex.: R$ por cm², R$ por cm, R$ por unidade.
    - quantidade_total_uso é mantido só por compatibilidade e recebe 1 na tela nova.
    """
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
    # A partir desta versão, custo_compra é o custo referência direto.
    # Não dividimos pelo estoque nem pela quantidade total.
    custo_ref = float(row["custo_compra"] or 0)
    uso_ref = float(row["uso_minimo_por_pedido"] or 0)
    estoque_atual = float(row["estoque_atual_uso"] or 0)
    custo_uso_ref = custo_ref * uso_ref if uso_ref > 0 else 0
    valor_estoque = custo_ref * estoque_atual
    return {
        **row,
        "custo_por_unidade_uso": custo_ref,
        "custo_minimo_por_pedido": custo_uso_ref,
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
