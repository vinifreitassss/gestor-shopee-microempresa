from src.database import fetch_all, fetch_one
from src.services.reports_service import current_month_reference
from src.services.settings_service import get_setting_float


def get_shopee_fees_summary(mes_referencia: str | None = None) -> dict:
    month = mes_referencia or current_month_reference()
    pedidos = fetch_one(
        """
        SELECT
            COUNT(*) AS pedidos,
            COALESCE(SUM(valor_total), 0) AS valor_total,
            COALESCE(SUM(total_global), 0) AS total_global,
            COALESCE(SUM(taxa_transacao), 0) AS taxa_transacao,
            COALESCE(SUM(comissao_bruta), 0) AS comissao_bruta,
            COALESCE(SUM(comissao_liquida), 0) AS comissao_liquida,
            COALESCE(SUM(taxa_servico_bruta), 0) AS taxa_servico_bruta,
            COALESCE(SUM(taxa_servico_liquida), 0) AS taxa_servico_liquida,
            COALESCE(SUM(valor_liquido_estimado), 0) AS liquido_estimado,
            COALESCE(SUM(valor_pago_real), 0) AS valor_pago_real,
            COALESCE(SUM(diferenca), 0) AS diferenca_total
        FROM shopee_pedidos_financeiros
        WHERE status_financeiro <> 'cancelado'
          AND substr(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao), 1, 7) = ?
        """,
        (month,),
    ) or {}

    carteira = fetch_one(
        """
        SELECT
            COALESCE(SUM(CASE WHEN LOWER(tipo_transacao || ' ' || descricao) LIKE '%ads%'
                              THEN ABS(valor) ELSE 0 END), 0) AS shopee_ads,
            COALESCE(SUM(CASE WHEN LOWER(tipo_transacao) NOT LIKE '%saque%'
                               AND LOWER(direcao) <> 'entrada'
                               AND LOWER(tipo_transacao || ' ' || descricao) NOT LIKE '%ads%'
                              THEN ABS(valor) ELSE 0 END), 0) AS ajustes_descontos,
            COALESCE(SUM(CASE WHEN LOWER(direcao) = 'entrada' THEN valor ELSE 0 END), 0) AS entradas_carteira
        FROM shopee_transacoes
        WHERE substr(data_movimento, 1, 7) = ?
        """,
        (month,),
    ) or {}

    aliquota = get_setting_float("imposto_percentual", 7)
    valor_total = float(pedidos.get("valor_total") or 0)
    total_global = float(pedidos.get("total_global") or 0)
    faturamento_bruto = total_global if total_global else valor_total
    taxa_transacao = float(pedidos.get("taxa_transacao") or 0)
    comissao_liquida = float(pedidos.get("comissao_liquida") or 0)
    taxa_servico_liquida = float(pedidos.get("taxa_servico_liquida") or 0)
    shopee_ads = float(carteira.get("shopee_ads") or 0)
    ajustes_descontos = float(carteira.get("ajustes_descontos") or 0)
    total_taxas_pedidos = taxa_transacao + comissao_liquida + taxa_servico_liquida
    total_shopee = total_taxas_pedidos + shopee_ads + ajustes_descontos
    base_liquida_sem_ads = max(faturamento_bruto - total_taxas_pedidos, 0)
    base_liquida_com_ads = max(faturamento_bruto - total_shopee, 0)
    imposto_bruto = faturamento_bruto * aliquota / 100
    imposto_liquido_sem_ads = base_liquida_sem_ads * aliquota / 100
    imposto_liquido_com_ads = base_liquida_com_ads * aliquota / 100

    return {
        "mes_referencia": month,
        "aliquota": aliquota,
        "pedidos": int(pedidos.get("pedidos") or 0),
        "faturamento_bruto": faturamento_bruto,
        "valor_total": valor_total,
        "total_global": total_global,
        "taxa_transacao": taxa_transacao,
        "comissao_bruta": float(pedidos.get("comissao_bruta") or 0),
        "comissao_liquida": comissao_liquida,
        "taxa_servico_bruta": float(pedidos.get("taxa_servico_bruta") or 0),
        "taxa_servico_liquida": taxa_servico_liquida,
        "total_taxas_pedidos": total_taxas_pedidos,
        "shopee_ads": shopee_ads,
        "ajustes_descontos": ajustes_descontos,
        "total_shopee": total_shopee,
        "liquido_estimado": float(pedidos.get("liquido_estimado") or 0),
        "valor_pago_real": float(pedidos.get("valor_pago_real") or 0),
        "diferenca_total": float(pedidos.get("diferenca_total") or 0),
        "entradas_carteira": float(carteira.get("entradas_carteira") or 0),
        "base_bruta_conservadora": faturamento_bruto,
        "base_liquida_sem_ads": base_liquida_sem_ads,
        "base_liquida_com_ads": base_liquida_com_ads,
        "imposto_bruto": imposto_bruto,
        "imposto_liquido_sem_ads": imposto_liquido_sem_ads,
        "imposto_liquido_com_ads": imposto_liquido_com_ads,
        "economia_sem_ads": imposto_bruto - imposto_liquido_sem_ads,
        "economia_com_ads": imposto_bruto - imposto_liquido_com_ads,
        "percentual_taxas_sobre_bruto": (total_taxas_pedidos / faturamento_bruto * 100) if faturamento_bruto else 0,
        "percentual_total_shopee_sobre_bruto": (total_shopee / faturamento_bruto * 100) if faturamento_bruto else 0,
        "ticket_medio_bruto": (faturamento_bruto / int(pedidos.get("pedidos") or 0)) if int(pedidos.get("pedidos") or 0) else 0,
        "taxa_media_pedido": (total_taxas_pedidos / int(pedidos.get("pedidos") or 0)) if int(pedidos.get("pedidos") or 0) else 0,
    }


