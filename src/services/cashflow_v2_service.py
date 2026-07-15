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
            ) VALUES (?, ?, ?, ?, 'marco zero ativo', ?, ?)
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


def _date_range(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    last = date.fromisoformat(end)
    days = []
    while current <= last:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _day_before(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def _positive(value: float) -> float:
    return value if value > 0 else 0.0


def _order_date_expression() -> str:
    return "date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao))"


def _open_order_date_expression(default_date: str = "1900-01-01") -> str:
    return f"date(COALESCE(NULLIF(data_prevista_envio, ''), NULLIF(data_criacao, ''), '{default_date}'))"


def _query_orders_tracked(balance_start: str, balance_end: str) -> dict:
    return fetch_one(
        f"""
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
          AND status_financeiro <> 'cancelado'
          AND {_order_date_expression()} BETWEEN date(?) AND date(?)
        """,
        (balance_start, balance_end),
    ) or {}


def _query_orders_tracked_month(month_start: str, month_end: str) -> dict:
    return fetch_one(
        f"""
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
          AND {_order_date_expression()} BETWEEN date(?) AND date(?)
        """,
        (month_start, month_end),
    ) or {}


def _query_open_orders() -> dict:
    return fetch_one(
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


def _query_shopee_movements(start: str, end: str) -> dict:
    return fetch_one(
        """
        SELECT
            COALESCE(SUM(CASE WHEN LOWER(t.direcao) = 'entrada' THEN t.valor ELSE 0 END), 0) AS entradas_totais,
            COALESCE(SUM(CASE WHEN LOWER(t.direcao) <> 'entrada'
                               AND LOWER(t.tipo_transacao) NOT LIKE '%saque%'
                              THEN ABS(t.valor) ELSE 0 END), 0) AS debitos_saldo_shopee,
            COALESCE(SUM(CASE WHEN t.pedido_id IS NOT NULL AND TRIM(t.pedido_id) <> ''
                               AND LOWER(t.direcao) = 'entrada'
                              THEN t.valor ELSE 0 END), 0) AS pagamentos_pedidos,
            COALESCE(SUM(CASE WHEN t.pedido_id IS NOT NULL AND TRIM(t.pedido_id) <> ''
                               AND p.pedido_id IS NULL
                               AND LOWER(t.direcao) = 'entrada'
                              THEN t.valor ELSE 0 END), 0) AS pagamentos_sem_cadastro,
            COALESCE(SUM(CASE WHEN (t.pedido_id IS NULL OR TRIM(t.pedido_id) = '')
                               AND LOWER(t.direcao) = 'entrada'
                              THEN t.valor ELSE 0 END), 0) AS pagamentos_sem_pedido,
            COALESCE(AVG(
                CASE
                    WHEN p.data_envio_real IS NOT NULL AND p.data_envio_real <> ''
                    THEN julianday(t.data_movimento) - julianday(p.data_envio_real)
                END
            ), 0) AS tempo_liberacao_medio
        FROM shopee_transacoes t
        LEFT JOIN shopee_pedidos_financeiros p ON p.pedido_id = t.pedido_id
        WHERE date(t.data_movimento) BETWEEN date(?) AND date(?)
        """,
        (start, end),
    ) or {}


def _query_saques(start: str, end: str) -> float:
    row = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS total
        FROM shopee_saques
        WHERE date(data_saque) BETWEEN date(?) AND date(?)
        """,
        (start, end),
    ) or {}
    return float(row.get("total") or 0)


def _query_despesas(start: str, end: str) -> float:
    row = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS total
        FROM despesas
        WHERE date(data) BETWEEN date(?) AND date(?)
        """,
        (start, end),
    ) or {}
    return float(row.get("total") or 0)


def _query_latest_shopee_balance(as_of: str) -> dict:
    return fetch_one(
        """
        SELECT data_movimento, balanca_apos_transacoes
        FROM shopee_transacoes
        WHERE date(data_movimento) <= date(?)
        ORDER BY datetime(data_movimento) DESC, id DESC
        LIMIT 1
        """,
        (as_of,),
    ) or {}


def _calculate_snapshot(as_of: str, visual_start: str | None = None, visual_end: str | None = None) -> dict:
    initial = get_initial_position()
    balance_start = _balance_start(initial)
    initial_bank = float((initial or {}).get("saldo_banco") or 0)
    initial_shopee_cash = float((initial or {}).get("saldo_shopee_disponivel") or 0)
    initial_shopee_waiting = float((initial or {}).get("saldo_shopee_espera") or 0)

    tracked_balance = _query_orders_tracked(balance_start, as_of)
    open_orders = _query_open_orders()
    shopee_movements = _query_shopee_movements(balance_start, as_of)
    saques_acumulados = _query_saques(balance_start, as_of)
    despesas_acumuladas = _query_despesas(balance_start, as_of)
    latest_balance = _query_latest_shopee_balance(as_of)

    tracked_liquido_acumulado = float(tracked_balance.get("liquido_estimado") or 0)
    entradas_acumuladas = float(shopee_movements.get("entradas_totais") or 0)
    debitos_shopee_acumulado = float(shopee_movements.get("debitos_saldo_shopee") or 0)

    shopee_em_espera = _positive(initial_shopee_waiting + tracked_liquido_acumulado - entradas_acumuladas)
    shopee_caixa = initial_shopee_cash + entradas_acumuladas - debitos_shopee_acumulado - saques_acumulados
    banco = initial_bank + saques_acumulados - despesas_acumuladas
    saldo_possivel_aberto = float(open_orders.get("saldo_possivel_aberto") or 0)
    disponibilidades = banco + shopee_caixa
    total_gerencial = disponibilidades + shopee_em_espera + saldo_possivel_aberto

    month_orders = _query_orders_tracked_month(visual_start or balance_start, visual_end or as_of)
    month_movements = _query_shopee_movements(visual_start or balance_start, visual_end or as_of)
    month_saques = _query_saques(visual_start or balance_start, visual_end or as_of)
    month_despesas = _query_despesas(visual_start or balance_start, visual_end or as_of)

    valor_bruto = float(month_orders.get("valor_bruto") or 0)
    imposto_percentual = get_setting_float("imposto_percentual", 9)
    imposto_reservado = valor_bruto * imposto_percentual / 100
    taxa_total = (
        float(month_orders.get("comissao") or 0)
        + float(month_orders.get("taxa_servico") or 0)
        + float(month_orders.get("taxa_transacao") or 0)
    )
    pedidos_mes = int(month_orders.get("pedidos") or 0)
    saldo_oficial_raw = latest_balance.get("balanca_apos_transacoes")
    saldo_oficial = float(saldo_oficial_raw or 0)
    has_oficial = saldo_oficial_raw is not None and str(saldo_oficial_raw) != ""

    return {
        "data_corte": (initial or {}).get("data_corte", ""),
        "balance_start": balance_start,
        "as_of": as_of,
        "saldo_banco": banco,
        "saldo_shopee_disponivel": shopee_caixa,
        "saldo_shopee_espera": shopee_em_espera,
        "saldo_shopee_espera_inicial": initial_shopee_waiting,
        "tracked_liquido_acumulado": tracked_liquido_acumulado,
        "abatimento_espera": entradas_acumuladas,
        "saldo_possivel_aberto": saldo_possivel_aberto,
        "valor_bruto_aberto": float(open_orders.get("valor_bruto_aberto") or 0),
        "pedidos_em_aberto": int(open_orders.get("pedidos_em_aberto") or 0),
        "disponibilidades": disponibilidades,
        "caixa_disponivel": disponibilidades,
        "total_dinheiro_gerencial": total_gerencial,
        "caixa_livre_estimado": disponibilidades - imposto_reservado,
        "entradas_acumuladas": entradas_acumuladas,
        "debitos_shopee_acumulado": debitos_shopee_acumulado,
        "saques_acumulados": saques_acumulados,
        "despesas_acumuladas": despesas_acumuladas,
        "saldo_shopee_relatorio": saldo_oficial if has_oficial else 0,
        "saldo_shopee_calculado": shopee_caixa,
        "diferenca_caixa_shopee": (saldo_oficial - shopee_caixa) if has_oficial else 0,
        "data_saldo_shopee": latest_balance.get("data_movimento", ""),
        "pedidos": pedidos_mes,
        "valor_bruto": valor_bruto,
        "liquido_estimado": float(month_orders.get("liquido_estimado") or 0),
        "taxa_total": taxa_total,
        "taxa_total_percentual": (taxa_total / valor_bruto * 100) if valor_bruto else 0,
        "imposto_reservado": imposto_reservado,
        "entradas_shopee": float(month_movements.get("entradas_totais") or 0),
        "debitos_shopee": float(month_movements.get("debitos_saldo_shopee") or 0),
        "saques": month_saques,
        "despesas": month_despesas,
        "pagamentos_pedidos": float(shopee_movements.get("pagamentos_pedidos") or 0),
        "pagamentos_sem_pedido": float(shopee_movements.get("pagamentos_sem_pedido") or 0),
        "pagamentos_sem_cadastro": float(shopee_movements.get("pagamentos_sem_cadastro") or 0),
        "tempo_liberacao_medio": float(shopee_movements.get("tempo_liberacao_medio") or 0),
        "prazo_envio_medio": float(month_orders.get("prazo_envio_medio") or 0),
        "comissao_media": (float(month_orders.get("comissao") or 0) / pedidos_mes) if pedidos_mes else 0,
        "ticket_medio_bruto": (valor_bruto / pedidos_mes) if pedidos_mes else 0,
        "ticket_medio_liquido": (float(month_orders.get("liquido_estimado") or 0) / pedidos_mes) if pedidos_mes else 0,
        "imposto_percentual": imposto_percentual,
    }


def get_cashflow_summary(mes_referencia: str) -> dict:
    month_start, month_end = month_bounds(mes_referencia)
    summary = _calculate_snapshot(month_end, month_start, month_end)
    summary["periodo_inicio"] = month_start
    summary["periodo_fim"] = month_end
    return summary


def list_cashflow_audit(mes_referencia: str) -> list[dict]:
    summary = get_cashflow_summary(mes_referencia)
    return [
        {
            "grupo": "Regra mestre",
            "item": "Shopee em espera",
            "valor": summary.get("saldo_shopee_espera"),
            "obs": "espera inicial + pedidos com rastreio - entradas de pedidos pagos",
            "tipo": "money",
        },
        {
            "grupo": "Regra mestre",
            "item": "Caixa Shopee calculado",
            "valor": summary.get("saldo_shopee_calculado"),
            "obs": "caixa Shopee inicial + entradas - débitos Shopee - saques",
            "tipo": "money",
        },
        {
            "grupo": "Regra mestre",
            "item": "Banco calculado",
            "valor": summary.get("saldo_banco"),
            "obs": "banco inicial + saques Shopee - despesas cadastradas",
            "tipo": "money",
        },
        {
            "grupo": "Em espera",
            "item": "Espera inicial",
            "valor": summary.get("saldo_shopee_espera_inicial"),
            "obs": "valor informado no marco zero",
            "tipo": "money",
        },
        {
            "grupo": "Em espera",
            "item": "Pedidos com rastreio acumulados",
            "valor": summary.get("tracked_liquido_acumulado"),
            "obs": "entraram na espera desde o marco zero",
            "tipo": "money",
        },
        {
            "grupo": "Em espera",
            "item": "Pagamentos abatidos",
            "valor": summary.get("abatimento_espera"),
            "obs": "entradas do my balance desde o marco zero",
            "tipo": "money",
        },
        {
            "grupo": "Carteira Shopee",
            "item": "Saldo oficial Shopee",
            "valor": summary.get("saldo_shopee_relatorio"),
            "obs": f"saldo do relatório para conferência; última data: {summary.get('data_saldo_shopee') or '-'}",
            "tipo": "money",
        },
        {
            "grupo": "Carteira Shopee",
            "item": "Diferença oficial x calculado",
            "valor": summary.get("diferenca_caixa_shopee"),
            "obs": "diferença indica marco zero errado, planilha faltando ou movimento não importado",
            "tipo": "money",
        },
        {
            "grupo": "Banco",
            "item": "Saques acumulados",
            "valor": summary.get("saques_acumulados"),
            "obs": "saques Shopee somados ao banco desde o marco zero",
            "tipo": "money",
        },
        {
            "grupo": "Banco",
            "item": "Despesas acumuladas",
            "valor": summary.get("despesas_acumuladas"),
            "obs": "todas as saídas cadastradas reduzem banco, entrando ou não no DRE",
            "tipo": "money",
        },
    ]


def _daily_values(start: str, end: str) -> dict[str, dict]:
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
        f"""
        SELECT {_open_order_date_expression(start)} AS data,
               COALESCE(SUM(valor_liquido_estimado), 0) AS valor
        FROM shopee_pedidos_financeiros
        WHERE (numero_rastreio IS NULL OR TRIM(numero_rastreio) = '')
          AND status_financeiro = 'em_aberto'
          AND {_open_order_date_expression(start)} BETWEEN date(?) AND date(?)
        GROUP BY {_open_order_date_expression(start)}
        """,
        (start, end),
    ):
        if row["data"] in rows_by_date:
            rows_by_date[row["data"]]["envio_previsto"] = float(row["valor"] or 0)

    for row in fetch_all(
        """
        SELECT date(data_movimento) AS data,
               COALESCE(SUM(CASE WHEN LOWER(direcao) = 'entrada' THEN valor ELSE 0 END), 0) AS entradas,
               COALESCE(SUM(CASE WHEN LOWER(direcao) <> 'entrada'
                                  AND LOWER(tipo_transacao) NOT LIKE '%saque%'
                                 THEN ABS(valor) ELSE 0 END), 0) AS debitos
        FROM shopee_transacoes
        WHERE date(data_movimento) BETWEEN date(?) AND date(?)
        GROUP BY date(data_movimento)
        """,
        (start, end),
    ):
        if row["data"] in rows_by_date:
            rows_by_date[row["data"]]["entrada_shopee"] = float(row["entradas"] or 0)
            rows_by_date[row["data"]]["despesa"] += float(row["debitos"] or 0)

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
            rows_by_date[row["data"]]["despesa"] += float(row["valor"] or 0)

    return rows_by_date


def list_daily_cashflow_forecast(mes_referencia: str) -> list[dict]:
    start, end = month_bounds(mes_referencia)
    initial_snapshot = _calculate_snapshot(_day_before(start), start, end)
    saldo_disponivel = float(initial_snapshot.get("disponibilidades") or 0)
    saldo_total = float(initial_snapshot.get("total_dinheiro_gerencial") or 0)
    rows_by_date = _daily_values(start, end)

    result = []
    for day in _date_range(start, end):
        row = rows_by_date[day]
        entrada_shopee = float(row["entrada_shopee"] or 0)
        despesas_e_debitos = float(row["despesa"] or 0)
        # Envio previsto muda aberto futuro → espera, mas não muda dinheiro total.
        # Entrada Shopee muda espera → caixa Shopee, aumentando disponibilidade mas não total gerencial.
        # Saque muda caixa Shopee → banco, sem alterar disponibilidade.
        # Despesa/débito reduz disponibilidade e total gerencial.
        saldo_disponivel += entrada_shopee - despesas_e_debitos
        saldo_total -= despesas_e_debitos
        row["saldo_disponivel"] = saldo_disponivel
        row["saldo_total_gerencial"] = saldo_total
        result.append(row)
    return result


def list_cashflow_events(mes_referencia: str, limit: int = 200) -> list[dict]:
    start, end = month_bounds(mes_referencia)
    return fetch_all(
        f"""
        SELECT {_order_date_expression()} AS data,
               'Pedido com rastreio' AS tipo,
               pedido_id AS referencia,
               'Entra em Shopee em espera' AS descricao,
               valor_liquido_estimado AS entrada,
               0 AS saida,
               status_financeiro AS status
        FROM shopee_pedidos_financeiros
        WHERE numero_rastreio IS NOT NULL
          AND TRIM(numero_rastreio) <> ''
          AND status_financeiro <> 'cancelado'
          AND {_order_date_expression()} BETWEEN date(?) AND date(?)

        UNION ALL

        SELECT {_open_order_date_expression()} AS data,
               'Aberto futuro' AS tipo,
               pedido_id AS referencia,
               'Pedido sem rastreio / a enviar' AS descricao,
               valor_liquido_estimado AS entrada,
               0 AS saida,
               status_financeiro AS status
        FROM shopee_pedidos_financeiros
        WHERE (numero_rastreio IS NULL OR TRIM(numero_rastreio) = '')
          AND status_financeiro = 'em_aberto'
          AND {_open_order_date_expression()} BETWEEN date(?) AND date(?)

        UNION ALL

        SELECT date(data_movimento) AS data,
               'Entrada Shopee' AS tipo,
               COALESCE(pedido_id, '') AS referencia,
               tipo_transacao AS descricao,
               CASE WHEN LOWER(direcao) = 'entrada' THEN valor ELSE 0 END AS entrada,
               CASE WHEN LOWER(direcao) <> 'entrada' AND LOWER(tipo_transacao) NOT LIKE '%saque%' THEN ABS(valor) ELSE 0 END AS saida,
               status_conciliacao AS status
        FROM shopee_transacoes
        WHERE date(data_movimento) BETWEEN date(?) AND date(?)
          AND LOWER(tipo_transacao) NOT LIKE '%saque%'

        UNION ALL

        SELECT date(data_saque) AS data,
               'Transferência' AS tipo,
               'Shopee para Banco' AS referencia,
               'Saque da Shopee para conta bancária' AS descricao,
               valor AS entrada,
               0 AS saida,
               status AS status
        FROM shopee_saques
        WHERE date(data_saque) BETWEEN date(?) AND date(?)

        UNION ALL

        SELECT data AS data,
               'Despesa / saída' AS tipo,
               categoria AS referencia,
               descricao AS descricao,
               0 AS entrada,
               valor AS saida,
               CASE WHEN COALESCE(incide_dre, 1) = 1 THEN 'DRE + caixa' ELSE 'Só caixa' END AS status
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
        f"""
        SELECT
            pedido_id,
            numero_rastreio,
            {_order_date_expression()} AS data_envio,
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
        WHERE {_order_date_expression()} BETWEEN date(?) AND date(?)
           OR status_financeiro IN ('em_aberto', 'em_espera')
        ORDER BY
            CASE status_financeiro
                WHEN 'divergente' THEN 0
                WHEN 'em_espera' THEN 1
                WHEN 'em_aberto' THEN 2
                ELSE 3
            END,
            {_order_date_expression()} ASC
        LIMIT ?
        """,
        (start, end, limit),
    )
