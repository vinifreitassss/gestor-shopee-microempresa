from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.database import fetch_all
from src.importer import ShopeeImportError, ShopeeImporter
from src.services.financial_import_service import (
    find_financial_importations_same_period,
    preview_financial_importation,
    save_financial_importation,
)
from src.services.import_service import (
    delete_importation,
    find_importations_same_month,
    find_importations_same_period,
    list_importations,
    save_importation,
)
from src.services.mercadolivre_import_service import (
    find_ml_importations_same_period,
    preview_mercadolivre,
    save_mercadolivre_importation,
)
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, mes_referencia_from_date


REPORT_OPTIONS = {
    "parentskudetail - Vendas/desempenho Shopee": "performance",
    "Mercado Livre - Vendas/desempenho": "mercadolivre_performance",
    "Order.toship - Pedidos a enviar Shopee": "pedidos_enviados",
    "my_balance - Pagamentos/saques Shopee": "pagamentos_shopee",
}

HISTORY_TABS = {
    "parentskudetail": "performance",
    "Mercado Livre": "mercadolivre_performance",
    "Order.toship": "pedidos_enviados",
    "my_balance": "pagamentos_shopee",
}

REPORT_HINTS = {
    "performance": "Vendas/desempenho Shopee: alimenta DRE, produtos, variações, ranking e custos.",
    "mercadolivre_performance": "Vendas/desempenho Mercado Livre: alimenta o mesmo DRE, mas usa 9% imposto + 22% comissão + R$8 por unidade.",
    "pedidos_enviados": "Snapshot diário dos pedidos Shopee ainda a enviar. Preserva o histórico da esteira.",
    "pagamentos_shopee": "Carteira Shopee: concilia entradas, saques, débitos e Shopee Ads.",
}

HISTORY_COLUMNS = [
    ("id", "ID", 60), ("arquivo_nome", "Arquivo", 270), ("tipo_periodo", "Tipo", 100),
    ("data_inicio", "Início", 100), ("data_fim", "Fim", 100), ("mes_referencia", "Mês", 90),
    ("status", "Status", 100), ("criado_em", "Criado em", 155),
]


