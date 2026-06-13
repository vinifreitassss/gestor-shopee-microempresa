import customtkinter as ctk

from src.services.cashflow_service import get_cashflow_summary
from src.services.reports_service import current_month_reference
from src.ui.components import MetricCard
from src.ui.theme import PAD
from src.utils import brl, percent


class CashFlowView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.month_var = ctk.StringVar(value=current_month_reference())
        self.cards = {}
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=PAD, pady=PAD)

        ctk.CTkLabel(
            header,
            text="Fluxo de Caixa",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")

        ctk.CTkLabel(header, text="Mês:").pack(side="left", padx=(24, 6))
        ctk.CTkEntry(header, textvariable=self.month_var, width=90).pack(side="left", padx=6)
        ctk.CTkButton(header, text="Atualizar", command=self.refresh).pack(side="left", padx=8)

        metrics = ctk.CTkFrame(self)
        metrics.pack(fill="x", padx=PAD, pady=(0, PAD))

        metric_defs = [
            ("em_espera", "Shopee em espera"),
            ("saldo_shopee", "Saldo Shopee"),
            ("saques", "Transferido no mês"),
            ("despesas", "Despesas no mês"),
            ("imposto_reservado", "Imposto reservado"),
            ("caixa_livre_estimado", "Caixa livre estimado"),
            ("taxa_total_percentual", "Taxa média Shopee"),
            ("tempo_liberacao_medio", "Tempo médio liberação"),
        ]

        for idx, (key, title) in enumerate(metric_defs):
            card = MetricCard(metrics, title)
            card.grid(row=idx // 4, column=idx % 4, sticky="ew", padx=6, pady=6)
            metrics.grid_columnconfigure(idx % 4, weight=1)
            self.cards[key] = card

        self.info_label = ctk.CTkLabel(
            self,
            text="Importe pedidos enviados e o relatório de pagamentos na aba Importações para preencher estes indicadores.",
            text_color="gray",
        )
        self.info_label.pack(anchor="w", padx=PAD, pady=(0, PAD))

    def refresh(self) -> None:
        month = self.month_var.get().strip()
        summary = get_cashflow_summary(month)

        money_fields = {
            "em_espera",
            "saldo_shopee",
            "saques",
            "despesas",
            "imposto_reservado",
            "caixa_livre_estimado",
        }

        for key, card in self.cards.items():
            value = summary.get(key)
            if key in money_fields:
                card.set_value(brl(value))
            elif key == "taxa_total_percentual":
                card.set_value(percent(value))
            elif key == "tempo_liberacao_medio":
                card.set_value(f"{float(value or 0):.1f} dias".replace(".", ","))
            else:
                card.set_value(str(value or "-"))
