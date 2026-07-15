from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

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
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, mes_referencia_from_date


REPORT_OPTIONS = {
    "parentskudetail - Vendas/desempenho": "performance",
    "Order.toship - Pedidos a enviar": "pedidos_enviados",
    "my_balance - Pagamentos/saques Shopee": "pagamentos_shopee",
}

HISTORY_TABS = {
    "parentskudetail": "performance",
    "Order.toship": "pedidos_enviados",
    "my_balance": "pagamentos_shopee",
}

REPORT_HINTS = {
    "performance": (
        "Arquivo parentskudetail: alimenta DRE, produtos, variações, ranking e custos. "
        "Não mexe no Fluxo de Caixa."
    ),
    "pedidos_enviados": (
        "Arquivo Order.toship: snapshot diário dos pedidos ainda a enviar. "
        "Pedidos que aparecem nele ficam em Aberto futuro. Pedidos abertos que somem no próximo snapshot são consolidados como Shopee em espera."
    ),
    "pagamentos_shopee": (
        "Arquivo my_balance: alimenta a conciliação financeira. "
        "Entradas reduzem Shopee em espera e aumentam Caixa Shopee; saques movem Caixa Shopee para Banco; débitos reduzem Caixa Shopee."
    ),
}

HISTORY_COLUMNS = [
    ("id", "ID", 60),
    ("arquivo_nome", "Arquivo", 270),
    ("tipo_periodo", "Tipo", 100),
    ("data_inicio", "Início", 100),
    ("data_fim", "Fim", 100),
    ("mes_referencia", "Mês", 90),
    ("status", "Status", 100),
    ("criado_em", "Criado em", 155),
]


