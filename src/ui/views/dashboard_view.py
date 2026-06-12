import customtkinter as ctk

from src.services.reports_service import current_month_reference, get_dashboard_summary, get_product_ranking
from src.ui.components import MetricCard, SimpleTable
from src.ui.theme import PAD
from src.utils import brl, percent


class DashboardView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.month_var = ctk.StringVar(value=current_month_reference())
        self.chart_metric_var = ctk.StringVar(value="Lucro")
        self.cards: dict[str, MetricCard] = {}
        self.chart_canvas = None
        self.chart_frame = None
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

        content = ctk.CTkFrame(self)
        content.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            content,
            text="Ranking por produto pai",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        chart_header = ctk.CTkFrame(content)
        chart_header.grid(row=0, column=1, sticky="ew", padx=8, pady=(8, 4))
        ctk.CTkLabel(chart_header, text="Composição", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        self.chart_metric_menu = ctk.CTkOptionMenu(
            chart_header,
            variable=self.chart_metric_var,
            values=["Lucro", "Faturamento", "Unidades"],
            command=lambda _value: self.refresh(),
            width=130,
        )
        self.chart_metric_menu.pack(side="right", padx=6)

        self.table = SimpleTable(
            content,
            [
                ("produto_pai", "Produto pai", 320),
                ("faturamento", "Faturamento", 120),
                ("unidades", "Unidades", 85),
                ("lucro", "Lucro", 120),
                ("margem", "Margem", 90),
            ],
            height=15,
        )
        self.table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        self.chart_frame = ctk.CTkFrame(content)
        self.chart_frame.grid(row=1, column=1, sticky="nsew", padx=8, pady=(0, 8))

    def refresh(self) -> None:
        month = self.month_var.get().strip()
        summary = get_dashboard_summary(month)
        self.cards["faturamento_bruto"].set_value(brl(summary["faturamento_bruto"]))
        self.cards["lucro_bruto"].set_value(brl(summary["lucro_bruto"]))
        self.cards["despesas"].set_value(brl(summary["despesas"]))
        self.cards["lucro_final"].set_value(brl(summary["lucro_final"]))
        self.cards["margem_liquida"].set_value(percent(summary["margem_liquida"]))
        self.cards["custos_pendentes"].set_value(str(summary["custos_pendentes"]))

        raw_ranking = get_product_ranking(month)
        ranking = []
        for row in raw_ranking:
            ranking.append(
                {
                    "produto_pai": row["produto_pai"],
                    "faturamento": brl(row["faturamento"]),
                    "unidades": row["unidades"],
                    "lucro": brl(row["lucro"]),
                    "margem": percent(row["margem"]),
                }
            )
        self.table.set_rows(ranking)
        self.draw_composition_chart(raw_ranking)

    def draw_composition_chart(self, ranking: list[dict]) -> None:
        if self.chart_frame is None:
            return
        if self.chart_canvas is not None:
            self.chart_canvas.get_tk_widget().destroy()
            self.chart_canvas = None

        for child in self.chart_frame.winfo_children():
            child.destroy()

        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ModuleNotFoundError:
            ctk.CTkLabel(
                self.chart_frame,
                text=(
                    "Gráfico indisponível.\n\n"
                    "Instale o matplotlib para habilitar a pizza:\n"
                    "py -m pip install matplotlib"
                ),
                text_color="gray",
                justify="center",
            ).pack(expand=True, padx=16, pady=16)
            return

        metric_label = self.chart_metric_var.get()
        metric_key = {
            "Lucro": "lucro",
            "Faturamento": "faturamento",
            "Unidades": "unidades",
        }.get(metric_label, "lucro")

        chart_rows = []
        for row in ranking:
            value = float(row.get(metric_key) or 0)
            # Pizza não lida bem com valores negativos. Mantemos apenas fatias positivas.
            if value > 0:
                chart_rows.append({"produto": row["produto_pai"], "valor": value})

        fig = Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)

        if not chart_rows:
            ax.text(0.5, 0.5, "Sem dados positivos\npara o gráfico", ha="center", va="center")
            ax.axis("off")
        else:
            top = chart_rows[:8]
            others = chart_rows[8:]
            labels = [self._short_label(row["produto"]) for row in top]
            values = [row["valor"] for row in top]
            others_total = sum(row["valor"] for row in others)
            if others_total > 0:
                labels.append("Outros")
                values.append(others_total)

            ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
            ax.set_title(f"Composição por {metric_label.lower()}")
            ax.axis("equal")

        fig.tight_layout()
        self.chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        self.chart_canvas.draw()
        self.chart_canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)

    def _short_label(self, value: str, limit: int = 24) -> str:
        text = str(value or "")
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."
