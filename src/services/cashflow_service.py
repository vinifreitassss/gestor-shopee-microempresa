from datetime import date, timedelta

from src.database import fetch_all, fetch_one
from src.services.settings_service import get_setting_float


def month_bounds(mes_referencia: str) -> tuple[str, str]:
    year_text, month_text = mes_referencia.split("-")
    year = int(year_text)
    month = int(month_text)
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def get_cashflow_summary(mes_referencia: str) -> dict:
    start, end = month_bounds(mes_referencia)

    orders = fetch_one(
        """
        SELECT
            COUNT(*) AS pedidos,
            COALESCE(SUM(valor_total), 0) AS valor_bruto,
            COALESCE(SUM(total_global), 0) AS total_global,
            COALESCE(SUM(valor_liquido_estimado), 0) AS liquido_estimado,
            COALESCE(SUM(valor_pago_real), 0) AS pago_real,
            COALESCE(SUM(CASE WHEN valor_pago_real <= 0 THEN valor_liquido_estimado ELSE 0 END), 0) AS em_espera,
            COALESCE(SUM(comissao_liquida), 0) AS comissao,
            COALESCE(SUM(taxa_servico_liquida), 0) AS taxa_servico,
            COALESCE(SUM(taxa_transacao), 0) AS taxa_transacao,
            COALESCE(AVG(
                CASE
                    WHEN data_envio_real IS NOT NULL AND data_envio_real <> ''
                     AND data_pagamento IS NOT NULL AND data_pagamento <> ''
                    THEN julianday(data_envio_real) - julianday(data_pagamento)
                END
            ), 0) AS prazo_envio_medio,
            COALESCE(AVG(
                CASE
                    WHEN data_liberacao_shopee IS NOT NULL AND data_liberacao_shopee <> ''
                     AND data_envio_real IS NOT NULL AND data_envio_real <> ''
                    THEN julianday(data_liberacao_shopee) - julianday(data_envio_real)
                END
            ), 0) AS tempo_liberacao_medio,
            COALESCE(SUM(CASE WHEN status_financeiro = 'divergente' THEN diferenca ELSE 0 END), 0) AS divergencia_total,
            COALESCE(SUM(CASE WHEN status_financeiro = 'divergente' THEN 1 ELSE 0 END), 0) AS pedidos_divergentes
        FROM shopee_pedidos_financeiros
        WHERE date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao))
              BETWEEN date(?) AND date(?)
        """,
        (start, end),
    ) or {}

    latest_balance = fetch_one(
        """
        SELECT balanca_apos_transacoes
        FROM shopee_transacoes
        WHERE date(data_movimento) <= date(?)
        ORDER BY datetime(data_movimento) DESC, id DESC
        LIMIT 1
        """,
        (end,),
    ) or {}

    saques = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS total
        FROM shopee_saques
        WHERE date(data_saque) BETWEEN date(?) AND date(?)
        """,
        (start, end),
    ) or {}

    despesas = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS total
        FROM despesas
        WHERE date(data) BETWEEN date(?) AND date(?)
        """,
        (start, end),
    ) or {}

    imposto_percentual = get_setting_float("imposto_percentual", 9)
    imposto_reservado = float(orders.get("valor_bruto") or 0) * imposto_percentual / 100
    taxa_total = (
        float(orders.get("comissao") or 0)
        + float(orders.get("taxa_servico") or 0)
        + float(orders.get("taxa_transacao") or 0)
    )
    valor_bruto = float(orders.get("valor_bruto") or 0)

    saldo_shopee = float(latest_balance.get("balanca_apos_transacoes") or 0)
    total_saques = float(saques.get("total") or 0)
    total_despesas = float(despesas.get("total") or 0)
    caixa_livre_estimado = saldo_shopee + total_saques - total_despesas - imposto_reservado

    return {
        "periodo_inicio": start,
        "periodo_fim": end,
        "pedidos": int(orders.get("pedidos") or 0),
        "valor_bruto": valor_bruto,
        "liquido_estimado": float(orders.get("liquido_estimado") or 0),
        "pago_real": float(orders.get("pago_real") or 0),
        "em_espera": float(orders.get("em_espera") or 0),
        "saldo_shopee": saldo_shopee,
        "saques": total_saques,
        "despesas": total_despesas,
        "imposto_reservado": imposto_reservado,
        "caixa_livre_estimado": caixa_livre_estimado,
        "taxa_total": taxa_total,
        "taxa_total_percentual": (taxa_total / valor_bruto * 100) if valor_bruto else 0,
        "comissao_media": (float(orders.get("comissao") or 0) / int(orders.get("pedidos") or 1))
        if int(orders.get("pedidos") or 0)
        else 0,
        "ticket_medio_bruto": (valor_bruto / int(orders.get("pedidos") or 1))
        if int(orders.get("pedidos") or 0)
        else 0,
        "ticket_medio_liquido": (
            float(orders.get("liquido_estimado") or 0) / int(orders.get("pedidos") or 1)
        )
        if int(orders.get("pedidos") or 0)
        else 0,
        "prazo_envio_medio": float(orders.get("prazo_envio_medio") or 0),
        "tempo_liberacao_medio": float(orders.get("tempo_liberacao_medio") or 0),
        "divergencia_total": float(orders.get("divergencia_total") or 0),
        "pedidos_divergentes": int(orders.get("pedidos_divergentes") or 0),
        "imposto_percentual": imposto_percentual,
    }