def list_shopee_fees_by_order(mes_referencia: str | None = None, limit: int = 300) -> list[dict]:
    month = mes_referencia or current_month_reference()
    rows = fetch_all(
        """
        SELECT
            pedido_id,
            status_financeiro,
            date(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao)) AS data_base,
            valor_total,
            total_global,
            taxa_transacao,
            comissao_liquida,
            taxa_servico_liquida,
            (taxa_transacao + comissao_liquida + taxa_servico_liquida) AS total_taxas,
            valor_liquido_estimado,
            valor_pago_real,
            diferenca
        FROM shopee_pedidos_financeiros
        WHERE status_financeiro <> 'cancelado'
          AND substr(COALESCE(NULLIF(data_envio_real, ''), NULLIF(data_prevista_envio, ''), data_criacao), 1, 7) = ?
        ORDER BY total_taxas DESC, data_base DESC
        LIMIT ?
        """,
        (month, limit),
    )
    for row in rows:
        bruto = float(row.get("total_global") or row.get("valor_total") or 0)
        total_taxas = float(row.get("total_taxas") or 0)
        row["percentual_taxas"] = total_taxas / bruto * 100 if bruto else 0
    return rows


def list_shopee_fees_breakdown(mes_referencia: str | None = None) -> list[dict]:
    summary = get_shopee_fees_summary(mes_referencia)
    return [
        {"grupo": "Taxas por pedido", "item": "Taxa de transação", "valor": summary["taxa_transacao"]},
        {"grupo": "Taxas por pedido", "item": "Comissão Shopee líquida", "valor": summary["comissao_liquida"]},
        {"grupo": "Taxas por pedido", "item": "Taxa de serviço líquida", "valor": summary["taxa_servico_liquida"]},
        {"grupo": "Carteira Shopee", "item": "Shopee Ads", "valor": summary["shopee_ads"]},
        {"grupo": "Carteira Shopee", "item": "Ajustes/descontos/reembolsos", "valor": summary["ajustes_descontos"]},
        {"grupo": "Total", "item": "Total cobrado/retido pela Shopee", "valor": summary["total_shopee"]},
    ]


def list_tax_base_scenarios(mes_referencia: str | None = None) -> list[dict]:
    summary = get_shopee_fees_summary(mes_referencia)
    return [
        {
            "cenario": "Conservador / fiscal bruto",
            "base": summary["base_bruta_conservadora"],
            "imposto": summary["imposto_bruto"],
            "economia": 0,
            "obs": "Base sobre faturamento bruto. Mais conservador para Simples Nacional.",
        },
        {
            "cenario": "Líquido pós-taxas de pedido",
            "base": summary["base_liquida_sem_ads"],
            "imposto": summary["imposto_liquido_sem_ads"],
            "economia": summary["economia_sem_ads"],
            "obs": "Simulação: bruto menos taxa de transação, comissão e taxa de serviço.",
        },
        {
            "cenario": "Líquido pós-Shopee total",
            "base": summary["base_liquida_com_ads"],
            "imposto": summary["imposto_liquido_com_ads"],
            "economia": summary["economia_com_ads"],
            "obs": "Simulação gerencial: também abate Ads e ajustes da carteira.",
        },
    ]
