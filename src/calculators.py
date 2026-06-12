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


def calculate_sale_profit(
    faturamento: float,
    unidades: int,
    imposto_percentual: float,
    comissao_percentual: float,
    taxa_fixa_unitaria: float,
    custo_unitario: float | None,
) -> SaleCalculation:
    imposto_valor = faturamento * (imposto_percentual / 100)
    comissao_valor = faturamento * (comissao_percentual / 100)
    taxa_fixa_valor = unidades * taxa_fixa_unitaria

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
    )


def calculate_margin(lucro_final: float, faturamento: float) -> float:
    if faturamento <= 0:
        return 0.0
    return (lucro_final / faturamento) * 100