class ImportView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        yesterday = date.today() - timedelta(days=1)
        self.file_path_var = ctk.StringVar(value="")
        self.report_label_var = ctk.StringVar(value="parentskudetail - Vendas/desempenho")
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

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Central de Importações Shopee", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)

        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=(0, PAD))
        box.grid_columnconfigure(1, weight=1)
        box.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(box, text="Escolher planilha", command=self.choose_file).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.file_path_var, width=760).grid(row=0, column=1, columnspan=3, padx=8, pady=8, sticky="ew")

        ctk.CTkLabel(box, text="Tipo de arquivo:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=8, pady=8, sticky="w")
        self.report_menu = ctk.CTkOptionMenu(
            box,
            variable=self.report_label_var,
            values=list(REPORT_OPTIONS.keys()),
            width=300,
            command=lambda _value: self.update_import_summary(),
        )
        self.report_menu.grid(row=1, column=1, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(box, text="Período:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=2, padx=8, pady=8, sticky="e")
        self.tipo_menu = ctk.CTkOptionMenu(
            box,
            variable=self.tipo_var,
            values=["diario", "mensal", "personalizado"],
            width=180,
            command=lambda _value: self.update_import_summary(),
        )
        self.tipo_menu.grid(row=1, column=3, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(box, text="Data início:").grid(row=2, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.data_inicio_var, width=140).grid(row=2, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, text="Data fim / envio:").grid(row=2, column=2, padx=8, pady=8, sticky="e")
        ctk.CTkEntry(box, textvariable=self.data_fim_var, width=140).grid(row=2, column=3, padx=8, pady=8, sticky="w")

        action_row = ctk.CTkFrame(box)
        action_row.grid(row=3, column=0, columnspan=4, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(action_row, text="Pré-visualizar", command=self.preview).pack(side="left", padx=(0, 8), pady=4)
        ctk.CTkButton(action_row, text="Confirmar e plugar no app", command=self.confirm_import).pack(side="left", padx=8, pady=4)
        ctk.CTkButton(action_row, text="Excluir selecionada da aba atual", command=self.delete_selected_importation).pack(side="left", padx=8, pady=4)
        ctk.CTkLabel(action_row, textvariable=self.status_var, text_color="gray", wraplength=560, justify="left").pack(side="left", padx=16, pady=4)

        ctk.CTkLabel(
            box,
            textvariable=self.summary_var,
            text_color="#f6c343",
            font=ctk.CTkFont(size=13, weight="bold"),
            wraplength=980,
            justify="left",
        ).grid(row=4, column=0, columnspan=4, padx=8, pady=(0, 10), sticky="w")

        ctk.CTkLabel(self, text="Prévia da planilha", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        self.preview_table = SimpleTable(
            self,
            [
                ("pedido_id", "Pedido / Produto", 180),
                ("status", "Status", 160),
                ("data", "Data", 140),
                ("valor", "Valor bruto", 130),
                ("liquido", "Líquido / saldo", 130),
                ("obs", "Obs.", 260),
            ],
            height=8,
        )
        self.preview_table.pack(fill="both", expand=True, padx=PAD, pady=(6, PAD))

        ctk.CTkLabel(self, text="Importações separadas por arquivo", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        self.history_tabs = ctk.CTkTabview(self)
        self.history_tabs.pack(fill="both", expand=True, padx=PAD, pady=(6, PAD))
        for tab_name, report_type in HISTORY_TABS.items():
            tab = self.history_tabs.add(tab_name)
            ctk.CTkLabel(tab, text=REPORT_HINTS[report_type], text_color="gray", wraplength=980, justify="left").pack(anchor="w", padx=8, pady=(8, 4))
            table = SimpleTable(tab, HISTORY_COLUMNS, height=7)
            table.pack(fill="both", expand=True, padx=8, pady=8)
            self.history_tables[report_type] = table

    def _bind_summary_updates(self) -> None:
        for var in (self.file_path_var, self.report_label_var, self.tipo_var, self.data_inicio_var, self.data_fim_var):
            var.trace_add("write", lambda *_: self.update_import_summary())

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(title="Escolha a planilha Shopee", filetypes=[("Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")])
        if path:
            self.file_path_var.set(path)
            self._suggest_report_type_from_filename(Path(path).name)
            self.status_var.set(f"Selecionado: {Path(path).name}")
            self.update_import_summary()

    def _suggest_report_type_from_filename(self, filename: str) -> None:
        lowered = filename.lower()
        if "parentskudetail" in lowered or "parent" in lowered:
            self.report_label_var.set("parentskudetail - Vendas/desempenho")
        elif "order.toship" in lowered or "toship" in lowered or "to ship" in lowered:
            self.report_label_var.set("Order.toship - Pedidos a enviar")
        elif "balance" in lowered or "my_balance" in lowered or "transaction" in lowered:
            self.report_label_var.set("my_balance - Pagamentos/saques Shopee")

    def _report_type(self) -> str:
        return REPORT_OPTIONS[self.report_label_var.get()]

    def update_import_summary(self) -> None:
        path = self.file_path_var.get().strip()
        arquivo = Path(path).name if path else "nenhuma planilha escolhida"
        report_label = self.report_label_var.get()
        report_type = REPORT_OPTIONS.get(report_label, "performance")
        tipo = self.tipo_var.get().strip()
        data_inicio = self.data_inicio_var.get().strip()
        data_fim = self.data_fim_var.get().strip()
        self.summary_var.set(
            "Esta planilha será plugada no app como: "
            f"{report_label} | período {tipo} | de {data_inicio} até {data_fim} | arquivo: {arquivo}\n"
            f"Efeito: {REPORT_HINTS.get(report_type, '')}"
        )

    def preview(self) -> None:
        path = self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha uma planilha primeiro.")
            return
        report_type = self._report_type()
        try:
            if report_type == "performance":
                self._preview_performance(path)
            else:
                data_fim = date.fromisoformat(self.data_fim_var.get().strip())
                self._preview_financial(path, report_type, data_fim)
        except ShopeeImportError as exc:
            messagebox.showerror("Erro ao ler planilha", str(exc))
        except ValueError:
            messagebox.showerror("Data inválida", "Use o formato AAAA-MM-DD, exemplo: 2026-06-11.")

    def _preview_performance(self, path: str) -> None:
        self.preview_lines = ShopeeImporter().preview(path)
        rows = []
        for line in self.preview_lines:
            if not line.contabilizar:
                continue
            rows.append({"pedido_id": line.produto_nome, "status": line.variacao_nome, "data": "", "valor": brl(line.vendas_pedido_pago), "liquido": "", "obs": f"{line.unidades_pedido_pago} un. | DRE/produtos"})
        self.preview_table.set_rows(rows)
        self.status_var.set(f"{len(rows)} variações vendidas encontradas. Impacto: DRE/produtos, sem fluxo de caixa.")

    def _preview_financial(self, path: str, report_type: str, data_envio_real: date) -> None:
        preview = preview_financial_importation(path, report_type, data_envio_real=data_envio_real)
        rows = [{**row, "valor": brl(row.get("valor")), "liquido": brl(row.get("liquido"))} for row in preview["rows"]]
        self.preview_table.set_rows(rows)
        if report_type == "pedidos_enviados":
            self.status_var.set(
                f"{preview['count']} pedidos no snapshot. Aberto futuro: {brl(preview.get('saldo_possivel_aberto', 0))}. "
                "Pedidos que sumirem no próximo snapshot são consolidados como Shopee em espera."
            )
        else:
            self.status_var.set(
                f"{preview['count']} transações. Entradas: {brl(preview['valor_total'])}. "
                f"Saques: {brl(preview.get('saques', preview.get('taxas', 0)))}. "
                f"Ads: {brl(preview.get('ads', 0))}. Ajustes: {brl(preview.get('ajustes_pedido', 0))}."
            )

    def confirm_import(self) -> None:
        path = self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha uma planilha primeiro.")
            return
        try:
            data_inicio = date.fromisoformat(self.data_inicio_var.get().strip())
            data_fim = date.fromisoformat(self.data_fim_var.get().strip())
        except ValueError:
            messagebox.showerror("Data inválida", "Use o formato AAAA-MM-DD, exemplo: 2026-06-11.")
            return

        tipo = self.tipo_var.get().strip()
        report_label = self.report_label_var.get()
        report_type = self._report_type()
        mes_ref = mes_referencia_from_date(data_inicio)
        mode = "somar"
        duplicates = []

        if report_type == "pedidos_enviados":
            replacement_text = (
                "\n\nModo snapshot diário: esta planilha preserva o histórico e atualiza a posição dos pedidos. "
                "Não apague snapshots antigos sem necessidade, porque eles ajudam a identificar pedidos que saíram da lista a enviar."
            )
        else:
            if tipo == "mensal":
                duplicates = find_importations_same_month(report_type, tipo, mes_ref)
            else:
                duplicates = find_importations_same_period(tipo, data_inicio, data_fim) if report_type == "performance" else find_financial_importations_same_period(report_type, tipo, data_inicio, data_fim)
            replacement_text = ""
            if duplicates:
                replacement_text = f"\n\nAtenção: serão substituída(s) {len(duplicates)} importação(ões) anterior(es) desse mesmo tipo/período."

        ok = messagebox.askyesno(
            "Confirmar importação",
            "Deseja plugar esta planilha no app?\n\n"
            f"Arquivo: {Path(path).name}\n"
            f"Tipo de arquivo: {report_label}\n"
            f"Período: {tipo}\n"
            f"Data início: {data_inicio.isoformat()}\n"
            f"Data fim/envio: {data_fim.isoformat()}\n"
            f"Mês de referência: {mes_ref}"
            f"{replacement_text}",
        )
        if not ok:
            return

        replaced_count = 0
        for duplicate in duplicates:
            delete_importation(int(duplicate["id"]))
            replaced_count += 1

        try:
            if report_type == "performance":
                import_id = save_importation(path, tipo, data_inicio, data_fim, mode=mode)
            else:
                import_id = save_financial_importation(path, report_type, tipo, data_inicio, data_fim, mode=mode)
            message = f"Importação salva com ID {import_id}."
            if report_type == "pedidos_enviados":
                message += "\n\nSnapshot diário consolidado."
            if replaced_count:
                message += f"\n\nSubstituiu {replaced_count} importação(ões) anterior(es)."
            messagebox.showinfo("Importação concluída", message)
            self.status_var.set(message.replace("\n", " "))
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível importar:\n{exc}")

    def delete_selected_importation(self) -> None:
        current_tab = self.history_tabs.get()
        report_type = HISTORY_TABS.get(current_tab)
        table = self.history_tables.get(report_type)
        if not table:
            messagebox.showwarning("Atenção", "Não consegui identificar a aba atual.")
            return
        selected = table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", f"Selecione uma importação na aba {current_tab}.")
            return
        try:
            importacao_id = int(selected[0])
        except (TypeError, ValueError):
            messagebox.showerror("Erro", "Não consegui identificar o ID da importação selecionada.")
            return
        confirm = messagebox.askyesno(
            "Excluir importação",
            f"Excluir a importação ID {importacao_id} da aba {current_tab}?\n\n"
            "Os dados gerados por essa planilha serão removidos do sistema.",
        )
        if not confirm:
            return
        try:
            deleted = delete_importation(importacao_id)
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível excluir:\n{exc}")
            return
        if not deleted:
            messagebox.showwarning("Atenção", "Importação não encontrada.")
            return
        self.status_var.set(f"Importação ID {importacao_id} excluída da aba {current_tab}.")
        self.refresh()

    def refresh(self) -> None:
        rows = list_importations()
        grouped = {report_type: [] for report_type in HISTORY_TABS.values()}
        for row in rows:
            report_type = row.get("tipo_relatorio")
            if report_type in grouped:
                grouped[report_type].append(row)
        for report_type, table in self.history_tables.items():
            table.set_rows(grouped.get(report_type, []))
