import customtkinter as ctk

from src.config import APP_NAME, APP_VERSION
from src.ui.theme import SIDEBAR_WIDTH, apply_theme
from src.ui.views.cancellations_view import CancellationsView
from src.ui.views.cashflow_view import CashFlowView
from src.ui.views.costs_view import CostsView
from src.ui.views.dashboard_view import DashboardView
from src.ui.views.dre_view import DreView
from src.ui.views.expenses_view import ExpensesView
from src.ui.views.import_view import ImportView
from src.ui.views.inputs_view import InputsView
from src.ui.views.launcher_view import LauncherView
from src.ui.views.products_view import ProductsView
from src.ui.views.settings_view import SettingsView


VIEWS = {
    "Dashboard": DashboardView,
    "Central de Automações": LauncherView,
    "Importações": ImportView,
    "Produtos": ProductsView,
    "Custos": CostsView,
    "Insumos / Estoque": InputsView,
    "Despesas": ExpensesView,
    "Fluxo de Caixa": CashFlowView,
    "Cancelamentos": CancellationsView,
    "Resultado Operacional": DreView,
    "Configurações": SettingsView,
}


class GestorApp(ctk.CTk):
    def __init__(self):
        apply_theme()
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1180x720")
        self.minsize(1050, 650)
        self.views = {}

        self.sidebar = ctk.CTkFrame(self, width=SIDEBAR_WIDTH, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.content = ctk.CTkFrame(self, corner_radius=0)
        self.content.pack(side="right", fill="both", expand=True)

        self._build_sidebar()
        self.show_view("Dashboard")

    def _build_sidebar(self) -> None:
        ctk.CTkLabel(
            self.sidebar,
            text="Gestor Shopee",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(20, 8), padx=16, anchor="w")
        ctk.CTkLabel(self.sidebar, text="Microempresa", text_color="gray").pack(pady=(0, 18), padx=16, anchor="w")

        for item in VIEWS:
            ctk.CTkButton(
                self.sidebar,
                text=item,
                anchor="w",
                command=lambda name=item: self.show_view(name),
            ).pack(fill="x", padx=12, pady=5)

    def show_view(self, name: str) -> None:
        for child in self.content.winfo_children():
            child.pack_forget()

        if name not in self.views:
            self.views[name] = VIEWS[name](self.content)

        view = self.views[name]
        if hasattr(view, "refresh"):
            view.refresh()
        view.pack(fill="both", expand=True)
