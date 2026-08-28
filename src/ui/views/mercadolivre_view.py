from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.services.mercadolivre_import_service import (
    find_ml_importations_same_period,
    preview_mercadolivre,
    save_mercadolivre_importation,
)
from src.services.settings_service import get_all_settings
from src.ui.components import MetricCard, SimpleTable
from src.ui.theme import PAD
from src.utils import brl


class MercadoLivreView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.file_var = ctk.StringVar(value="")
        self.start_var = ctk.StringVar(value="")
        self.end_var = ctk.StringVar(value="")
        self.status_var = ctk.StringVar(value="Nenhuma planilha do Mercado Livre selecionada.")
        self.summary_var = ctk.StringVar(value="Escolha a planilha padrão de desempenho do Mercado Livre.")
        self.cards = {}
        self.preview_rows = []
        self.preview_data = None
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Mercado Livre", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text=(
                "Importa o relatório padrão 'Métricas de desempenho dos seus anúncios'. "
                "O sistema usa ID do anúncio como identificador, Anúncio como produto, Variação/SKU como variação, "
                "Unidades vendidas como quantidade e Vendas brutas (BRL) como faturamento. "
                "Os anúncios são cadastrados no mesmo cadastro de produtos da Shopee para receber custo e regras normalmente."
            ),
            text_color="gray", wraplength=1000, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=(0, PAD))
        box.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(box, text="Anexar planilha ML", command=self.choose_file).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.file_var).grid(row=0, column=1, columnspan=3, padx=8, pady=8, sticky="ew")
        ctk.CTkLabel(box, text="Período encontrado:").grid(row=1, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.start_var, width=120, state="readonly").grid(row=1, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.end_var, width=120, state="readonly").grid(row=1, column=2, padx=8, pady=8, sticky="w")
        ctk.CTkButton(box, text="Pré-visualizar", command=self.preview).grid(row=1, column=3, padx=8, pady=8, sticky="w")
        ctk.CTkButton(box, text="Confirmar importação", command=self.confirm).grid(row=2, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, textvariable=self.status_var, text_color="gray", wraplength=760, justify="left").grid(row=2, column=1, columnspan=3, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, textvariable=self.summary_var, text_color="#f6c343", wraplength=1000, justify="left").grid(row=3, column=0, columnspan=4, padx=8, pady=(0, 10), sticky="w")

        metrics = ctk.CTkFrame(self)
        metrics.pack(fill="x", padx=PAD, pady=(0, PAD))
        for idx, (key, title) in enumerate([
            ("faturamento", "Faturamento ML"), ("unidades", "Unidades"),
            ("imposto", "Imposto"), ("comissao", "Comissão"),
            ("taxa_fixa", "Taxa fixa"), ("liquido_sem_custo", "Após taxas"),
        ]):
            card = MetricCard(metrics, title)
            card.grid(row=0, column=idx, sticky="ew", padx=5, pady=5)
            metrics.grid_columnconfigure(idx, weight=1)
            self.cards[key] = card

        self.table = SimpleTable(
            self,
            [
                ("ad_id", "ID anúncio", 100), ("produto_nome", "Produto ML", 300),
                ("variacao_nome", "Variação", 160), ("sku", "SKU", 110),
                ("unidades", "Unid.", 70), ("faturamento", "Bruto", 110),
                ("imposto", "Imposto", 100), ("comissao", "Comissão", 105),
                ("taxa_fixa", "Taxa fixa", 100), ("custo", "Custo", 100),
                ("lucro", "Lucro", 105), ("margem", "Margem", 85),
            ], height=18,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        ctk.CTkLabel(
            self,
            text=(
                "Importante: o relatório de desempenho do ML não traz as taxas finais. As taxas usadas são as configurações "
                "separadas do Mercado Livre em Configurações. O custo do produto permanece pendente até você cadastrar o custo "
                "da variação, exatamente como ocorre com os produtos da Shopee."
            ),
            text_color="#f6c343", wraplength=1000, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Escolha o relatório padrão de desempenho do Mercado Livre",
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self.file_var.set(path)
            self.preview()

    def preview(self) -> None:
        path = self.file_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha a planilha do Mercado Livre primeiro.")
            return
        try:
            preview = preview_mercadolivre(path)
            self.preview_data = preview
            self.start_var.set(preview["data_inicio"].isoformat())
            self.end_var.set(preview["data_fim"].isoformat())
            self._render_preview(preview)
        except Exception as exc:
            messagebox.showerror("Erro ao ler Mercado Livre", str(exc))

    def _ml_settings(self) -> tuple[float, float, float]:
        settings = get_all_settings()
        def number(key: str, default: float) -> float:
            try:
                return max(0.0, float(str(settings.get(key, default)).replace(",", ".")))
            except (TypeError, ValueError):
                return default
        return number("ml_imposto_percentual", 9), number("ml_comissao_percentual", 22), number("ml_taxa_fixa_unidade", 8)

    def _render_preview(self, preview: dict) -> None:
        self.preview_rows = preview["rows"]
        ml_tax, ml_commission, ml_fixed_fee = self._ml_settings()
        rows = []
        total_tax = total_commission = total_fixed = 0.0

        for item in self.preview_rows:
            gross = float(item["faturamento"])
            units = int(item["unidades"])
            tax = gross * ml_tax / 100
            commission = gross * ml_commission / 100
            fixed = units * ml_fixed_fee
            total_tax += tax
            total_commission += commission
            total_fixed += fixed
            rows.append({
                "ad_id": item["ad_id"], "produto_nome": item["produto_nome"],
                "variacao_nome": item["variacao_nome"], "sku": item["sku"],
                "unidades": units, "faturamento": brl(gross), "imposto": brl(tax),
                "comissao": brl(commission), "taxa_fixa": brl(fixed),
                "custo": "Pendente", "lucro": "Pendente", "margem": "—",
            })

        self.table.set_rows(rows)
        gross_total = float(preview["faturamento"])
        net = gross_total - total_tax - total_commission - total_fixed
        self.cards["faturamento"].set_value(brl(gross_total))
        self.cards["unidades"].set_value(str(preview["unidades"]))
        self.cards["imposto"].set_value(brl(total_tax))
        self.cards["comissao"].set_value(brl(total_commission))
        self.cards["taxa_fixa"].set_value(brl(total_fixed))
        self.cards["liquido_sem_custo"].set_value(brl(net))
        self.summary_var.set(
            f"Planilha válida | {preview['data_inicio'].isoformat()} até {preview['data_fim'].isoformat()} | "
            f"{preview['count']} anúncios com vendas | {preview['unidades']} unidades | faturamento {brl(gross_total)}."
        )
        self.status_var.set(
            f"Taxas ML configuradas: {ml_tax:g}% imposto + {ml_commission:g}% comissão + R$ {ml_fixed_fee:.2f}/un. "
            "O custo e o lucro por produto ficam pendentes até o cadastro do custo."
        )

    def confirm(self) -> None:
        path = self.file_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha a planilha primeiro.")
            return
        try:
            preview = preview_mercadolivre(path)
            start, end = preview["data_inicio"], preview["data_fim"]
            self.start_var.set(start.isoformat())
            self.end_var.set(end.isoformat())
        except Exception as exc:
            messagebox.showerror("Erro ao validar planilha", str(exc))
            return

        try:
            duplicates = find_ml_importations_same_period(start, end)
            if duplicates:
                answer = messagebox.askyesno(
                    "Período já importado",
                    "Já existe uma importação do Mercado Livre para este período.\n\n"
                    "Substituir a importação anterior e manter apenas esta versão?",
                )
                if not answer:
                    return
            result = save_mercadolivre_importation(path, start, end, replace_same_period=True)
        except Exception as exc:
            messagebox.showerror("Erro ao importar Mercado Livre", str(exc))
            return

        self._render_preview(preview)
        messagebox.showinfo(
            "Mercado Livre",
            f"Importação concluída.\n\n{result['inserted']} anúncios/vendas incorporados ao DRE.\n"
            f"Faturamento: {brl(result['faturamento'])}\n"
            f"Custos pendentes: {result['incomplete']}\n\n"
            "Os anúncios foram criados/atualizados no cadastro de produtos e podem receber custo normalmente.",
        )
        self.status_var.set("Mercado Livre incorporado ao DRE e ao cadastro de produtos.")
