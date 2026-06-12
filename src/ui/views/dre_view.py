from tkinter import messagebox

import customtkinter as ctk

from src.services.reports_service import (
    close_month,
    current_month_reference,
    get_dre,
    get_expenses_by_category,
    get_operational_insights,
    get_pending_costs,
    get_product_abc_curve,
    get_product_ranking,
)
from src.ui.components import MetricCard, SimpleTable
from src.ui.theme import PAD
from src.utils import brl, percent


class DreView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.month_var = ctk.StringVar(value=current_month_reference())
        self.cards: dict[str, MetricCard] = {}
        self.chart_canvases = []
        self.chart_frames: dict[str, ctk.CTkFrame] = {}
        self.alert_var = ctk.StringVar(value="")
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkLabel(header, text="Resultado Operacional", font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text="Mês:").pack(side="left", padx=(30, 8))
        ctk.CTkEntry(header, textvariable=self.month_var, width=90).pack(side="left")
        ctk.CTkButton(header, text="Atualizar", command=self.refresh).pack(side="left", padx=8)
        ctk.CTkButton(header, text="Fechar mês", command=self.close_month).pack(side="left", padx=8)

        self.body = ctk.CTkScrollableFrame(self)
        self.body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

        cards_frame = ctk.CTkFrame(self.body)
        cards_frame.pack(fill="x", pady=(0, PAD))
        card_specs = [
            ("faturamento_bruto", "Faturamento"),
            ("lucro_bruto", "Lucro bruto"),
            ("despesas", "Despesas"),
            ("lucro_final", "Lucro operacional"),
            ("margem_liquida", "Margem operacional"),
            ("itens_incompletos", "Custos pendentes"),
        ]
        for idx, (key, title) in enumerate(card_specs):
            card = MetricCard(cards_frame, title)
            card.grid(row=0, column=idx, padx=6, pady=6, sticky="ew")
            cards_frame.grid_columnconfigure(idx, weight=1)
            self.cards[key] = card

        alert = ctk.CTkLabel(
            self.body,
            textvariable=self.alert_var,
            text_color="#f6c343",
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=1000,
            justify="left",
        )
        alert.pack(anchor="w", fill="x", pady=(0, PAD))

        top = ctk.CTkFrame(self.body)
        top.pack(fill="x", pady=(0, PAD))
        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=2)

        ctk.CTkLabel(top, text="DRE operacional", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        self.dre_table = SimpleTable(
            top,
            [("indicador", "Indicador", 300), ("valor", "Valor", 150)],
            height=10,
        )
        self.dre_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        ctk.CTkLabel(top, text="Insights do mês", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=1, sticky="w", padx=8, pady=(8, 4))
        self.insights_table = SimpleTable(
            top,
            [("insight", "Insight", 250), ("resultado", "Resultado", 560)],
            height=10,
        )
        self.insights_table.grid(row=1, column=1, sticky="nsew", padx=8, pady=(0, 8))

        charts = ctk.CTkFrame(self.body)
        charts.pack(fill="x", pady=(0, PAD))
        charts.grid_columnconfigure(0, weight=1)
        charts.grid_columnconfigure(1, weight=1)
        charts.grid_columnconfigure(2, weight=1)

        self.chart_frames["profit"] = self._chart_box(charts, "Lucro por produto", 0)
        self.chart_frames["expenses"] = self._chart_box(charts, "Despesas por categoria", 1)
        self.chart_frames["margin"] = self._chart_box(charts, "Margem por produto", 2)

        ctk.CTkLabel(self.body, text="Produtos: lucro, margem e custo", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(8, 4))
        self.product_table = SimpleTable(
            self.body,
            [
                ("produto_pai", "Produto", 300),
                ("faturamento", "Faturamento", 115),
                ("unidades", "Unid.", 70),
                ("custo_total", "Custo", 110),
                ("lucro", "Lucro", 110),
                ("margem", "Margem", 85),
                ("ticket_medio", "Ticket", 90),
                ("lucro_por_unidade", "Lucro/un.", 95),
                ("pendencias", "Pend.", 70),
            ],
            height=12,
        )
        self.product_table.pack(fill="x", pady=(0, PAD))

        ctk.CTkLabel(self.body, text="Curva ABC por lucro", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(8, 4))
        self.abc_table = SimpleTable(
            self.body,
            [
                ("produto_pai", "Produto", 360),
                ("abc_valor", "Lucro", 120),
                ("abc_percentual", "% total", 90),
                ("abc_acumulado", "% acum.", 90),
                ("abc_classe", "Classe", 80),
            ],
            height=10,
        )
        self.abc_table.pack(fill="x", pady=(0, PAD))

        ctk.CTkLabel(
            self.body,
            text="Custos pendentes vendidos",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", pady=(8, 4))
        self.pending_table = SimpleTable(
            self.body,
            [
                ("produto_pai", "Produto pai", 320),
                ("nome_variacao", "Variação", 300),
                ("sku", "SKU", 120),
                ("unidades", "Unidades", 90),
                ("faturamento", "Faturamento", 140),
            ],
            height=8,
        )
        self.pending_table.pack(fill="x", pady=(0, PAD))

    def _chart_box(self, master, title: str, column: int) -> ctk.CTkFrame:
        box = ctk.CTkFrame(master)
        box.grid(row=0, column=column, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=8, pady=(8, 4))
        frame = ctk.CTkFrame(box)
        frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        return frame

    def refresh(self) -> None:
        month = self.month_var.get().strip()
        dre = get_dre(month)
        products = get_product_ranking(month)
        expenses = get_expenses_by_category(month)
        abc = get_product_abc_curve(month, "lucro")
        insights = get_operational_insights(month)
        pending = get_pending_costs(month)

        self.cards["faturamento_bruto"].set_value(brl(dre["faturamento_bruto"]))
        self.cards["lucro_bruto"].set_value(brl(dre["lucro_bruto"]))
        self.cards["despesas"].set_value(brl(dre["despesas"]))
        self.cards["lucro_final"].set_value(brl(dre["lucro_final"]))
        self.cards["margem_liquida"].set_value(percent(dre["margem_liquida"]))
        self.cards["itens_incompletos"].set_value(str(dre["itens_incompletos"]))

        if dre["itens_incompletos"]:
            self.alert_var.set(f"⚠ Existem {dre['itens_incompletos']} vendas/itens com custo pendente. O lucro operacional pode estar subestimado ou incompleto.")
        else:
            self.alert_var.set("Resultado calculado sem custos pendentes vendidos.")

        self.dre_table.set_rows(
            [
                {"indicador": "Faturamento bruto", "valor": brl(dre["faturamento_bruto"])},
                {"indicador": "(-) Impostos", "valor": brl(dre["impostos"])},
                {"indicador": "(-) Comissão Shopee", "valor": brl(dre["comissao"])},
                {"indicador": "(-) Taxa fixa Shopee", "valor": brl(dre["taxa_fixa"])},
                {"indicador": "(-) CPV / custo dos produtos", "valor": brl(dre["custo_produtos"])},
                {"indicador": "Lucro bruto", "valor": brl(dre["lucro_bruto"])},
                {"indicador": "(-) Despesas operacionais", "valor": brl(dre["despesas"])},
                {"indicador": "Lucro operacional", "valor": brl(dre["lucro_final"])},
                {"indicador": "Margem operacional", "valor": percent(dre["margem_liquida"])},
                {"indicador": "Unidades vendidas", "valor": str(dre["unidades"])},
            ]
        )

        self.insights_table.set_rows(self._format_insights(insights))
        self.product_table.set_rows(self._format_products(products))
        self.abc_table.set_rows(self._format_abc(abc))
        self.pending_table.set_rows(self._format_pending(pending))
        self.draw_charts(products, expenses)

    def _format_products(self, products: list[dict]) -> list[dict]:
        rows = []
        for row in products:
            rows.append(
                {
                    "produto_pai": row["produto_pai"],
                    "faturamento": brl(row["faturamento"]),
                    "unidades": row["unidades"],
                    "custo_total": brl(row["custo_total"]),
                    "lucro": brl(row["lucro"]),
                    "margem": percent(row["margem"]),
                    "ticket_medio": brl(row["ticket_medio"]),
                    "lucro_por_unidade": brl(row["lucro_por_unidade"]),
                    "pendencias": int(row.get("pendencias") or 0),
                }
            )
        return rows

    def _format_abc(self, abc: list[dict]) -> list[dict]:
        rows = []
        for row in abc:
            rows.append(
                {
                    "produto_pai": row["produto_pai"],
                    "abc_valor": brl(row["abc_valor"]),
                    "abc_percentual": percent(row["abc_percentual"]),
                    "abc_acumulado": percent(row["abc_acumulado"]),
                    "abc_classe": row["abc_classe"],
                }
            )
        return rows

    def _format_pending(self, pending: list[dict]) -> list[dict]:
        return [
            {
                "produto_pai": row["produto_pai"],
                "nome_variacao": row["nome_variacao"],
                "sku": row.get("sku") or "-",
                "unidades": row["unidades"],
                "faturamento": brl(row["faturamento"]),
            }
            for row in pending
        ]

    def _format_insights(self, insights: dict) -> list[dict]:
        def product_summary(row, value_key="lucro", value_format=brl):
            if not row:
                return "Sem dados"
            return f"{row['produto_pai']} — {value_format(row.get(value_key) or 0)}"

        top_expense = insights.get("maior_despesa_categoria")
        abc_a = insights.get("produtos_abc_a") or []
        abc_names = ", ".join(row["produto_pai"] for row in abc_a[:5]) if abc_a else "Sem classe A"

        return [
            {"insight": "Produto mais lucrativo", "resultado": product_summary(insights.get("produto_mais_lucrativo"), "lucro", brl)},
            {"insight": "Produto menos lucrativo", "resultado": product_summary(insights.get("produto_menos_lucrativo"), "lucro", brl)},
            {"insight": "Maior faturamento", "resultado": product_summary(insights.get("maior_faturamento"), "faturamento", brl)},
            {"insight": "Melhor margem", "resultado": product_summary(insights.get("produto_melhor_margem"), "margem", percent)},
            {"insight": "Pior margem", "resultado": product_summary(insights.get("produto_pior_margem"), "margem", percent)},
            {"insight": "Maior custo total", "resultado": product_summary(insights.get("maior_custo_total"), "custo_total", brl)},
            {"insight": "Maior custo / faturamento", "resultado": product_summary(insights.get("maior_custo_percentual"), "custo_sobre_faturamento", percent)},
            {"insight": "Mais vendido em unidades", "resultado": product_summary(insights.get("mais_vendido_unidades"), "unidades", lambda v: str(int(v)))},
            {"insight": "Melhor lucro por unidade", "resultado": product_summary(insights.get("melhor_lucro_por_unidade"), "lucro_por_unidade", brl)},
            {"insight": "Maior despesa", "resultado": f"{top_expense['categoria']} — {brl(top_expense['valor'])}" if top_expense else "Sem despesas"},
            {"insight": "Despesas / faturamento", "resultado": percent(insights.get("despesas_sobre_faturamento") or 0)},
            {"insight": "Taxas Shopee / faturamento", "resultado": percent(insights.get("taxas_sobre_faturamento") or 0)},
            {"insight": "Produtos com prejuízo", "resultado": str(insights.get("produtos_com_prejuizo") or 0)},
            {"insight": "Produtos com margem abaixo de 10%", "resultado": str(insights.get("produtos_margem_baixa") or 0)},
            {"insight": "Produtos classe A por lucro", "resultado": abc_names},
        ]

    def draw_charts(self, products: list[dict], expenses: list[dict]) -> None:
        for canvas in self.chart_canvases:
            try:
                canvas.get_tk_widget().destroy()
            except Exception:
                pass
        self.chart_canvases = []
        for frame in self.chart_frames.values():
            for child in frame.winfo_children():
                child.destroy()

        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ModuleNotFoundError:
            for frame in self.chart_frames.values():
                ctk.CTkLabel(
                    frame,
                    text="Gráfico indisponível.\nInstale: py -m pip install matplotlib",
                    text_color="gray",
                    justify="center",
                ).pack(expand=True, padx=12, pady=12)
            return

        self._draw_pie(
            FigureCanvasTkAgg,
            Figure,
            self.chart_frames["profit"],
            [(row["produto_pai"], float(row.get("lucro") or 0)) for row in products],
            "Lucro por produto",
        )
        self._draw_pie(
            FigureCanvasTkAgg,
            Figure,
            self.chart_frames["expenses"],
            [(row["categoria"], float(row.get("valor") or 0)) for row in expenses],
            "Despesas por categoria",
        )
        self._draw_margin_bar(FigureCanvasTkAgg, Figure, self.chart_frames["margin"], products)

    def _draw_pie(self, canvas_cls, figure_cls, frame, values: list[tuple[str, float]], title: str) -> None:
        positive = [(label, value) for label, value in values if value > 0]
        positive = positive[:8] + [("Outros", sum(value for _, value in positive[8:]))] if len(positive) > 8 else positive
        positive = [(label, value) for label, value in positive if value > 0]

        fig = figure_cls(figsize=(4.2, 3.2), dpi=100)
        ax = fig.add_subplot(111)
        if not positive:
            ax.text(0.5, 0.5, "Sem dados positivos", ha="center", va="center")
            ax.axis("off")
        else:
            labels = [self._short_label(label, 20) for label, _ in positive]
            data = [value for _, value in positive]
            ax.pie(data, labels=labels, autopct="%1.1f%%", startangle=90)
            ax.set_title(title)
            ax.axis("equal")
        fig.tight_layout()
        canvas = canvas_cls(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.chart_canvases.append(canvas)

    def _draw_margin_bar(self, canvas_cls, figure_cls, frame, products: list[dict]) -> None:
        rows = [row for row in products if float(row.get("faturamento") or 0) > 0][:8]
        fig = figure_cls(figsize=(4.2, 3.2), dpi=100)
        ax = fig.add_subplot(111)
        if not rows:
            ax.text(0.5, 0.5, "Sem dados", ha="center", va="center")
            ax.axis("off")
        else:
            labels = [self._short_label(row["produto_pai"], 18) for row in rows]
            margins = [float(row.get("margem") or 0) for row in rows]
            ax.barh(labels, margins)
            ax.set_xlabel("Margem %")
            ax.set_title("Margem por produto")
            ax.invert_yaxis()
        fig.tight_layout()
        canvas = canvas_cls(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.chart_canvases.append(canvas)

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

    def _short_label(self, value: str, limit: int = 24) -> str:
        text = str(value or "")
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."
