from dataclasses import dataclass


@dataclass
class SaleCalculation:
    faturamento: float
    unidades: int
    imposto_percentual: float
    comissao_percentual: float
    taxa_fixa_unitaria: float
    custo_unitario: float | None
    imposto_valor: float
    comissao_valor: float
    taxa_fixa_valor: float
    custo_total: float | None
    lucro: float | None
    lucro_incompleto: bool
    quantidade_taxa_fixa: int = 0


def calculate_sale_profit(
    faturamento: float,
    unidades: int,
    imposto_percentual: float,
    comissao_percentual: float,
    taxa_fixa_unitaria: float,
    custo_unitario: float | None,
    quantidade_taxa_fixa: int | None = None,
) -> SaleCalculation:
    """Calcula o resultado de uma venda.

    unidades = quantidade de unidades para CMV.
    quantidade_taxa_fixa = base da taxa fixa (pedidos, unidades etc.).
    Mantemos unidades como fallback para preservar a regra antiga da Shopee.
    """
    unidades = int(unidades or 0)
    quantidade_taxa_fixa = unidades if quantidade_taxa_fixa is None else int(quantidade_taxa_fixa or 0)
    imposto_valor = faturamento * (imposto_percentual / 100)
    comissao_valor = faturamento * (comissao_percentual / 100)
    taxa_fixa_valor = quantidade_taxa_fixa * taxa_fixa_unitaria

    if custo_unitario is None:
        return SaleCalculation(
            faturamento=faturamento,
            unidades=unidades,
            imposto_percentual=imposto_percentual,
            comissao_percentual=comissao_percentual,
            taxa_fixa_unitaria=taxa_fixa_unitaria,
            custo_unitario=None,
            imposto_valor=imposto_valor,
            comissao_valor=comissao_valor,
            taxa_fixa_valor=taxa_fixa_valor,
            custo_total=None,
            lucro=None,
            lucro_incompleto=True,
            quantidade_taxa_fixa=quantidade_taxa_fixa,
        )

    custo_total = unidades * custo_unitario
    lucro = faturamento - imposto_valor - comissao_valor - taxa_fixa_valor - custo_total
    return SaleCalculation(
        faturamento=faturamento,
        unidades=unidades,
        imposto_percentual=imposto_percentual,
        comissao_percentual=comissao_percentual,
        taxa_fixa_unitaria=taxa_fixa_unitaria,
        custo_unitario=custo_unitario,
        imposto_valor=imposto_valor,
        comissao_valor=comissao_valor,
        taxa_fixa_valor=taxa_fixa_valor,
        custo_total=custo_total,
        lucro=lucro,
        lucro_incompleto=False,
        quantidade_taxa_fixa=quantidade_taxa_fixa,
    )


def calculate_margin(lucro_final: float, faturamento: float) -> float:
    if faturamento <= 0:
        return 0.0
    return (lucro_final / faturamento) * 100
