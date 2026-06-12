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
            ) AS origem_custo,
            regra.base_variacao_id,
            regra.multiplicador AS regra_multiplicador,
            regra.descricao AS regra_descricao,
            base_pp.nome AS base_produto_pai,
            base_var.nome_variacao AS base_nome_variacao
        FROM variacoes var
        JOIN produtos_pai pp ON pp.id = var.produto_pai_id
        LEFT JOIN regras_custo_variacao regra
            ON regra.variacao_id = var.id AND regra.ativo = 1
        LEFT JOIN variacoes base_var
            ON base_var.id = regra.base_variacao_id
        LEFT JOIN produtos_pai base_pp
            ON base_pp.id = base_var.produto_pai_id
        WHERE var.ativo = 1
        ORDER BY pp.nome, var.nome_variacao
        """
    )


def save_variation_cost(variacao_id: int, custo_unitario: float, origem_custo: str = "manual") -> None:
    """Salva o custo atual da variação e recalcula vendas abertas.

    Refinamento da regra:
    - Atualizar custo da VARIAÇÃO é uma correção/apuração deliberada.
      Portanto recalcula vendas de meses ainda não fechados.
    - Meses fechados continuam congelados.
    - Alterar custo de INSUMO sozinho não chama esta função; só impacta o DRE
      quando o usuário aplicar novamente o custo calculado na variação.
    - Se a variação tiver dependentes por multiplicador, eles são atualizados.
    """
    with get_connection() as conn:
        _save_variation_cost(
            conn,
            variacao_id=variacao_id,
            custo_unitario=custo_unitario,
            origem_custo=origem_custo,
            clear_rule=True,
        )
        _apply_dependent_rules(conn, variacao_id, custo_unitario, visited={variacao_id})


def apply_multiplier_rule(
    variacao_id: int,
    base_variacao_id: int,
    multiplicador: float,
    descricao: str = "",
) -> float:
    """Faz uma variação usar o custo de outra variação multiplicado.

    Exemplos:
    - medalha 30 un. = base medalha 10 un. x 3
    - produto semelhante = base x 1
    - produto mais trabalhoso = base x 1.2
    """
    if variacao_id == base_variacao_id:
        raise ValueError("A variação não pode usar ela mesma como base.")
    if multiplicador <= 0:
        raise ValueError("O multiplicador precisa ser maior que zero.")

    with get_connection() as conn:
        _validate_no_cycle(conn, variacao_id, base_variacao_id)
        base_cost = _get_active_cost(conn, base_variacao_id)
        if base_cost is None:
            raise ValueError("A variação base ainda não possui custo ativo.")

        now = now_iso()
        conn.execute(
            """
            INSERT INTO regras_custo_variacao (
                variacao_id, base_variacao_id, multiplicador, descricao,
                ativo, criado_em, atualizado_em
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(variacao_id)
            DO UPDATE SET
                base_variacao_id = excluded.base_variacao_id,
                multiplicador = excluded.multiplicador,
                descricao = excluded.descricao,
                ativo = 1,
                atualizado_em = excluded.atualizado_em
            """,
            (variacao_id, base_variacao_id, multiplicador, descricao, now, now),
        )

        calculated_cost = base_cost * multiplicador
        origem = f"regra_multiplicador:base={base_variacao_id};x={multiplicador:g}"
        _save_variation_cost(
            conn,
            variacao_id=variacao_id,
            custo_unitario=calculated_cost,
            origem_custo=origem,
            clear_rule=False,
        )
        _apply_dependent_rules(conn, variacao_id, calculated_cost, visited={base_variacao_id, variacao_id})
        return calculated_cost


def remove_multiplier_rule(variacao_id: int) -> bool:
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id FROM regras_custo_variacao
            WHERE variacao_id = ? AND ativo = 1
            """,
            (variacao_id,),
        ).fetchone()
        if not existing:
            return False
        conn.execute(
            "UPDATE regras_custo_variacao SET ativo = 0, atualizado_em = ? WHERE id = ?",
            (now_iso(), existing["id"]),
        )
        return True


