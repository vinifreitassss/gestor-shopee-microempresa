from src.database import fetch_all, fetch_one, get_connection, now_iso
from src.services.products_service import save_variation_cost, set_variation_product_type


def add_or_update_recipe_item(variacao_id: int, insumo_id: int, quantidade_usada: float) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ficha_tecnica_insumos (
                variacao_id, insumo_id, quantidade_usada, criado_em
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(variacao_id, insumo_id)
            DO UPDATE SET quantidade_usada = excluded.quantidade_usada
            """,
            (variacao_id, insumo_id, quantidade_usada, now_iso()),
        )


def remove_recipe_item(item_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM ficha_tecnica_insumos WHERE id = ?", (item_id,))


def clear_recipe(variacao_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM ficha_tecnica_insumos WHERE variacao_id = ?", (variacao_id,))


def list_recipe_items(variacao_id: int) -> list[dict]:
    rows = fetch_all(
        """
        SELECT
            fti.id,
            fti.variacao_id,
            fti.insumo_id,
            i.nome AS insumo_nome,
            i.unidade_uso,
            i.custo_compra,
            i.quantidade_total_uso,
            i.uso_minimo_por_pedido,
            fti.quantidade_usada,
            CASE
                WHEN i.quantidade_total_uso > 0
                THEN i.custo_compra / i.quantidade_total_uso
                ELSE 0
            END AS custo_por_unidade_uso,
            CASE
                WHEN i.quantidade_total_uso > 0
                THEN (i.custo_compra / i.quantidade_total_uso) * fti.quantidade_usada
                ELSE 0
            END AS custo_item
        FROM ficha_tecnica_insumos fti
        JOIN insumos i ON i.id = fti.insumo_id
        WHERE fti.variacao_id = ? AND i.ativo = 1
        ORDER BY i.nome
        """,
        (variacao_id,),
    )
    return rows


def calculate_recipe_cost(variacao_id: int) -> float:
    row = fetch_one(
        """
        SELECT COALESCE(SUM(
            CASE
                WHEN i.quantidade_total_uso > 0
                THEN (i.custo_compra / i.quantidade_total_uso) * fti.quantidade_usada
                ELSE 0
            END
        ), 0) AS custo_total
        FROM ficha_tecnica_insumos fti
        JOIN insumos i ON i.id = fti.insumo_id
        WHERE fti.variacao_id = ? AND i.ativo = 1
        """,
        (variacao_id,),
    )
    return float(row["custo_total"] if row else 0)


def apply_recipe_cost_to_variation(variacao_id: int) -> float:
    cost = calculate_recipe_cost(variacao_id)
    if cost <= 0:
        return 0
    save_variation_cost(variacao_id, cost, origem_custo="calculado_por_insumos")
    set_variation_product_type(variacao_id, "fabricado")
    return cost
