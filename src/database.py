import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable

from src.config import DATA_DIR, DB_PATH, DEFAULT_SETTINGS


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


@contextmanager
def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(sql: str, params: Iterable[Any] | None = None) -> None:
    with get_connection() as conn:
        conn.execute(sql, tuple(params or ()))


def fetch_all(sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return list(conn.execute(sql, tuple(params or ())).fetchall())


def fetch_one(sql: str, params: Iterable[Any] | None = None) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(sql, tuple(params or ())).fetchone()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row["name"] for row in columns}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS importacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arquivo_nome TEXT NOT NULL,
                caminho_arquivo TEXT,
                tipo_periodo TEXT NOT NULL,
                data_inicio TEXT NOT NULL,
                data_fim TEXT NOT NULL,
                mes_referencia TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmada',
                criado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS linhas_importadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                importacao_id INTEGER NOT NULL,
                id_item_shopee TEXT,
                produto_nome TEXT NOT NULL,
                id_variacao_shopee TEXT,
                variacao_nome TEXT,
                sku_variacao TEXT,
                vendas_pedido_pago REAL NOT NULL DEFAULT 0,
                unidades_pedido_pago INTEGER NOT NULL DEFAULT 0,
                tipo_linha TEXT NOT NULL,
                contabilizar INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (importacao_id) REFERENCES importacoes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS produtos_pai (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_item_shopee TEXT UNIQUE,
                nome TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS variacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                produto_pai_id INTEGER NOT NULL,
                id_variacao_shopee TEXT UNIQUE,
                nome_variacao TEXT NOT NULL,
                sku TEXT,
                tipo_produto TEXT NOT NULL DEFAULT 'pronto',
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL,
                FOREIGN KEY (produto_pai_id) REFERENCES produtos_pai(id)
            );

            CREATE TABLE IF NOT EXISTS custos_variacao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                variacao_id INTEGER NOT NULL,
                custo_unitario REAL NOT NULL,
                origem_custo TEXT NOT NULL DEFAULT 'manual',
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL,
                FOREIGN KEY (variacao_id) REFERENCES variacoes(id)
            );

            CREATE TABLE IF NOT EXISTS insumos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                unidade_uso TEXT NOT NULL,
                quantidade_total_uso REAL NOT NULL,
                custo_compra REAL NOT NULL,
                uso_minimo_por_pedido REAL NOT NULL,
                estoque_atual_uso REAL NOT NULL DEFAULT 0,
                valor_total_estoque REAL NOT NULL DEFAULT 0,
                referencia_uso_custo TEXT DEFAULT '',
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ficha_tecnica_insumos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                variacao_id INTEGER NOT NULL,
                insumo_id INTEGER NOT NULL,
                quantidade_usada REAL NOT NULL,
                criado_em TEXT NOT NULL,
                UNIQUE (variacao_id, insumo_id),
                FOREIGN KEY (variacao_id) REFERENCES variacoes(id) ON DELETE CASCADE,
                FOREIGN KEY (insumo_id) REFERENCES insumos(id)
            );

            CREATE TABLE IF NOT EXISTS vendas_contabilizadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                importacao_id INTEGER NOT NULL,
                produto_pai_id INTEGER NOT NULL,
                variacao_id INTEGER NOT NULL,
                data_inicio TEXT NOT NULL,
                data_fim TEXT NOT NULL,
                mes_referencia TEXT NOT NULL,
                unidades INTEGER NOT NULL,
                faturamento REAL NOT NULL,
                imposto_percentual REAL NOT NULL,
                comissao_percentual REAL NOT NULL,
                taxa_fixa_unitaria REAL NOT NULL,
                imposto_valor REAL NOT NULL,
                comissao_valor REAL NOT NULL,
                taxa_fixa_valor REAL NOT NULL,
                custo_unitario_usado REAL,
                custo_total REAL,
                lucro REAL,
                lucro_incompleto INTEGER NOT NULL DEFAULT 0,
                criado_em TEXT NOT NULL,
                FOREIGN KEY (importacao_id) REFERENCES importacoes(id) ON DELETE CASCADE,
                FOREIGN KEY (produto_pai_id) REFERENCES produtos_pai(id),
                FOREIGN KEY (variacao_id) REFERENCES variacoes(id)
            );

            CREATE TABLE IF NOT EXISTS despesas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                mes_referencia TEXT NOT NULL,
                categoria TEXT NOT NULL,
                descricao TEXT NOT NULL,
                valor REAL NOT NULL,
                recorrente_id INTEGER,
                criado_em TEXT NOT NULL,
                FOREIGN KEY (recorrente_id) REFERENCES despesas_recorrentes(id)
            );

            CREATE TABLE IF NOT EXISTS despesas_recorrentes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                descricao TEXT NOT NULL,
                valor_padrao REAL NOT NULL,
                dia_vencimento INTEGER NOT NULL DEFAULT 1,
                frequencia TEXT NOT NULL DEFAULT 'mensal',
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fechamentos_mensais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mes_referencia TEXT UNIQUE NOT NULL,
                faturamento_bruto REAL NOT NULL,
                impostos REAL NOT NULL,
                comissao REAL NOT NULL,
                taxa_fixa REAL NOT NULL,
                custo_produtos REAL NOT NULL,
                lucro_bruto REAL NOT NULL,
                despesas REAL NOT NULL,
                lucro_final REAL NOT NULL,
                margem_liquida REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'fechado',
                fechado_em TEXT NOT NULL
            );
            """
        )

        _ensure_column(conn, "insumos", "valor_total_estoque", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "insumos", "referencia_uso_custo", "TEXT DEFAULT ''")

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (chave, valor, atualizado_em)
                VALUES (?, ?, ?)
                """,
                (key, value, now_iso()),
            )
