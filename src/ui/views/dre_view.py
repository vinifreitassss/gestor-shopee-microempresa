from tkinter import messagebox

import customtkinter as ctk

from src.services.reports_service import close_month, current_month_reference, get_dre, get_pending_costs
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, percent


class DreView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.month_var = ctk.StringVar(value=current_month_reference())
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkLabel(header, text="DRE Mensal", font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text="Mês:").pack(side="left", padx=(30, 8))
        ctk.CTkEntry(header, textvariable=self.month_var, width=90).pack(side="left")
        ctk.CTkButton(header, text="Atualizar", command=self.refresh).pack(side="left", padx=8)
        ctk.CTkButton(header, text="Fechar mês", command=self.close_month).pack(side="left", padx=8)

        self.dre_table = SimpleTable(
            self,
            [("indicador", "Indicador", 360), ("valor", "Valor", 180)],
            height=10,
        )
        self.dre_table.pack(fill="x", padx=PAD, pady=(0, PAD))

        ctk.CTkLabel(
            self,
            text="Custos pendentes somente de variações vendidas",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=PAD, pady=(8, 4))

        self.pending_table = SimpleTable(
            self,
            [
                ("produto_pai", "Produto pai", 320),
                ("nome_variacao", "Variação", 300),
                ("sku", "SKU", 120),
                ("unidades", "Unidades", 90),
                ("faturamento", "Faturamento", 140),
            ],
            height=12,
        )
        self.pending_table.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

    def refresh(self) -> None:
        month = self.month_var.get().strip()
        dre = get_dre(month)
        rows = [
            {"indicador": "Faturamento bruto", "valor": brl(dre["faturamento_bruto"])},
            {"indicador": "(-) Impostos", "valor": brl(dre["impostos"])},
            {"indicador": "(-) Comissão Shopee", "valor": brl(dre["comissao"])},
            {"indicador": "(-) Taxa fixa", "valor": brl(dre["taxa_fixa"])},
            {"indicador": "(-) Custo dos produtos vendidos", "valor": brl(dre["custo_produtos"])},
            {"indicador": "Lucro bruto", "valor": brl(dre["lucro_bruto"])},
            {"indicador": "(-) Despesas operacionais", "valor": brl(dre["despesas"])},
            {"indicador": "Lucro final", "valor": brl(dre["lucro_final"])},
            {"indicador": "Margem líquida", "valor": percent(dre["margem_liquida"])},
            {"indicador": "Itens com lucro incompleto", "valor": str(dre["itens_incompletos"])},
        ]
        self.dre_table.set_rows(rows)

        pending_rows = []
        for row in get_pending_costs(month):
            pending_rows.append(
                {
                    "produto_pai": row["produto_pai"],
                    "nome_variacao": row["nome_variacao"],
                    "sku": row.get("sku") or "-",
                    "unidades": row["unidades"],
                    "faturamento": brl(row["faturamento"]),
                }
            )
        self.pending_table.set_rows(pending_rows)

    def close_month(self) -> None:
        month = self.month_var.get().strip()
        dre = get_dre(month)
        if dre["itens_incompletos"]:
            ok = messagebox.askyesno(
                "Custos pendentes",
                "Existem variações vendidas sem custo. O lucro ficará incompleto.\n\nDeseja fechar mesmo assim?",
            )
            if not ok:
                return
        close_month(month)
        messagebox.showinfo("Fechamento", f"Mês {month} fechado/atualizado com sucesso.")
        self.refresh()
