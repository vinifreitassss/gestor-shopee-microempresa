import customtkinter as ctk

from src.services.reports_service import current_month_reference
from src.services.shopee_fees_service import (
    get_shopee_fees_summary,
    list_shopee_fees_breakdown,
    list_shopee_fees_by_order,
    list_tax_base_scenarios,
)
from src.ui.components import MetricCard, SimpleTable
from src.ui.theme import PAD
from src.utils import brl, percent


class ShopeeFeesView(ctk.CTkFrame):
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
            text="Taxas Shopee e Base Tributária",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(header, text="Mês:").pack(side="left", padx=(24, 6))
        ctk.CTkEntry(header, textvariable=self.month_var, width=90).pack(side="left", padx=6)
        ctk.CTkButton(header, text="Atualizar", command=self.refresh).pack(side="left", padx=8)

        ctk.CTkLabel(
            self,
            text=(
                "Use esta tela para gestão e simulação. A base fiscal oficial deve ser validada com o contador. "
                "O app mantém a base bruta conservadora e mostra cenários líquidos lado a lado."
            ),
            text_color="gray",
            wraplength=980,
            justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        metrics = ctk.CTkFrame(self)
        metrics.pack(fill="x", padx=PAD, pady=(0, PAD))
        metric_defs = [
            ("faturamento_bruto", "Faturamento bruto"),
            ("total_taxas_pedidos", "Taxas dos pedidos"),
            ("shopee_ads", "Shopee Ads"),
            ("total_shopee", "Total Shopee"),
            ("percentual_total_shopee_sobre_bruto", "% Shopee/bruto"),
            ("base_liquida_sem_ads", "Base líquida pedidos"),
            ("economia_sem_ads", "Economia simulada"),
            ("liquido_estimado", "Líquido estimado"),
        ]
        for idx, (key, title) in enumerate(metric_defs):
            card = MetricCard(metrics, title)
            card.grid(row=idx // 4, column=idx % 4, sticky="ew", padx=6, pady=6)
            metrics.grid_columnconfigure(idx % 4, weight=1)
            self.cards[key] = card

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self.breakdown_tab = self.tabs.add("Composição")
        self.scenarios_tab = self.tabs.add("Cenários tributários")
        self.orders_tab = self.tabs.add("Pedidos")

        self._build_breakdown_tab(self.breakdown_tab)
        self._build_scenarios_tab(self.scenarios_tab)
        self._build_orders_tab(self.orders_tab)

    def _build_breakdown_tab(self, parent) -> None:
        ctk.CTkLabel(
            parent,
            text="Quanto a Shopee reteve/cobrou no mês, separando taxas por pedido e movimentos da carteira.",
            text_color="gray",
        ).pack(anchor="w", padx=8, pady=(8, 4))
        self.breakdown_table = SimpleTable(
            parent,
            [
                ("grupo", "Grupo", 180),
                ("item", "Item", 260),
                ("valor", "Valor", 150),
            ],
            height=10,
        )
        self.breakdown_table.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_scenarios_tab(self, parent) -> None:
        ctk.CTkLabel(
            parent,
            text=(
                "Cenários para conversa com contador. O app não muda sozinho o DAS: ele mostra o impacto "
                "de apurar sobre bruto ou sobre valores líquidos pós-Shopee."
            ),
            text_color="gray",
            wraplength=980,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(8, 4))
        self.scenarios_table = SimpleTable(
            parent,
            [
                ("cenario", "Cenário", 230),
                ("base", "Base", 140),
                ("imposto", "Imposto estimado", 150),
                ("economia", "Economia", 130),
                ("obs", "Observação", 520),
            ],
            height=8,
        )
        self.scenarios_table.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_orders_tab(self, parent) -> None:
        ctk.CTkLabel(
            parent,
            text="Pedidos com maior custo de intermediação Shopee no mês.",
            text_color="gray",
        ).pack(anchor="w", padx=8, pady=(8, 4))
        self.orders_table = SimpleTable(
            parent,
            [
                ("pedido_id", "Pedido", 150),
                ("data_base", "Data", 110),
                ("status_financeiro", "Status", 115),
                ("bruto", "Bruto", 115),
                ("taxa_transacao", "Taxa trans.", 115),
                ("comissao_liquida", "Comissão", 115),
                ("taxa_servico_liquida", "Taxa serviço", 115),
                ("total_taxas", "Total taxas", 115),
                ("percentual_taxas", "%", 75),
                ("valor_liquido_estimado", "Líquido", 115),
                ("diferenca", "Dif.", 95),
            ],
            height=16,
        )
        self.orders_table.pack(fill="both", expand=True, padx=8, pady=8)

    def refresh(self) -> None:
        month = self.month_var.get().strip()
        summary = get_shopee_fees_summary(month)
        money_fields = {
            "faturamento_bruto",
            "total_taxas_pedidos",
            "shopee_ads",
            "total_shopee",
            "base_liquida_sem_ads",
            "economia_sem_ads",
            "liquido_estimado",
        }
        percent_fields = {"percentual_total_shopee_sobre_bruto"}
        for key, card in self.cards.items():
            value = summary.get(key, 0)
            if key in money_fields:
                card.set_value(brl(value))
            elif key in percent_fields:
                card.set_value(percent(value))
            else:
                card.set_value(str(value))

        self.breakdown_table.set_rows(
            [
                {"grupo": row["grupo"], "item": row["item"], "valor": brl(row["valor"])}
                for row in list_shopee_fees_breakdown(month)
            ]
        )

        self.scenarios_table.set_rows(
            [
                {
                    "cenario": row["cenario"],
                    "base": brl(row["base"]),
                    "imposto": brl(row["imposto"]),
                    "economia": brl(row["economia"]),
                    "obs": row["obs"],
                }
                for row in list_tax_base_scenarios(month)
            ]
        )

        order_rows = []
        for row in list_shopee_fees_by_order(month):
            bruto = float(row.get("total_global") or row.get("valor_total") or 0)
            order_rows.append(
                {
                    "pedido_id": row.get("pedido_id"),
                    "data_base": row.get("data_base"),
                    "status_financeiro": row.get("status_financeiro"),
                    "bruto": brl(bruto),
                    "taxa_transacao": brl(row.get("taxa_transacao")),
                    "comissao_liquida": brl(row.get("comissao_liquida")),
                    "taxa_servico_liquida": brl(row.get("taxa_servico_liquida")),
                    "total_taxas": brl(row.get("total_taxas")),
                    "percentual_taxas": percent(row.get("percentual_taxas")),
                    "valor_liquido_estimado": brl(row.get("valor_liquido_estimado")),
                    "diferenca": brl(row.get("diferenca")),
                }
            )
        self.orders_table.set_rows(order_rows)
