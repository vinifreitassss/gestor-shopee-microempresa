import customtkinter as ctk

from src.services.products_service import list_variations
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl


class ProductsView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Produtos e Variações", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Produto pai é usado para agrupamento. Variação é usada para cálculo real de venda, custo e lucro.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        self.table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("produto_pai", "Produto pai", 360),
                ("nome_variacao", "Variação", 300),
                ("sku", "SKU", 140),
                ("tipo_produto", "Tipo", 100),
                ("custo_unitario", "Custo", 120),
            ],
            height=24,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=PAD)

    def refresh(self) -> None:
        rows = []
        for row in list_variations():
            rows.append(
                {
                    "id": row["id"],
                    "produto_pai": row["produto_pai"],
                    "nome_variacao": row["nome_variacao"],
                    "sku": row.get("sku") or "-",
                    "tipo_produto": row["tipo_produto"],
                    "custo_unitario": brl(row["custo_unitario"]) if row["custo_unitario"] is not None else "Pendente",
                }
            )
        self.table.set_rows(rows)