def list_cashflow_events(mes_referencia: str, limit: int = 200) -> list[dict]:
    start, end = month_bounds(mes_referencia)

    rows = fetch_all(
        """
        SELECT
            date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao)) AS data,
            'Entrada prevista' AS tipo,
            pedido_id AS referencia,
            'Pedido enviado / em espera Shopee' AS descricao,
            valor_liquido_estimado AS entrada,
            0 AS saida,
            status_financeiro AS status
        FROM shopee_pedidos_financeiros
        WHERE date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao))
              BETWEEN date(?) AND date(?)

        UNION ALL

        SELECT
            date(data_movimento) AS data,
            'Entrada Shopee' AS tipo,
            COALESCE(pedido_id, '') AS referencia,
            tipo_transacao AS descricao,
            valor AS entrada,
            0 AS saida,
            status_conciliacao AS status
        FROM shopee_transacoes
        WHERE LOWER(direcao) = 'entrada'
          AND date(data_movimento) BETWEEN date(?) AND date(?)

        UNION ALL

        SELECT
            date(data_saque) AS data,
            'Transferência' AS tipo,
            'Shopee → Banco' AS referencia,
            'Saque da Shopee para conta bancária' AS descricao,
            valor AS entrada,
            0 AS saida,
            status AS status
        FROM shopee_saques
        WHERE date(data_saque) BETWEEN date(?) AND date(?)

        UNION ALL

        SELECT
            data AS data,
            'Saída' AS tipo,
            categoria AS referencia,
            descricao AS descricao,
            0 AS entrada,
            valor AS saida,
            'despesa' AS status
        FROM despesas
        WHERE date(data) BETWEEN date(?) AND date(?)

        ORDER BY data ASC, tipo ASC
        LIMIT ?
        """,
        (start, end, start, end, start, end, start, end, limit),
    )
    return rows


def list_shopee_pipeline(mes_referencia: str, limit: int = 200) -> list[dict]:
    start, end = month_bounds(mes_referencia)
    return fetch_all(
        """
        SELECT
            pedido_id,
            date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao)) AS data_envio,
            valor_total,
            valor_liquido_estimado,
            valor_pago_real,
            diferenca,
            status_financeiro,
            CASE
                WHEN data_liberacao_shopee IS NULL OR data_liberacao_shopee = '' THEN ''
                ELSE date(data_liberacao_shopee)
            END AS data_liberacao
        FROM shopee_pedidos_financeiros
        WHERE date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao))
              BETWEEN date(?) AND date(?)
        ORDER BY
            CASE status_financeiro
                WHEN 'divergente' THEN 0
                WHEN 'em_espera' THEN 1
                ELSE 2
            END,
            date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao)) ASC
        LIMIT ?
        """,
        (start, end, limit),
    )
