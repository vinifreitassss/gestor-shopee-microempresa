from datetime import date

from src.database import fetch_all, get_connection, now_iso


def register_cancelled_order(pedido_id: str, data_cancelamento: date, motivo: str = "") -> dict:
    pedido_id = str(pedido_id or "").strip()
    if not pedido_id:
        raise ValueError("Informe o ID do pedido.")

    timestamp = now_iso()
    with get_connection() as conn:
        order = conn.execute(
            """
            SELECT pedido_id, status_financeiro, valor_liquido_estimado
            FROM shopee_pedidos_financeiros
            WHERE pedido_id = ?
            """,
            (pedido_id,),
        ).fetchone()

        status_anterior = order["status_financeiro"] if order else "pendente"
        valor_baixado = float((order or {}).get("valor_liquido_estimado") or 0)

        conn.execute(
            """
            INSERT INTO cancelamentos_pedidos (
                pedido_id, data_cancelamento, motivo, status_anterior,
                valor_baixado, criado_em, atualizado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pedido_id) DO UPDATE SET
                data_cancelamento = excluded.data_cancelamento,
                motivo = excluded.motivo,
                status_anterior = CASE
                    WHEN cancelamentos_pedidos.status_anterior = ''
                      OR cancelamentos_pedidos.status_anterior = 'pendente'
                    THEN excluded.status_anterior
                    ELSE cancelamentos_pedidos.status_anterior
                END,
                valor_baixado = CASE
                    WHEN excluded.valor_baixado > 0 THEN excluded.valor_baixado
                    ELSE cancelamentos_pedidos.valor_baixado
                END,
                atualizado_em = excluded.atualizado_em
            """,
            (
                pedido_id,
                data_cancelamento.isoformat(),
                motivo,
                status_anterior,
                valor_baixado,
                timestamp,
                timestamp,
            ),
        )

        if order:
            conn.execute(
                """
                UPDATE shopee_pedidos_financeiros
                SET status_financeiro = 'cancelado',
                    status_pedido = CASE
                        WHEN LOWER(status_pedido) LIKE '%cancel%' THEN status_pedido
                        ELSE 'Cancelado manualmente'
                    END,
                    atualizado_em = ?
                WHERE pedido_id = ?
                """,
                (timestamp, pedido_id),
            )

    return {
        "pedido_id": pedido_id,
        "status_anterior": status_anterior,
        "valor_baixado": valor_baixado,
        "encontrado": bool(order),
    }


def apply_manual_cancellations(conn) -> int:
    timestamp = now_iso()
    rows = conn.execute(
        """
        SELECT pedido_id
        FROM cancelamentos_pedidos
        """
    ).fetchall()
    applied = 0
    for item in rows:
        pedido_id = item["pedido_id"]
        order = conn.execute(
            """
            SELECT pedido_id, status_financeiro, valor_liquido_estimado
            FROM shopee_pedidos_financeiros
            WHERE pedido_id = ?
            """,
            (pedido_id,),
        ).fetchone()
        if not order:
            continue
        conn.execute(
            """
            UPDATE cancelamentos_pedidos
            SET status_anterior = CASE
                    WHEN status_anterior = '' OR status_anterior = 'pendente'
                    THEN ?
                    ELSE status_anterior
                END,
                valor_baixado = CASE
                    WHEN valor_baixado = 0 THEN ?
                    ELSE valor_baixado
                END,
                atualizado_em = ?
            WHERE pedido_id = ?
            """,
            (
                order["status_financeiro"],
                float(order["valor_liquido_estimado"] or 0),
                timestamp,
                pedido_id,
            ),
        )
        conn.execute(
            """
            UPDATE shopee_pedidos_financeiros
            SET status_financeiro = 'cancelado',
                status_pedido = CASE
                    WHEN LOWER(status_pedido) LIKE '%cancel%' THEN status_pedido
                    ELSE 'Cancelado manualmente'
                END,
                atualizado_em = ?
            WHERE pedido_id = ?
            """,
            (timestamp, pedido_id),
        )
        applied += 1
    return applied


def list_cancelled_orders() -> list[dict]:
    return fetch_all(
        """
        SELECT
            c.pedido_id,
            c.data_cancelamento,
            c.motivo,
            c.status_anterior,
            c.valor_baixado,
            CASE WHEN p.pedido_id IS NULL THEN 'pendente' ELSE p.status_financeiro END AS status_atual,
            c.criado_em
        FROM cancelamentos_pedidos c
        LEFT JOIN shopee_pedidos_financeiros p ON p.pedido_id = c.pedido_id
        ORDER BY c.data_cancelamento DESC, c.criado_em DESC
        """
    )


def delete_cancelled_order(pedido_id: str) -> bool:
    pedido_id = str(pedido_id or "").strip()
    if not pedido_id:
        return False
    timestamp = now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT pedido_id FROM cancelamentos_pedidos WHERE pedido_id = ?",
            (pedido_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM cancelamentos_pedidos WHERE pedido_id = ?", (pedido_id,))
        conn.execute(
            """
            UPDATE shopee_pedidos_financeiros
            SET status_financeiro = CASE
                    WHEN valor_pago_real > 0 THEN 'liberado'
                    WHEN numero_rastreio IS NOT NULL AND TRIM(numero_rastreio) <> '' THEN 'em_espera'
                    ELSE 'em_aberto'
                END,
                status_pedido = CASE
                    WHEN status_pedido = 'Cancelado manualmente' THEN ''
                    ELSE status_pedido
                END,
                atualizado_em = ?
            WHERE pedido_id = ?
              AND status_financeiro = 'cancelado'
            """,
            (timestamp, pedido_id),
        )
        return True
