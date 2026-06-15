from datetime import date, timedelta

from src.database import fetch_all, fetch_one, get_connection, now_iso
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


def get_initial_position() -> dict | None:
    return fetch_one(
        """
        SELECT *
        FROM posicoes_iniciais_caixa
        ORDER BY date(data_corte) DESC, id DESC
        LIMIT 1
        """
    )


def save_initial_position(
    data_corte: date,
    saldo_banco: float,
    saldo_shopee_disponivel: float,
    saldo_shopee_espera: float,
) -> int:
    timestamp = now_iso()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO posicoes_iniciais_caixa (
                data_corte,
                saldo_banco,
                saldo_shopee_disponivel,
                saldo_shopee_espera,
                observacao,
                criado_em,
                atualizado_em
            ) VALUES (?, ?, ?, ?, 'posição inicial informada manualmente', ?, ?)
            """,
            (
                data_corte.isoformat(),
                saldo_banco,
                saldo_shopee_disponivel,
                saldo_shopee_espera,
                timestamp,
                timestamp,
            ),
        )
        return int(cursor.lastrowid)


def _movement_start(month_start: str, initial: dict | None) -> str:
    if not initial:
        return month_start
    corte = str(initial.get("data_corte") or month_start)
    return max(month_start, corte)


def get_cashflow_summary(mes_referencia: str) -> dict:
    month_start, month_end = month_bounds(mes_referencia)
    initial = get_initial_position()
    start = _movement_start(month_start, initial)
    end = month_end

    initial_bank = float((initial or {}).get("saldo_banco") or 0)
    initial_shopee_cash = float((initial or {}).get("saldo_shopee_disponivel") or 0)
    initial_shopee_waiting = float((initial or {}).get("saldo_shopee_espera") or 0)

    orders = fetch_one(
        """
        SELECT
            COUNT(*) AS pedidos,
            COALESCE(SUM(valor_total), 0) AS valor_bruto,
            COALESCE(SUM(valor_liquido_estimado), 0) AS liquido_estimado,
            COALESCE(SUM(comissao_liquida), 0) AS comissao,
            COALESCE(SUM(taxa_servico_liquida), 0) AS taxa_servico,
            COALESCE(SUM(taxa_transacao), 0) AS taxa_transacao,
            COALESCE(AVG(
                CASE
                    WHEN data_envio_real IS NOT NULL AND data_envio_real <> ''
                     AND data_pagamento IS NOT NULL AND data_pagamento <> ''
                    THEN julianday(data_envio_real) - julianday(data_pagamento)
                END
            ), 0) AS prazo_envio_medio
        FROM shopee_pedidos_financeiros
        WHERE numero_rastreio IS NOT NULL
          AND TRIM(numero_rastreio) <> ''
          AND status_financeiro <> 'cancelado'
          AND date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao))
              BETWEEN date(?) AND date(?)
        """,
        (start, end),
    ) or {}

    payments = fetch_one(
        """
        SELECT
            COALESCE(SUM(CASE WHEN pedido_id IS NOT NULL AND TRIM(pedido_id) <> '' THEN valor ELSE 0 END), 0) AS pagamentos_pedidos,
            COALESCE(SUM(CASE WHEN pedido_id IS NULL OR TRIM(pedido_id) = '' THEN valor ELSE 0 END), 0) AS pagamentos_sem_pedido,
            COALESCE(SUM(valor), 0) AS entradas_totais,
            COALESCE(AVG(
                CASE
                    WHEN p.data_envio_real IS NOT NULL AND p.data_envio_real <> ''
                    THEN julianday(t.data_movimento) - julianday(p.data_envio_real)
                END
            ), 0) AS tempo_liberacao_medio
        FROM shopee_transacoes t
        LEFT JOIN shopee_pedidos_financeiros p ON p.pedido_id = t.pedido_id
        WHERE LOWER(t.direcao) = 'entrada'
          AND date(t.data_movimento) BETWEEN date(?) AND date(?)
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

    divergences = fetch_one(
        """
        SELECT
            COALESCE(SUM(CASE WHEN status_financeiro = 'divergente' THEN diferenca ELSE 0 END), 0) AS total,
            COALESCE(SUM(CASE WHEN status_financeiro = 'divergente' THEN 1 ELSE 0 END), 0) AS pedidos
        FROM shopee_pedidos_financeiros
        WHERE numero_rastreio IS NOT NULL
          AND TRIM(numero_rastreio) <> ''
          AND status_financeiro <> 'cancelado'
          AND date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao))
              BETWEEN date(?) AND date(?)
        """,
        (start, end),
    ) or {}

    valor_bruto = float(orders.get("valor_bruto") or 0)
    liquido_enviado = float(orders.get("liquido_estimado") or 0)
    pagamentos_pedidos = float(payments.get("pagamentos_pedidos") or 0)
    pagamentos_sem_pedido = float(payments.get("pagamentos_sem_pedido") or 0)
    entradas_totais = float(payments.get("entradas_totais") or 0)
    total_saques = float(saques.get("total") or 0)
    total_despesas = float(despesas.get("total") or 0)

    # Regra de transição: como o controle está começando sem histórico completo,
    # toda entrada Shopee reduz o saldo em espera. Apenas pedidos com rastreio
    # aumentam o saldo em espera.
    abatimento_espera = entradas_totais

    shopee_em_espera = initial_shopee_waiting + liquido_enviado - abatimento_espera
    shopee_caixa = initial_shopee_cash + entradas_totais - total_saques
    banco = initial_bank + total_saques - total_despesas

    imposto_percentual = get_setting_float("imposto_percentual", 9)
    imposto_reservado = valor_bruto * imposto_percentual / 100
    taxa_total = (
        float(orders.get("comissao") or 0)
        + float(orders.get("taxa_servico") or 0)
        + float(orders.get("taxa_transacao") or 0)
    )
    caixa_livre = banco + shopee_caixa - imposto_reservado

    return {
        "periodo_inicio": start,
        "periodo_fim": end,
        "data_corte": (initial or {}).get("data_corte", ""),
        "saldo_banco": banco,
        "saldo_shopee_disponivel": shopee_caixa,
        "saldo_shopee_espera": shopee_em_espera,
        "saldo_shopee_relatorio": float(latest_balance.get("balanca_apos_transacoes") or 0),
        "caixa_disponivel": banco + shopee_caixa,
        "caixa_livre_estimado": caixa_livre,
        "pedidos": int(orders.get("pedidos") or 0),
        "valor_bruto": valor_bruto,
        "liquido_estimado": liquido_enviado,
        "pagamentos_pedidos": pagamentos_pedidos,
        "pagamentos_sem_pedido": pagamentos_sem_pedido,
        "abatimento_espera": abatimento_espera,
        "entradas_shopee": entradas_totais,
        "saques": total_saques,
        "despesas": total_despesas,
        "imposto_reservado": imposto_reservado,
        "taxa_total": taxa_total,
        "taxa_total_percentual": (taxa_total / valor_bruto * 100) if valor_bruto else 0,
        "comissao_media": (float(orders.get("comissao") or 0) / int(orders.get("pedidos") or 1))
        if int(orders.get("pedidos") or 0)
        else 0,
        "ticket_medio_bruto": (valor_bruto / int(orders.get("pedidos") or 1))
        if int(orders.get("pedidos") or 0)
        else 0,
        "ticket_medio_liquido": (liquido_enviado / int(orders.get("pedidos") or 1))
        if int(orders.get("pedidos") or 0)
        else 0,
        "prazo_envio_medio": float(orders.get("prazo_envio_medio") or 0),
        "tempo_liberacao_medio": float(payments.get("tempo_liberacao_medio") or 0),
        "divergencia_total": float(divergences.get("total") or 0),
        "pedidos_divergentes": int(divergences.get("pedidos") or 0),
        "imposto_percentual": imposto_percentual,
    }


def list_cashflow_events(mes_referencia: str, limit: int = 200) -> list[dict]:
    start, end = month_bounds(mes_referencia)
    return fetch_all(
        """
        SELECT
            date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao)) AS data,
            'Entrada prevista' AS tipo,
            pedido_id AS referencia,
            'Pedido com rastreio / em espera Shopee' AS descricao,
            valor_liquido_estimado AS entrada,
            0 AS saida,
            status_financeiro AS status
        FROM shopee_pedidos_financeiros
        WHERE numero_rastreio IS NOT NULL
          AND TRIM(numero_rastreio) <> ''
          AND status_financeiro <> 'cancelado'
          AND date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao))
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
            'Shopee para Banco' AS referencia,
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


def list_shopee_pipeline(mes_referencia: str, limit: int = 200) -> list[dict]:
    start, end = month_bounds(mes_referencia)
    return fetch_all(
        """
        SELECT
            pedido_id,
            numero_rastreio,
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
                WHEN 'em_aberto' THEN 2
                ELSE 3
            END,
            date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao)) ASC
        LIMIT ?
        """,
        (start, end, limit),
    )
