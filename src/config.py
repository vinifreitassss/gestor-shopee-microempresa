from pathlib import Path

APP_NAME = "Gestor Shopee Microempresa"
APP_VERSION = "0.1.0"

DATA_DIR = Path.home() / ".gestor_shopee_microempresa"
DB_PATH = DATA_DIR / "gestor.db"

DEFAULT_SETTINGS = {
    # Shopee
    "imposto_percentual": "9",
    "comissao_percentual": "22",
    "taxa_fixa_unidade": "5",
    # Mercado Livre: mantemos uma configuração separada para não aplicar
    # automaticamente as taxas da Shopee aos anúncios do ML.
    "ml_imposto_percentual": "9",
    "ml_comissao_percentual": "22",
    "ml_taxa_fixa_unidade": "8",
}

PERIOD_TYPES = ("diario", "mensal", "personalizado")
