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
    "Vendas / desempenho": "performance",
    "Pedidos enviados": "pedidos_enviados",
    "Pagamentos / saques Shopee": "pagamentos_shopee",
}


class ImportView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        yesterday = date.today() - timedelta(days=1)
        self.file_path_var = ctk.StringVar(value="")
        self.report_label_var = ctk.StringVar(value="Vendas / desempenho")
        self.tipo_var = ctk.StringVar(value="diario")
        self.data_inicio_var = ctk.StringVar(value=yesterday.isoformat())
        self.data_fim_var = ctk.StringVar(value=yesterday.isoformat())
        self.status_var = ctk.StringVar(value="Nenhuma planilha selecionada.")
        self.preview_lines = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Importações Shopee", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)

        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=(0, PAD))

        ctk.CTkButton(box, text="Escolher planilha", command=self.choose_file).grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkEntry(box, textvariable=self.file_path_var, width=520).grid(row=0, column=1, columnspan=5, padx=8, pady=8, sticky="ew")

        ctk.CTkLabel(box, text="Relatório:").grid(row=1, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkOptionMenu(box, variable=self.report_label_var, values=list(REPORT_OPTIONS.keys())).grid(row=1, column=1, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(box, text="Tipo:").grid(row=1, column=2, padx=8, pady=8, sticky="e")
        ctk.CTkOptionMenu(box, variable=self.tipo_var, values=["diario", "mensal", "personalizado"]).grid(row=1, column=3, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(box, text="Data início:").grid(row=1, column=4, padx=8, pady=8, sticky="e")
        ctk.CTkEntry(box, textvariable=self.data_inicio_var, width=120).grid(row=1, column=5, padx=8, pady=8)
        ctk.CTkLabel(box, text="Data fim/envio:").grid(row=1, column=6, padx=8, pady=8, sticky="e")
        ctk.CTkEntry(box, textvariable=self.data_fim_var, width=120).grid(row=1, column=7, padx=8, pady=8)

        ctk.CTkButton(box, text="Pré-visualizar", command=self.preview).grid(row=2, column=0, padx=8, pady=8)
        ctk.CTkButton(box, text="Confirmar importação", command=self.confirm_import).grid(row=2, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkButton(box, text="Excluir selecionada", command=self.delete_selected_importation).grid(row=2, column=2, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, textvariable=self.status_var).grid(row=2, column=3, columnspan=5, padx=8, pady=8, sticky="w")
        box.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Prévia da planilha", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        self.preview_table = SimpleTable(self, [("pedido_id", "Pedido / Produto", 180), ("status", "Status", 160), ("data", "Data", 140), ("valor", "Valor bruto", 130), ("liquido", "Líquido / saldo", 130), ("obs", "Obs.", 190)], height=9)
        self.preview_table.pack(fill="both", expand=True, padx=PAD, pady=(6, PAD))

        ctk.CTkLabel(self, text="Importações recentes", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        self.history_table = SimpleTable(self, [("id", "ID", 60), ("arquivo_nome", "Arquivo", 240), ("tipo_relatorio", "Relatório", 150), ("tipo_periodo", "Tipo", 100), ("data_inicio", "Início", 100), ("data_fim", "Fim", 100), ("mes_referencia", "Mês", 90), ("status", "Status", 100), ("criado_em", "Criado em", 150)], height=6)
        self.history_table.pack(fill="both", padx=PAD, pady=(6, PAD))

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(title="Escolha a planilha Shopee", filetypes=[("Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")])
        if path:
            self.file_path_var.set(path)
            self.status_var.set(f"Selecionado: {Path(path).name}")

    def _report_type(self) -> str:
        return REPORT_OPTIONS[self.report_label_var.get()]

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
            rows.append({"pedido_id": line.produto_nome, "status": line.variacao_nome, "data": "", "valor": brl(line.vendas_pedido_pago), "liquido": "", "obs": f"{line.unidades_pedido_pago} un."})
        self.preview_table.set_rows(rows)
        self.status_var.set(f"{len(rows)} variações vendidas encontradas.")

    def _preview_financial(self, path: str, report_type: str, data_envio_real: date) -> None:
        preview = preview_financial_importation(path, report_type, data_envio_real=data_envio_real)
        rows = [{**row, "valor": brl(row.get("valor")), "liquido": brl(row.get("liquido"))} for row in preview["rows"]]
        self.preview_table.set_rows(rows)
        if report_type == "pedidos_enviados":
            self.status_var.set(f"{preview['count']} pedidos únicos. Com rastreio: {preview.get('pedidos_com_rastreio', 0)}. Sem rastreio: {preview.get('pedidos_sem_rastreio', 0)}. Aberto futuro líquido: {brl(preview.get('saldo_possivel_aberto', 0))}. Entra em espera: {brl(preview['valor_liquido'])}.")
        else:
            self.status_var.set(f"{preview['count']} transações. Entradas: {brl(preview['valor_total'])}. Saques: {brl(preview['taxas'])}.")

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
        report_type = self._report_type()
        mes_ref = mes_referencia_from_date(data_inicio)
        mode = "somar"
        replaced_count = 0

        if tipo == "mensal":
            duplicates = find_importations_same_month(report_type, tipo, mes_ref)
            if duplicates:
                replace = messagebox.askyesno(
                    "Importação mensal já existe",
                    f"Já existe {len(duplicates)} importação mensal para esse relatório em {mes_ref}.\n\n"
                    "Sim = substituir a mensal anterior por esta nova\nNão = cancelar",
                )
                if not replace:
                    return
                for duplicate in duplicates:
                    delete_importation(int(duplicate["id"]))
                replaced_count = len(duplicates)
        else:
            duplicates = find_importations_same_period(tipo, data_inicio, data_fim) if report_type == "performance" else find_financial_importations_same_period(report_type, tipo, data_inicio, data_fim)
            if duplicates:
                replace = messagebox.askyesno("Importação já existe", "Já existe importação confirmada para esse tipo de relatório e período.\n\nSim = substituir anterior\nNão = cancelar")
                if not replace:
                    return
                for duplicate in duplicates:
                    delete_importation(int(duplicate["id"]))
                replaced_count = len(duplicates)

        try:
            if report_type == "performance":
                import_id = save_importation(path, tipo, data_inicio, data_fim, mode=mode)
            else:
                import_id = save_financial_importation(path, report_type, tipo, data_inicio, data_fim, mode=mode)
            message = f"Importação salva com ID {import_id}."
            if replaced_count:
                message += f"\n\nSubstituiu {replaced_count} importação(ões) anterior(es)."
            messagebox.showinfo("Importação concluída", message)
            self.status_var.set(message.replace("\n", " "))
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível importar:\n{exc}")

    def delete_selected_importation(self) -> None:
        selected = self.history_table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione uma importação na tabela de histórico.")
            return
        try:
            importacao_id = int(selected[0])
        except (TypeError, ValueError):
            messagebox.showerror("Erro", "Não consegui identificar o ID da importação selecionada.")
            return
        confirm = messagebox.askyesno("Excluir importação", f"Excluir a importação ID {importacao_id}?\n\nOs dados gerados por essa planilha serão removidos do sistema.")
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
        self.status_var.set(f"Importação ID {importacao_id} excluída.")
        self.refresh()

    def refresh(self) -> None:
        rows = list_importations()
        self.history_table.set_rows(rows)
