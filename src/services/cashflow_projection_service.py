from datetime import date, datetime, timedelta
from collections import defaultdict

from src.database import fetch_all
from src.services.cashflow_service import get_cashflow_summary, month_bounds
from src.services.settings_service import get_setting_float


def _parse_date(value: object, fallback: date) -> date:
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        return datetime.fromisoformat(text[:19]).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return fallback


def _month_dates(month_start: str, month_end: str) -> list[date]:
    start = date.fromisoformat(month_start)
    end = date.fromisoformat(month_end)
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def list_cashflow_projection(mes_referencia: str, limit_days: int = 62) -> list[dict]:
    """Projeção gerencial diária do fluxo.

    A projeção usa:
    - saldo atual calculado no painel;
    - pedidos em aberto/em espera como entradas previstas;
    - entradas reais Shopee do relatório de pagamentos;
    - saques como transferência para banco;
    - despesas lançadas como saída.

    Como a Shopee não informa a data futura exata de liberação no relatório de pedidos,
    usamos uma estimativa configurável. Padrão: 14 dias após envio/previsão de envio.
    """
    month_start, month_end = month_bounds(mes_referencia)
    summary = get_cashflow_summary(mes_referencia)
    dias_liberacao = int(get_setting_float("dias_liberacao_shopee", 14) or 14)

    days = _month_dates(month_start, month_end)[:limit_days]
    if not days:
        return []

    projection_start = days[0]
    today = date.today()
    if days[0] <= today <= days[-1]:
        projection_start = today

    entradas_previstas = defaultdict(float)
    entradas_previstas_aberto = defaultdict(float)
    entradas_previstas_espera = defaultdict(float)
    entradas_reais = defaultdict(float)
    saques = defaultdict(float)
    despesas = defaultdict(float)

    orders = fetch_all(
        """
        SELECT
            pedido_id,
            status_financeiro,
            numero_rastreio,
            valor_liquido_estimado,
            data_envio_real,
            data_prevista_envio,
            data_criacao
        FROM shopee_pedidos_financeiros
        WHERE status_financeiro IN ('em_aberto', 'em_espera')
          AND valor_liquido_estimado > 0
        """
    )

    for order in orders:
        base = _parse_date(
            order.get("data_envio_real")
            or order.get("data_prevista_envio")
            or order.get("data_criacao"),
            projection_start,
        )
        expected = base + timedelta(days=dias_liberacao)
        if expected < projection_start:
            expected = projection_start
        if expected > days[-1]:
            expected = days[-1]

        value = float(order.get("valor_liquido_estimado") or 0)
        entradas_previstas[expected] += value
        if order.get("status_financeiro") == "em_aberto":
            entradas_previstas_aberto[expected] += value
        else:
            entradas_previstas_espera[expected] += value

    payment_rows = fetch_all(
        """
        SELECT date(data_movimento) AS data, COALESCE(SUM(valor), 0) AS total
        FROM shopee_transacoes
        WHERE LOWER(direcao) = 'entrada'
          AND date(data_movimento) BETWEEN date(?) AND date(?)
        GROUP BY date(data_movimento)
        """,
        (month_start, month_end),
    )
    for row in payment_rows:
        entradas_reais[date.fromisoformat(row["data"])] += float(row.get("total") or 0)

    saque_rows = fetch_all(
        """
        SELECT date(data_saque) AS data, COALESCE(SUM(valor), 0) AS total
        FROM shopee_saques
        WHERE date(data_saque) BETWEEN date(?) AND date(?)
        GROUP BY date(data_saque)
        """,
        (month_start, month_end),
    )
    for row in saque_rows:
        saques[date.fromisoformat(row["data"])] += float(row.get("total") or 0)

    despesa_rows = fetch_all(
        """
        SELECT date(data) AS data, COALESCE(SUM(valor), 0) AS total
        FROM despesas
        WHERE date(data) BETWEEN date(?) AND date(?)
        GROUP BY date(data)
        """,
        (month_start, month_end),
    )
    for row in despesa_rows:
        despesas[date.fromisoformat(row["data"])] += float(row.get("total") or 0)

    banco = float(summary.get("saldo_banco") or 0)
    caixa_shopee = float(summary.get("saldo_shopee_disponivel") or 0)
    espera = float(summary.get("saldo_shopee_espera") or 0)
    aberto = float(summary.get("saldo_possivel_aberto") or 0)
    imposto_reservado = float(summary.get("imposto_reservado") or 0)

    rows = []
    for day in days:
        prevista = entradas_previstas[day]
        prevista_aberto = entradas_previstas_aberto[day]
        prevista_espera = entradas_previstas_espera[day]
        real = entradas_reais[day]
        saque = saques[day]
        despesa = despesas[day]

        if day >= projection_start:
            caixa_shopee += prevista + real - saque
            banco += saque - despesa
            aberto = max(0, aberto - prevista_aberto)
            espera = max(0, espera - prevista_espera - real)

        caixa_disponivel = banco + caixa_shopee
        caixa_livre = caixa_disponivel - imposto_reservado
        entrada_total = prevista + real
        saida_total = despesa
        net = entrada_total - saida_total

        rows.append(
            {
                "data": day.isoformat(),
                "entrada_prevista": prevista,
                "entrada_real": real,
                "saida": saida_total,
                "saque": saque,
                "saldo_banco": banco,
                "saldo_shopee": caixa_shopee,
                "saldo_espera": espera,
                "saldo_aberto": aberto,
                "caixa_disponivel": caixa_disponivel,
                "caixa_livre": caixa_livre,
                "grafico": _mini_bar(net, caixa_livre),
            }
        )

    return rows


def _mini_bar(net: float, saldo: float) -> str:
    signal = "↑" if net >= 0 else "↓"
    blocks = max(1, min(12, int(abs(net) // 250) + 1)) if net else 1
    return f"{signal} {'█' * blocks}  saldo {saldo:,.0f}".replace(",", ".")