class ImportView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        yesterday = date.today() - timedelta(days=1)
        self.file_path_var = ctk.StringVar(value="")
        self.report_label_var = ctk.StringVar(value="parentskudetail - Vendas/desempenho Shopee")
        self.tipo_var = ctk.StringVar(value="diario")
        self.data_inicio_var = ctk.StringVar(value=yesterday.isoformat())
        self.data_fim_var = ctk.StringVar(value=yesterday.isoformat())
        self.status_var = ctk.StringVar(value="Nenhuma planilha selecionada.")
        self.summary_var = ctk.StringVar(value="Escolha uma planilha e confira o tipo antes de confirmar.")
        self.history_tables = {}
        self.preview_lines = []
        self._build()
        self._bind_summary_updates()
        self.update_import_summary()
        self.refresh()

    def _build(self):
        ctk.CTkLabel(self, text="Central de Importações", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=(0, PAD))
        box.grid_columnconfigure(1, weight=1); box.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(box, text="Escolher planilha", command=self.choose_file).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.file_path_var, width=760).grid(row=0, column=1, columnspan=3, padx=8, pady=8, sticky="ew")
        ctk.CTkLabel(box, text="Tipo de arquivo:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=8, pady=8, sticky="w")
        self.report_menu = ctk.CTkOptionMenu(box, variable=self.report_label_var, values=list(REPORT_OPTIONS), width=330, command=lambda _: self.update_import_summary())
        self.report_menu.grid(row=1, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, text="Período:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=2, padx=8, pady=8, sticky="e")
        self.tipo_menu = ctk.CTkOptionMenu(box, variable=self.tipo_var, values=["diario", "mensal", "personalizado"], width=180, command=lambda _: self.update_import_summary())
        self.tipo_menu.grid(row=1, column=3, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, text="Data início:").grid(row=2, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.data_inicio_var, width=140).grid(row=2, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, text="Data fim / envio:").grid(row=2, column=2, padx=8, pady=8, sticky="e")
        ctk.CTkEntry(box, textvariable=self.data_fim_var, width=140).grid(row=2, column=3, padx=8, pady=8, sticky="w")

        actions = ctk.CTkFrame(box); actions.grid(row=3, column=0, columnspan=4, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(actions, text="Pré-visualizar", command=self.preview).pack(side="left", padx=(0, 8), pady=4)
        ctk.CTkButton(actions, text="Confirmar e plugar no app", command=self.confirm_import).pack(side="left", padx=8, pady=4)
        ctk.CTkButton(actions, text="Excluir selecionada", command=self.delete_selected_importation).pack(side="left", padx=8, pady=4)
        ctk.CTkButton(actions, text="Apagar TODAS da aba", command=self.delete_all_current_tab).pack(side="left", padx=8, pady=4)
        ctk.CTkLabel(actions, textvariable=self.status_var, text_color="gray", wraplength=420, justify="left").pack(side="left", padx=16, pady=4)
        ctk.CTkLabel(box, textvariable=self.summary_var, text_color="#f6c343", font=ctk.CTkFont(size=13, weight="bold"), wraplength=980, justify="left").grid(row=4, column=0, columnspan=4, padx=8, pady=(0, 10), sticky="w")

        ctk.CTkLabel(self, text="Prévia da planilha", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        self.preview_table = SimpleTable(self, [
            ("pedido_id", "Pedido / Produto", 230), ("status", "Variação / Status", 180), ("data", "Data", 120),
            ("valor", "Valor bruto", 130), ("liquido", "Líquido / saldo", 130), ("obs", "Obs.", 300),
        ], height=8)
        self.preview_table.pack(fill="both", expand=True, padx=PAD, pady=(6, PAD))

        ctk.CTkLabel(self, text="Importações separadas por arquivo", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        self.history_tabs = ctk.CTkTabview(self); self.history_tabs.pack(fill="both", expand=True, padx=PAD, pady=(6, PAD))
        for tab_name, report_type in HISTORY_TABS.items():
            tab = self.history_tabs.add(tab_name)
            ctk.CTkLabel(tab, text=REPORT_HINTS[report_type], text_color="gray", wraplength=980, justify="left").pack(anchor="w", padx=8, pady=(8, 4))
            table = SimpleTable(tab, HISTORY_COLUMNS, height=7); table.pack(fill="both", expand=True, padx=8, pady=8)
            self.history_tables[report_type] = table

    def _bind_summary_updates(self):
        for var in (self.file_path_var, self.report_label_var, self.tipo_var, self.data_inicio_var, self.data_fim_var):
            var.trace_add("write", lambda *_: self.update_import_summary())

    def choose_file(self):
        path = filedialog.askopenfilename(title="Escolha a planilha", filetypes=[("Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")])
        if not path: return
        self.file_path_var.set(path)
        self._suggest_report_type(Path(path))
        self.status_var.set(f"Selecionado: {Path(path).name}")

    def _suggest_report_type(self, path: Path):
        lowered = path.name.lower().replace("_", " ").replace("-", " ")
        if ShopeeImporter._looks_like_mercadolivre(path):
            self.report_label_var.set("Mercado Livre - Vendas/desempenho")
        elif "parentskudetail" in lowered or "parent" in lowered:
            self.report_label_var.set("parentskudetail - Vendas/desempenho Shopee")
        elif "order.toship" in lowered or "toship" in lowered or "to ship" in lowered:
            self.report_label_var.set("Order.toship - Pedidos a enviar Shopee")
        elif "balance" in lowered or "my_balance" in lowered or "transaction" in lowered:
            self.report_label_var.set("my_balance - Pagamentos/saques Shopee")

    def _report_type(self):
        return REPORT_OPTIONS[self.report_label_var.get()]

    def _current_history_context(self):
        tab = self.history_tabs.get(); report_type = HISTORY_TABS.get(tab, "")
        return tab, report_type, self.history_tables.get(report_type)

    def update_import_summary(self):
        path = self.file_path_var.get().strip(); arquivo = Path(path).name if path else "nenhuma planilha escolhida"
        report_type = REPORT_OPTIONS.get(self.report_label_var.get(), "performance")
        self.summary_var.set(
            "Esta planilha será plugada no app como: " + f"{self.report_label_var.get()} | período {self.tipo_var.get()} | de {self.data_inicio_var.get()} até {self.data_fim_var.get()} | arquivo: {arquivo}\n" +
            f"Efeito: {REPORT_HINTS.get(report_type, '')}"
        )

    def preview(self):
        path = self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha uma planilha primeiro."); return
        report_type = self._report_type()
        try:
            if report_type == "performance":
                self._preview_shopee(path)
            elif report_type == "mercadolivre_performance":
                self._preview_ml(path)
            else:
                self._preview_financial(path, report_type, date.fromisoformat(self.data_fim_var.get().strip()))
        except (ShopeeImportError, ValueError) as exc:
            messagebox.showerror("Erro ao ler planilha", str(exc))

    def _preview_shopee(self, path):
        self.preview_lines = ShopeeImporter().preview(path); rows = []
        for line in self.preview_lines:
            if line.contabilizar:
                rows.append({"pedido_id": line.produto_nome, "status": line.variacao_nome, "data": "", "valor": brl(line.vendas_pedido_pago), "liquido": "", "obs": f"{line.unidades_pedido_pago} un. | DRE/produtos"})
        self.preview_table.set_rows(rows); self.status_var.set(f"{len(rows)} variações/produtos vendidos encontrados.")

    def _preview_ml(self, path):
        preview = preview_mercadolivre(path); rows = []
        for row in preview["rows"]:
            rows.append({"pedido_id": row["produto_nome"], "status": row.get("variacao_nome") or "Sem variação", "data": f"{preview['data_inicio']} a {preview['data_fim']}", "valor": brl(row["faturamento"]), "liquido": "", "obs": f"{row['unidades']} un. | ML | 22% + R$8/un."})
        self.preview_table.set_rows(rows); self.status_var.set(f"{len(rows)} produtos do Mercado Livre encontrados. Faturamento: {brl(preview['faturamento'])}.")

    def _preview_financial(self, path, report_type, data_envio_real):
        preview = preview_financial_importation(path, report_type, data_envio_real=data_envio_real)
        rows = [{**row, "valor": brl(row.get("valor")), "liquido": brl(row.get("liquido"))} for row in preview["rows"]]
        self.preview_table.set_rows(rows)
        if report_type == "pedidos_enviados":
            self.status_var.set(f"{preview['count']} pedidos no snapshot. Novos: {preview.get('novos', 0)}. Continuam: {preview.get('continuam', 0)}. Saíram: {preview.get('sairam_da_fila', 0)}. Aberto futuro: {brl(preview.get('saldo_possivel_aberto', 0))}.")
        else:
            self.status_var.set(f"{preview['count']} transações. Novas: {preview.get('novas', 0)}. Repetidas ignoradas: {preview.get('repetidas', 0)}. Entradas: {brl(preview['valor_total'])}. Ads: {brl(preview.get('ads', 0))}.")

    def confirm_import(self):
        path = self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha uma planilha primeiro."); return
        try:
            data_inicio = date.fromisoformat(self.data_inicio_var.get().strip()); data_fim = date.fromisoformat(self.data_fim_var.get().strip())
        except ValueError:
            messagebox.showerror("Data inválida", "Use AAAA-MM-DD."); return
        tipo = self.tipo_var.get().strip(); report_type = self._report_type(); mes_ref = mes_referencia_from_date(data_inicio)

        # O ML possui seu próprio histórico: nunca substitui nem apaga uma importação Shopee.
        if report_type == "mercadolivre_performance":
            duplicates = find_ml_importations_same_period(data_inicio, data_fim)
            replacement_text = f"\n\nSerá substituída a importação anterior do Mercado Livre desse mesmo período ({len(duplicates)} encontrada(s))." if duplicates else ""
        elif report_type == "pedidos_enviados":
            duplicates = []
            replacement_text = "\n\nModo snapshot diário: preserva o histórico da esteira."
        else:
            if tipo == "mensal":
                duplicates = find_importations_same_month(report_type, tipo, mes_ref)
            else:
                duplicates = find_importations_same_period(tipo, data_inicio, data_fim) if report_type == "performance" else find_financial_importations_same_period(report_type, tipo, data_inicio, data_fim)
            replacement_text = f"\n\nAtenção: serão substituída(s) {len(duplicates)} importação(ões) anterior(es) desse mesmo tipo/período." if duplicates else ""

        ok = messagebox.askyesno("Confirmar importação", "Deseja plugar esta planilha no app?\n\n" + f"Arquivo: {Path(path).name}\nTipo: {self.report_label_var.get()}\nPeríodo: {tipo}\nData início: {data_inicio}\nData fim: {data_fim}\nMês: {mes_ref}" + replacement_text)
        if not ok: return

        replaced_count = 0
        for duplicate in duplicates:
            if delete_importation(int(duplicate["id"])): replaced_count += 1
        try:
            if report_type == "mercadolivre_performance":
                result = save_mercadolivre_importation(path, data_inicio, data_fim, replace_same_period=False)
                import_id = result["importacao_id"]
            elif report_type == "performance":
                import_id = save_importation(path, tipo, data_inicio, data_fim, mode="somar")
            else:
                import_id = save_financial_importation(path, report_type, tipo, data_inicio, data_fim, mode="somar")
            message = f"Importação salva com ID {import_id}."
            if replaced_count: message += f"\n\nSubstituiu {replaced_count} importação(ões) anterior(es)."
            messagebox.showinfo("Importação concluída", message); self.status_var.set(message.replace("\n", " ")); self.refresh()
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível importar:\n{exc}")

    def delete_selected_importation(self):
        current_tab, report_type, table = self._current_history_context()
        if not table:
            messagebox.showwarning("Atenção", "Não consegui identificar a aba atual."); return
        selected = table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione uma importação na tabela."); return
        try: importacao_id = int(selected[0])
        except (TypeError, ValueError):
            messagebox.showerror("Erro", "Não consegui identificar o ID."); return
        if not messagebox.askyesno("Excluir importação", f"Excluir a importação ID {importacao_id}?\n\nOs dados gerados por essa planilha serão removidos."): return
        try:
            if delete_importation(importacao_id): self.status_var.set(f"Importação ID {importacao_id} excluída."); self.refresh()
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível excluir:\n{exc}")

    def delete_all_current_tab(self):
        current_tab, report_type, _ = self._current_history_context()
        if not report_type: return
        rows = fetch_all("SELECT id FROM importacoes WHERE tipo_relatorio = ? ORDER BY criado_em DESC", (report_type,))
        if not rows:
            messagebox.showinfo("Nada para apagar", f"A aba {current_tab} não tem importações."); return
        if not messagebox.askyesno("Apagar todas", f"Você vai apagar {len(rows)} importação(ões) da aba {current_tab}.\n\nContinuar?"): return
        for row in rows:
            try: delete_importation(int(row["id"]))
            except Exception: pass
        self.refresh(); self.status_var.set(f"Aba {current_tab}: importações apagadas.")

    def refresh(self):
        rows = list_importations(); grouped = {report_type: [] for report_type in HISTORY_TABS.values()}
        for row in rows:
            if row.get("tipo_relatorio") in grouped: grouped[row["tipo_relatorio"]].append(row)
        for report_type, table in self.history_tables.items(): table.set_rows(grouped.get(report_type, []))
