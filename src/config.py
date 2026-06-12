from pathlib import Path

APP_NAME = "Gestor Shopee Microempresa"
APP_VERSION = "0.1.0"

DATA_DIR = Path.home() / ".gestor_shopee_microempresa"
DB_PATH = DATA_DIR / "gestor.db"

DEFAULT_SETTINGS = {
    "imposto_percentual": "9",
    "comissao_percentual": "22",
    "taxa_fixa_unidade": "5",
}

PERIOD_TYPES = ("diario", "mensal", "personalizado")