def remove_current_variation_cost(variacao_id: int) -> bool:
    """Remove o custo ativo da variação e reabre vendas não fechadas.

    A ideia é evitar DRE errado quando um custo foi aplicado por engano.
    Fechamentos mensais já fechados não são alterados.
    """
    with get_connection() as conn:
        current = conn.execute(
            """
            SELECT id
            FROM custos_variacao
            WHERE variacao_id = ? AND ativo = 1
            ORDER BY criado_em DESC, id DESC
            LIMIT 1
            """,
            (variacao_id,),
        ).fetchone()
        if not current:
            return False

        conn.execute(
            "UPDATE custos_variacao SET ativo = 0 WHERE id = ?",
            (current["id"],),
        )
        conn.execute(
            "UPDATE regras_custo_variacao SET ativo = 0, atualizado_em = ? WHERE variacao_id = ?",
            (now_iso(), variacao_id),
        )
        _mark_open_sales_as_incomplete(conn, variacao_id)
        return True


def set_variation_product_type(variacao_id: int, tipo_produto: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE variacoes SET tipo_produto = ? WHERE id = ?",
            (tipo_produto, variacao_id),
        )


def _save_variation_cost(
    conn,
    variacao_id: int,
    custo_unitario: float,
    origem_custo: str,
    clear_rule: bool,
) -> None:
    if clear_rule:
        conn.execute(
            "UPDATE regras_custo_variacao SET ativo = 0, atualizado_em = ? WHERE variacao_id = ?",
            (now_iso(), variacao_id),
        )
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
    _recalculate_open_sales(conn, variacao_id, custo_unitario)


def _get_active_cost(conn, variacao_id: int) -> float | None:
    row = conn.execute(
        """
        SELECT custo_unitario
        FROM custos_variacao
        WHERE variacao_id = ? AND ativo = 1
        ORDER BY criado_em DESC, id DESC
        LIMIT 1
        """,
        (variacao_id,),
    ).fetchone()
    if not row:
        return None
    return float(row["custo_unitario"])


def _apply_dependent_rules(conn, base_variacao_id: int, base_cost: float, visited: set[int]) -> None:
    dependents = conn.execute(
        """
        SELECT variacao_id, multiplicador
        FROM regras_custo_variacao
        WHERE base_variacao_id = ? AND ativo = 1
        """,
        (base_variacao_id,),
    ).fetchall()

    for row in dependents:
        target_id = int(row["variacao_id"])
        if target_id in visited:
            continue
        multiplier = float(row["multiplicador"] or 1)
        new_cost = base_cost * multiplier
        origem = f"regra_multiplicador:base={base_variacao_id};x={multiplier:g}"
        _save_variation_cost(
            conn,
            variacao_id=target_id,
            custo_unitario=new_cost,
            origem_custo=origem,
            clear_rule=False,
        )
        visited.add(target_id)
        _apply_dependent_rules(conn, target_id, new_cost, visited)


def _validate_no_cycle(conn, target_variacao_id: int, base_variacao_id: int) -> None:
    seen = {target_variacao_id}
    current = base_variacao_id
    while current:
        if current in seen:
            raise ValueError("Essa regra criaria um ciclo entre variações.")
        seen.add(current)
        row = conn.execute(
            """
            SELECT base_variacao_id
            FROM regras_custo_variacao
            WHERE variacao_id = ? AND ativo = 1
            """,
            (current,),
        ).fetchone()
        current = int(row["base_variacao_id"]) if row else 0


def _recalculate_open_sales(conn, variacao_id: int, custo_unitario: float) -> None:
    rows = conn.execute(
        """
        SELECT id, unidades, faturamento, imposto_valor, comissao_valor, taxa_fixa_valor
        FROM vendas_contabilizadas
        WHERE variacao_id = ?
          AND mes_referencia NOT IN (
              SELECT mes_referencia
              FROM fechamentos_mensais
              WHERE status = 'fechado'
          )
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


def _mark_open_sales_as_incomplete(conn, variacao_id: int) -> None:
    conn.execute(
        """
        UPDATE vendas_contabilizadas
        SET custo_unitario_usado = NULL,
            custo_total = NULL,
            lucro = NULL,
            lucro_incompleto = 1
        WHERE variacao_id = ?
          AND mes_referencia NOT IN (
              SELECT mes_referencia
              FROM fechamentos_mensais
              WHERE status = 'fechado'
          )
        """,
        (variacao_id,),
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
