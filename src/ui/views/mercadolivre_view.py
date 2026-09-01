from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.services.mercadolivre_import_service import (
    ML_COMMISSION_PERCENT,
    ML_FIXED_FEE,
    ML_TAX_PERCENT,
    find_ml_importations_same_period,
    preview_mercadolivre,
    save_mercadolivre_importation,
)
from src.ui.components import MetricCard, SimpleTable
from src.ui.theme import PAD
from src.utils import brl, percent


class MercadoLivreView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.file_var = ctk.StringVar(value="")
        self.start_var = ctk.StringVar(value=date.today().isoformat())
        self.end_var = ctk.StringVar(value=date.today().isoformat())
        self.status_var = ctk.StringVar(value="Nenhuma planilha do Mercado Livre selecionada.")
        self.summary_var = ctk.StringVar(value="Escolha a planilha para pré-visualizar o período e as vendas.")
        self.cards = {}
        self.preview_rows = []
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Mercado Livre", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text=(
                "Importa o relatório de vendas do Mercado Livre e soma as vendas ao mesmo DRE da Shopee. "
                "Regra ML: 9% de imposto + 25% de comissão + R$ 7,00 por pedido. "
                "Os anúncios vendidos são cadastrados como produtos novos do Mercado Livre, com custo pendente, para vínculo posterior."
            ),
            text_color="gray", wraplength=1000, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=(0, PAD))
        box.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(box, text="Escolher planilha", command=self.choose_file).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.file_var).grid(row=0, column=1, columnspan=3, padx=8, pady=8, sticky="ew")
        ctk.CTkLabel(box, text="Período:").grid(row=1, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.start_var, width=120).grid(row=1, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.end_var, width=120).grid(row=1, column=2, padx=8, pady=8, sticky="w")
        ctk.CTkButton(box, text="Pré-visualizar", command=self.preview).grid(row=1, column=3, padx=8, pady=8, sticky="w")
        ctk.CTkButton(box, text="Confirmar e plugar", command=self.confirm).grid(row=2, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, textvariable=self.status_var, text_color="gray", wraplength=760, justify="left").grid(row=2, column=1, columnspan=3, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, textvariable=self.summary_var, text_color="#f6c343", wraplength=1000, justify="left").grid(row=3, column=0, columnspan=4, padx=8, pady=(0, 10), sticky="w")

        metrics = ctk.CTkFrame(self)
        metrics.pack(fill="x", padx=PAD, pady=(0, PAD))
        for idx, (key, title) in enumerate([
            ("faturamento", "Faturamento ML"),
            ("pedidos", "Pedidos"),
            ("unidades", "Unidades"),
            ("imposto", "Imposto 9%"),
            ("comissao", "Comissão 25%"),
            ("taxa_fixa", "Taxa R$7/pedido"),
            ("liquido_sem_custo", "Após taxas"),
        ]):
            card = MetricCard(metrics, title)
            card.grid(row=0, column=idx, sticky="ew", padx=4, pady=5)
            metrics.grid_columnconfigure(idx, weight=1)
            self.cards[key] = card

        self.table = SimpleTable(
            self,
            [
                ("ad_id", "ID anúncio", 100),
                ("produto_nome", "Produto ML", 300),
                ("variacao_nome", "Variação", 150),
                ("pedidos", "Pedidos", 75),
                ("unidades", "Unid.", 70),
                ("faturamento", "Bruto", 110),
                ("imposto", "Imposto", 100),
                ("comissao", "Comissão", 105),
                ("taxa_fixa", "Taxa fixa", 110),
                ("custo", "Custo", 100),
                ("lucro", "Lucro", 105),
                ("margem", "Margem", 85),
            ], height=18,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Custo pendente: o produto entra no DRE com faturamento e taxas, mas o lucro definitivo só é apurado quando houver custo cadastrado ou vínculo com um produto mestre.",
            text_color="#f6c343", wraplength=1000, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(title="Escolha o relatório de vendas do Mercado Livre", filetypes=[("Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")])
        if not path:
            return
        self.file_var.set(path)
        try:
            preview = preview_mercadolivre(path)
            self.start_var.set(preview["data_inicio"].isoformat())
            self.end_var.set(preview["data_fim"].isoformat())
            self.status_var.set(f"Selecionado: {Path(path).name}")
            self._render_preview(preview)
        except Exception as exc:
            self.status_var.set(f"Arquivo selecionado, mas não consegui pré-visualizar: {exc}")

    def preview(self) -> None:
        path = self.file_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha a planilha do Mercado Livre primeiro.")
            return
        try:
            preview = preview_mercadolivre(path)
            self.start_var.set(preview["data_inicio"].isoformat())
            self.end_var.set(preview["data_fim"].isoformat())
            self._render_preview(preview)
        except Exception as exc:
            messagebox.showerror("Erro ao ler Mercado Livre", str(exc))

    def _render_preview(self, preview: dict) -> None:
        self.preview_rows = preview["rows"]
        rows = []
        total_tax = total_commission = total_fixed = 0.0
        for item in self.preview_rows:
            gross = float(item["faturamento"])
            orders = int(item["pedidos"])
            units = int(item["unidades"])
            tax = gross * ML_TAX_PERCENT / 100
            commission = gross * ML_COMMISSION_PERCENT / 100
            fixed = orders * ML_FIXED_FEE
            after_fees = gross - tax - commission - fixed
            total_tax += tax; total_commission += commission; total_fixed += fixed
            rows.append({
                "ad_id": item["ad_id"], "produto_nome": item["produto_nome"], "variacao_nome": item["variacao_nome"],
                "pedidos": orders, "unidades": units, "faturamento": brl(gross), "imposto": brl(tax),
                "comissao": brl(commission), "taxa_fixa": brl(fixed), "custo": "Pendente", "lucro": brl(after_fees),
                "margem": percent((after_fees / gross * 100) if gross else 0),
            })
        self.table.set_rows(rows)
        gross_total = float(preview["faturamento"])
        net = gross_total - total_tax - total_commission - total_fixed
        self.cards["faturamento"].set_value(brl(gross_total))
        self.cards["pedidos"].set_value(str(preview["pedidos"]))
        self.cards["unidades"].set_value(str(preview["unidades"]))
        self.cards["imposto"].set_value(brl(total_tax))
        self.cards["comissao"].set_value(brl(total_commission))
        self.cards["taxa_fixa"].set_value(brl(total_fixed))
        self.cards["liquido_sem_custo"].set_value(brl(net))
        self.summary_var.set(
            f"Esta planilha será plugada como Mercado Livre | {preview['data_inicio'].isoformat()} até {preview['data_fim'].isoformat()} | "
            f"{preview['count']} anúncios com vendas | {preview['pedidos']} pedidos | {preview['unidades']} unidades | faturamento {brl(gross_total)}."
        )
        self.status_var.set(
            f"Regra ML: {ML_TAX_PERCENT:g}% imposto + {ML_COMMISSION_PERCENT:g}% comissão + R$ {ML_FIXED_FEE:.2f}/pedido. "
            "A taxa fixa usa pedidos; o CMV usa unidades."
        )

    def confirm(self) -> None:
        path = self.file_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha a planilha primeiro.")
            return
        try:
            start = date.fromisoformat(self.start_var.get().strip())
            end = date.fromisoformat(self.end_var.get().strip())
        except ValueError:
            messagebox.showerror("Data inválida", "Use AAAA-MM-DD.")
            return
        try:
            duplicates = find_ml_importations_same_period(start, end)
            if duplicates:
                answer = messagebox.askyesno("Período já importado", "Já existe uma planilha do Mercado Livre para este período.\n\nSubstituir a importação anterior e manter apenas esta versão?")
                if not answer:
                    return
            result = save_mercadolivre_importation(path, start, end, replace_same_period=True)
        except Exception as exc:
            messagebox.showerror("Erro ao importar Mercado Livre", str(exc))
            return
        messagebox.showinfo(
            "Mercado Livre",
            f"Importação concluída.\n\n{result['inserted']} anúncios/vendas incorporados ao DRE.\n"
            f"Pedidos: {result['pedidos']}\nUnidades: {result['unidades']}\nFaturamento: {brl(result['faturamento'])}\n"
            f"Custos pendentes: {result['incomplete']}\n\nOs anúncios foram criados como produtos novos do Mercado Livre.",
        )
        self.status_var.set("Mercado Livre incorporado ao DRE e aos relatórios.")
