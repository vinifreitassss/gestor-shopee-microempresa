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

            CREATE TABLE IF NOT EXISTS regras_custo_variacao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                variacao_id INTEGER NOT NULL UNIQUE,
                base_variacao_id INTEGER NOT NULL,
                multiplicador REAL NOT NULL DEFAULT 1,
                descricao TEXT DEFAULT '',
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
                FOREIGN KEY (variacao_id) REFERENCES variacoes(id) ON DELETE CASCADE,
                FOREIGN KEY (base_variacao_id) REFERENCES variacoes(id) ON DELETE CASCADE
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
                incide_dre INTEGER NOT NULL DEFAULT 1,
                recorrente_id INTEGER,
                origem_importacao_id INTEGER,
                origem_referencia TEXT DEFAULT '',
                criado_em TEXT NOT NULL,
                FOREIGN KEY (recorrente_id) REFERENCES despesas_recorrentes(id),
                FOREIGN KEY (origem_importacao_id) REFERENCES importacoes(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS despesas_recorrentes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                descricao TEXT NOT NULL,
                valor_padrao REAL NOT NULL,
                dia_vencimento INTEGER NOT NULL DEFAULT 1,
                incide_dre INTEGER NOT NULL DEFAULT 1,
                frequencia TEXT NOT NULL DEFAULT 'mensal',
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS shopee_pedidos_financeiros (
                pedido_id TEXT PRIMARY KEY,
                importacao_id INTEGER,
                status_pedido TEXT DEFAULT '',
                numero_rastreio TEXT DEFAULT '',
                data_criacao TEXT,
                data_pagamento TEXT,
                data_prevista_envio TEXT,
                data_envio_real TEXT,
                valor_total REAL NOT NULL DEFAULT 0,
                total_global REAL NOT NULL DEFAULT 0,
                taxa_transacao REAL NOT NULL DEFAULT 0,
                comissao_bruta REAL NOT NULL DEFAULT 0,
                comissao_liquida REAL NOT NULL DEFAULT 0,
                taxa_servico_bruta REAL NOT NULL DEFAULT 0,
                taxa_servico_liquida REAL NOT NULL DEFAULT 0,
                valor_liquido_estimado REAL NOT NULL DEFAULT 0,
                valor_pago_real REAL NOT NULL DEFAULT 0,
                data_liberacao_shopee TEXT,
                diferenca REAL NOT NULL DEFAULT 0,
                status_financeiro TEXT NOT NULL DEFAULT 'em_aberto',
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
                FOREIGN KEY (importacao_id) REFERENCES importacoes(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS shopee_itens_pedido (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id TEXT NOT NULL,
                importacao_id INTEGER,
                produto_nome TEXT NOT NULL,
                sku TEXT DEFAULT '',
                variacao_nome TEXT DEFAULT '',
                quantidade INTEGER NOT NULL DEFAULT 0,
                subtotal_produto REAL NOT NULL DEFAULT 0,
                criado_em TEXT NOT NULL,
                FOREIGN KEY (pedido_id) REFERENCES shopee_pedidos_financeiros(pedido_id) ON DELETE CASCADE,
                FOREIGN KEY (importacao_id) REFERENCES importacoes(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS shopee_transacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                importacao_id INTEGER,
                data_movimento TEXT NOT NULL,
                tipo_transacao TEXT NOT NULL,
                descricao TEXT DEFAULT '',
                pedido_id TEXT,
                direcao TEXT DEFAULT '',
                valor REAL NOT NULL DEFAULT 0,
                status TEXT DEFAULT '',
                balanca_apos_transacoes REAL NOT NULL DEFAULT 0,
                valor_ajustado REAL NOT NULL DEFAULT 0,
                status_conciliacao TEXT NOT NULL DEFAULT 'pendente',
                criado_em TEXT NOT NULL,
                UNIQUE (data_movimento, tipo_transacao, descricao, pedido_id, direcao, valor),
                FOREIGN KEY (importacao_id) REFERENCES importacoes(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS shopee_saques (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transacao_id INTEGER,
                importacao_id INTEGER,
                data_saque TEXT NOT NULL,
                valor REAL NOT NULL DEFAULT 0,
                saldo_apos_transacao REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'a_conciliar',
                criado_em TEXT NOT NULL,
                UNIQUE (data_saque, valor, saldo_apos_transacao),
                FOREIGN KEY (transacao_id) REFERENCES shopee_transacoes(id) ON DELETE SET NULL,
                FOREIGN KEY (importacao_id) REFERENCES importacoes(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS posicoes_iniciais_caixa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_corte TEXT NOT NULL,
                saldo_banco REAL NOT NULL DEFAULT 0,
                saldo_shopee_disponivel REAL NOT NULL DEFAULT 0,
                saldo_shopee_espera REAL NOT NULL DEFAULT 0,
                observacao TEXT DEFAULT '',
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_shopee_pedidos_status
                ON shopee_pedidos_financeiros(status_financeiro);
            CREATE INDEX IF NOT EXISTS idx_shopee_pedidos_envio
                ON shopee_pedidos_financeiros(data_envio_real);
            CREATE INDEX IF NOT EXISTS idx_shopee_transacoes_pedido
                ON shopee_transacoes(pedido_id);
            CREATE INDEX IF NOT EXISTS idx_shopee_transacoes_data
                ON shopee_transacoes(data_movimento);
            CREATE INDEX IF NOT EXISTS idx_shopee_saques_data
                ON shopee_saques(data_saque);
            CREATE INDEX IF NOT EXISTS idx_posicoes_iniciais_caixa_data
                ON posicoes_iniciais_caixa(data_corte);

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

        _ensure_column(conn, "importacoes", "tipo_relatorio", "TEXT NOT NULL DEFAULT 'performance'")
        _ensure_column(conn, "insumos", "valor_total_estoque", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "insumos", "referencia_uso_custo", "TEXT DEFAULT ''")
        _ensure_column(conn, "shopee_pedidos_financeiros", "numero_rastreio", "TEXT DEFAULT ''")
        _ensure_column(conn, "despesas", "incide_dre", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "despesas", "origem_importacao_id", "INTEGER")
        _ensure_column(conn, "despesas", "origem_referencia", "TEXT DEFAULT ''")
        _ensure_column(conn, "despesas_recorrentes", "incide_dre", "INTEGER NOT NULL DEFAULT 1")

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (chave, valor, atualizado_em)
                VALUES (?, ?, ?)
                """,
                (key, value, now_iso()),
            )
