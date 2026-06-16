import customtkinter as ctk

from src.services.products_service import list_variations_with_sales_metrics
from src.services.reports_service import current_month_reference
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, percent


class ProductsView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.month_var = ctk.StringVar(value=current_month_reference())
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Produtos e Variações", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Produto pai é usado para agrupamento. Variação é usada para cálculo real de venda, custo e lucro.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        controls = ctk.CTkFrame(self)
        controls.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(controls, text="Mês de análise:").pack(side="left", padx=8, pady=8)
        ctk.CTkEntry(controls, textvariable=self.month_var, width=90).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(controls, text="Atualizar", command=self.refresh).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(
            controls,
            text="Cupom máx. é uma referência aproximada baseada no lucro por unidade do mês.",
            text_color="gray",
        ).pack(side="left", padx=16, pady=8)

        self.table = SimpleTable(
            self,
            [
                ("id", "ID", 55),
                ("produto_pai", "Produto pai", 250),
                ("nome_variacao", "Variação", 210),
                ("sku", "SKU", 90),
                ("custo_unitario", "Custo atual", 95),
                ("preco_medio_vendido", "Preço vendido", 105),
                ("unidades_vendidas", "Unid.", 65),
                ("faturamento", "Faturamento", 105),
                ("lucro", "Lucro", 100),
                ("margem", "Margem", 80),
                ("lucro_por_unidade", "Lucro/un.", 90),
                ("cupom_teto", "Cupom máx.", 95),
                ("pendencias", "Pend.", 60),
            ],
            height=24,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=PAD)

    def refresh(self) -> None:
        rows = []
        month = self.month_var.get().strip()
        for row in list_variations_with_sales_metrics(month):
            lucro_por_unidade = float(row["lucro_por_unidade"] or 0)
            cupom_teto = max(lucro_por_unidade, 0)
            rows.append(
                {
                    "id": row["id"],
                    "produto_pai": row["produto_pai"],
                    "nome_variacao": row["nome_variacao"],
                    "sku": row.get("sku") or "-",
                    "custo_unitario": brl(row["custo_unitario"]) if row["custo_unitario"] is not None else "Pendente",
                    "preco_medio_vendido": brl(row["preco_medio_vendido"]),
                    "unidades_vendidas": int(row["unidades_vendidas"] or 0),
                    "faturamento": brl(row["faturamento"]),
                    "lucro": brl(row["lucro"]),
                    "margem": percent(row["margem"]),
                    "lucro_por_unidade": brl(lucro_por_unidade),
                    "cupom_teto": brl(cupom_teto),
                    "pendencias": int(row.get("pendencias") or 0),
                }
            )
        self.table.set_rows(rows)
