import customtkinter as ctk

from src.services.reports_service import current_month_reference, get_dashboard_summary, get_product_ranking
from src.ui.components import MetricCard, SimpleTable
from src.ui.theme import PAD
from src.utils import brl, percent


class DashboardView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.month_var = ctk.StringVar(value=current_month_reference())
        self.cards: dict[str, MetricCard] = {}
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=PAD, pady=PAD)

        ctk.CTkLabel(header, text="Dashboard", font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text="Mês:").pack(side="left", padx=(30, 8))
        ctk.CTkEntry(header, textvariable=self.month_var, width=90).pack(side="left")
        ctk.CTkButton(header, text="Atualizar", command=self.refresh, width=100).pack(side="left", padx=8)

        cards_frame = ctk.CTkFrame(self)
        cards_frame.pack(fill="x", padx=PAD, pady=(0, PAD))

        card_specs = [
            ("faturamento_bruto", "Faturamento"),
            ("lucro_bruto", "Lucro bruto"),
            ("despesas", "Despesas"),
            ("lucro_final", "Lucro final"),
            ("margem_liquida", "Margem líquida"),
            ("custos_pendentes", "Custos pendentes"),
        ]
        for idx, (key, title) in enumerate(card_specs):
            card = MetricCard(cards_frame, title)
            card.grid(row=0, column=idx, padx=6, pady=6, sticky="ew")
            cards_frame.grid_columnconfigure(idx, weight=1)
            self.cards[key] = card

        ctk.CTkLabel(
            self,
            text="Ranking por produto pai",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=PAD, pady=(8, 4))

        self.table = SimpleTable(
            self,
            [
                ("produto_pai", "Produto pai", 360),
                ("faturamento", "Faturamento", 140),
                ("unidades", "Unidades", 100),
                ("lucro", "Lucro", 140),
            ],
            height=14,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

    def refresh(self) -> None:
        month = self.month_var.get().strip()
        summary = get_dashboard_summary(month)
        self.cards["faturamento_bruto"].set_value(brl(summary["faturamento_bruto"]))
        self.cards["lucro_bruto"].set_value(brl(summary["lucro_bruto"]))
        self.cards["despesas"].set_value(brl(summary["despesas"]))
        self.cards["lucro_final"].set_value(brl(summary["lucro_final"]))
        self.cards["margem_liquida"].set_value(percent(summary["margem_liquida"]))
        self.cards["custos_pendentes"].set_value(str(summary["custos_pendentes"]))

        ranking = []
        for row in get_product_ranking(month):
            ranking.append(
                {
                    "produto_pai": row["produto_pai"],
                    "faturamento": brl(row["faturamento"]),
                    "unidades": row["unidades"],
                    "lucro": brl(row["lucro"]),
                }
            )
        self.table.set_rows(ranking)
