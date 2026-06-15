from datetime import date, timedelta

from src.database import fetch_all, fetch_one, get_connection, now_iso
from src.services.settings_service import get_setting_float


def month_bounds(mes_referencia: str) -> tuple[str, str]:
    parts = mes_referencia.strip().split("-")
    if len(parts) < 2:
        raise ValueError("Informe o mês no formato AAAA-MM, exemplo: 2026-06.")
    year = int(parts[0])
    month = int(parts[1])
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
        ORDER BY id DESC
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
        conn.execute("DELETE FROM posicoes_iniciais_caixa")
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
            ) VALUES (?, ?, ?, ?, 'posição inicial ativa', ?, ?)
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


def _balance_start(initial: dict | None) -> str:
    if not initial:
        return "1900-01-01"
    return str(initial.get("data_corte") or "1900-01-01")


def _positive(value: float) -> float:
    return value if value > 0 else 0


def _date_range(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    last = date.fromisoformat(end)
    days = []
    while current <= last:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def get_cashflow_summary(mes_referencia: str) -> dict:
    month_start, month_end = month_bounds(mes_referencia)
    initial = get_initial_position()
    balance_start = _balance_start(initial)
    balance_end = month_end

    initial_bank = float((initial or {}).get("saldo_banco") or 0)
    initial_shopee_cash = float((initial or {}).get("saldo_shopee_disponivel") or 0)
    initial_shopee_waiting = float((initial or {}).get("saldo_shopee_espera") or 0)

    waiting_orders = fetch_one(
        """
        SELECT
            COUNT(*) AS pedidos,
            COALESCE(SUM(valor_total), 0) AS valor_bruto,
            COALESCE(SUM(valor_liquido_estimado), 0) AS liquido_estimado,
            COALESCE(SUM(comissao_liquida), 0) AS comissao,
            COALESCE(SUM(taxa_servico_liquida), 0) AS taxa_servico,
            COALESCE(SUM(taxa_transacao), 0) AS taxa_transacao
        FROM shopee_pedidos_financeiros
        WHERE numero_rastreio IS NOT NULL
          AND TRIM(numero_rastreio) <> ''
          AND status_financeiro = 'em_espera'
        """
    ) or {}

    tracked_orders_month = fetch_one(
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
        (month_start, month_end),
    ) or {}

    open_orders = fetch_one(
        """
        SELECT
            COUNT(*) AS pedidos_em_aberto,
            COALESCE(SUM(valor_total), 0) AS valor_bruto_aberto,
            COALESCE(SUM(valor_liquido_estimado), 0) AS saldo_possivel_aberto
        FROM shopee_pedidos_financeiros
        WHERE (numero_rastreio IS NULL OR TRIM(numero_rastreio) = '')
          AND status_financeiro = 'em_aberto'
        """
    ) or {}

    payments_balance = fetch_one(
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
        (balance_start, balance_end),
    ) or {}

    payments_month = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS entradas_totais
        FROM shopee_transacoes
        WHERE LOWER(direcao) = 'entrada'
          AND date(data_movimento) BETWEEN date(?) AND date(?)
        """,
        (month_start, month_end),
    ) or {}

    latest_balance = fetch_one(
        """
        SELECT balanca_apos_transacoes
        FROM shopee_transacoes
        WHERE date(data_movimento) <= date(?)
        ORDER BY datetime(data_movimento) DESC, id DESC
        LIMIT 1
        """,
        (balance_end,),
    ) or {}

    saques_balance = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS total
        FROM shopee_saques
        WHERE date(data_saque) BETWEEN date(?) AND date(?)
        """,
        (balance_start, balance_end),
    ) or {}

    saques_month = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS total
        FROM shopee_saques
        WHERE date(data_saque) BETWEEN date(?) AND date(?)
        """,
        (month_start, month_end),
    ) or {}

    despesas_balance = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS total
        FROM despesas
        WHERE date(data) BETWEEN date(?) AND date(?)
        """,
        (balance_start, balance_end),
    ) or {}

    despesas_month = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS total
        FROM despesas
        WHERE date(data) BETWEEN date(?) AND date(?)
        """,
        (month_start, month_end),
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
        (month_start, month_end),
    ) or {}

    valor_bruto = float(tracked_orders_month.get("valor_bruto") or 0)
    liquido_rastreado_mes = float(tracked_orders_month.get("liquido_estimado") or 0)
    liquido_em_espera_atual = float(waiting_orders.get("liquido_estimado") or 0)
    pagamentos_pedidos = float(payments_balance.get("pagamentos_pedidos") or 0)
    pagamentos_sem_pedido = float(payments_balance.get("pagamentos_sem_pedido") or 0)
    entradas_acumuladas = float(payments_balance.get("entradas_totais") or 0)
    entradas_mes = float(payments_month.get("entradas_totais") or 0)
    total_saques_acumulado = float(saques_balance.get("total") or 0)
    total_saques_mes = float(saques_month.get("total") or 0)
    total_despesas_acumulado = float(despesas_balance.get("total") or 0)
    total_despesas_mes = float(despesas_month.get("total") or 0)
    saldo_possivel_aberto = float(open_orders.get("saldo_possivel_aberto") or 0)
    valor_bruto_aberto = float(open_orders.get("valor_bruto_aberto") or 0)
    pedidos_em_aberto = int(open_orders.get("pedidos_em_aberto") or 0)

    abatimento_espera = entradas_acumuladas
    shopee_em_espera = _positive(initial_shopee_waiting + liquido_em_espera_atual - abatimento_espera)
    shopee_caixa = initial_shopee_cash + entradas_acumuladas - total_saques_acumulado
    banco = initial_bank + total_saques_acumulado - total_despesas_acumulado

    disponibilidades = banco + shopee_caixa
    total_gerencial = disponibilidades + shopee_em_espera + saldo_possivel_aberto

    imposto_percentual = get_setting_float("imposto_percentual", 9)
    imposto_reservado = valor_bruto * imposto_percentual / 100
    taxa_total = (
        float(tracked_orders_month.get("comissao") or 0)
        + float(tracked_orders_month.get("taxa_servico") or 0)
        + float(tracked_orders_month.get("taxa_transacao") or 0)
    )
    caixa_livre = disponibilidades - imposto_reservado
    pedidos_rastreados_mes = int(tracked_orders_month.get("pedidos") or 0)

    return {
        "periodo_inicio": month_start,
        "periodo_fim": month_end,
        "data_corte": (initial or {}).get("data_corte", ""),
        "saldo_banco": banco,
        "saldo_shopee_disponivel": shopee_caixa,
        "saldo_shopee_espera": shopee_em_espera,
        "saldo_possivel_aberto": saldo_possivel_aberto,
        "valor_bruto_aberto": valor_bruto_aberto,
        "pedidos_em_aberto": pedidos_em_aberto,
        "saldo_shopee_relatorio": float(latest_balance.get("balanca_apos_transacoes") or 0),
        "caixa_disponivel": disponibilidades,
        "disponibilidades": disponibilidades,
        "total_dinheiro_gerencial": total_gerencial,
        "caixa_livre_estimado": caixa_livre,
        "pedidos": pedidos_rastreados_mes,
        "valor_bruto": valor_bruto,
        "liquido_estimado": liquido_rastreado_mes,
        "pagamentos_pedidos": pagamentos_pedidos,
        "pagamentos_sem_pedido": pagamentos_sem_pedido,
        "abatimento_espera": abatimento_espera,
        "entradas_shopee": entradas_mes,
        "saques": total_saques_mes,
        "despesas": total_despesas_mes,
        "imposto_reservado": imposto_reservado,
        "taxa_total": taxa_total,
        "taxa_total_percentual": (taxa_total / valor_bruto * 100) if valor_bruto else 0,
        "comissao_media": (float(tracked_orders_month.get("comissao") or 0) / pedidos_rastreados_mes) if pedidos_rastreados_mes else 0,
        "ticket_medio_bruto": (valor_bruto / pedidos_rastreados_mes) if pedidos_rastreados_mes else 0,
        "ticket_medio_liquido": (liquido_rastreado_mes / pedidos_rastreados_mes) if pedidos_rastreados_mes else 0,
        "prazo_envio_medio": float(tracked_orders_month.get("prazo_envio_medio") or 0),
        "tempo_liberacao_medio": float(payments_balance.get("tempo_liberacao_medio") or 0),
        "divergencia_total": float(divergences.get("total") or 0),
        "pedidos_divergentes": int(divergences.get("pedidos") or 0),
        "imposto_percentual": imposto_percentual,
    }


def list_daily_cashflow_forecast(mes_referencia: str) -> list[dict]:
    start, end = month_bounds(mes_referencia)
    summary = get_cashflow_summary(mes_referencia)

    rows_by_date = {
        day: {
            "data": day,
            "envio_previsto": 0.0,
            "entrada_shopee": 0.0,
            "saque": 0.0,
            "despesa": 0.0,
            "saldo_disponivel": 0.0,
            "saldo_total_gerencial": 0.0,
        }
        for day in _date_range(start, end)
    }

    for row in fetch_all(
        """
        SELECT
            date(COALESCE(NULLIF(data_prevista_envio, ''), NULLIF(data_criacao, ''), ?)) AS data,
            COALESCE(SUM(valor_liquido_estimado), 0) AS valor
        FROM shopee_pedidos_financeiros
        WHERE (numero_rastreio IS NULL OR TRIM(numero_rastreio) = '')
          AND status_financeiro = 'em_aberto'
          AND date(COALESCE(NULLIF(data_prevista_envio, ''), NULLIF(data_criacao, ''), ?)) BETWEEN date(?) AND date(?)
        GROUP BY date(COALESCE(NULLIF(data_prevista_envio, ''), NULLIF(data_criacao, ''), ?))
        """,
        (start, start, start, end, start),
    ):
        if row["data"] in rows_by_date:
            rows_by_date[row["data"]]["envio_previsto"] = float(row["valor"] or 0)

    for row in fetch_all(
        """
        SELECT date(data_movimento) AS data, COALESCE(SUM(valor), 0) AS valor
        FROM shopee_transacoes
        WHERE LOWER(direcao) = 'entrada'
          AND date(data_movimento) BETWEEN date(?) AND date(?)
        GROUP BY date(data_movimento)
        """,
        (start, end),
    ):
        if row["data"] in rows_by_date:
            rows_by_date[row["data"]]["entrada_shopee"] = float(row["valor"] or 0)

    for row in fetch_all(
        """
        SELECT date(data_saque) AS data, COALESCE(SUM(valor), 0) AS valor
        FROM shopee_saques
        WHERE date(data_saque) BETWEEN date(?) AND date(?)
        GROUP BY date(data_saque)
        """,
        (start, end),
    ):
        if row["data"] in rows_by_date:
            rows_by_date[row["data"]]["saque"] = float(row["valor"] or 0)

    for row in fetch_all(
        """
        SELECT date(data) AS data, COALESCE(SUM(valor), 0) AS valor
        FROM despesas
        WHERE date(data) BETWEEN date(?) AND date(?)
        GROUP BY date(data)
        """,
        (start, end),
    ):
        if row["data"] in rows_by_date:
            rows_by_date[row["data"]]["despesa"] = float(row["valor"] or 0)

    saldo_disponivel = float(summary.get("disponibilidades") or 0)
    saldo_total = float(summary.get("total_dinheiro_gerencial") or 0)

    result = []
    for day in _date_range(start, end):
        row = rows_by_date[day]
        # Envio previsto apenas muda de Aberto futuro para Shopee em espera.
        # Entrada Shopee e saque não alteram total gerencial; despesa reduz total e disponibilidade.
        saldo_disponivel += float(row["entrada_shopee"] or 0) - float(row["despesa"] or 0)
        saldo_total -= float(row["despesa"] or 0)
        row["saldo_disponivel"] = saldo_disponivel
        row["saldo_total_gerencial"] = saldo_total
        result.append(row)
    return result


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
            date(COALESCE(NULLIF(data_prevista_envio, ''), NULLIF(data_criacao, ''), '1900-01-01')) AS data,
            'Aberto futuro' AS tipo,
            pedido_id AS referencia,
            'Pedido aberto sem rastreio / a enviar' AS descricao,
            valor_liquido_estimado AS entrada,
            0 AS saida,
            status_financeiro AS status
        FROM shopee_pedidos_financeiros
        WHERE (numero_rastreio IS NULL OR TRIM(numero_rastreio) = '')
          AND status_financeiro = 'em_aberto'
          AND date(COALESCE(NULLIF(data_prevista_envio, ''), NULLIF(data_criacao, ''), '1900-01-01'))
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
        (start, end, start, end, start, end, start, end, start, end, limit),
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
           OR status_financeiro IN ('em_aberto', 'em_espera')
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
