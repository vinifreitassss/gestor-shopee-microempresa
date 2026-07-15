from datetime import date
from pathlib import Path
import hashlib
import sqlite3

from src.database import fetch_all, get_connection, now_iso
from src.importers.shopee_financial_importer import (
    BalanceTransaction,
    FinancialOrder,
    ShopeeFinancialImporter,
)
from src.services.cancellations_service import apply_manual_cancellations
from src.utils import mes_referencia_from_date, normalize_text


REPORT_TYPE_LABELS = {
    "pedidos_enviados": "Pedidos a enviar / snapshot diário",
    "pagamentos_shopee": "Pagamentos e saques Shopee",
}

SNAPSHOT_SENT_TRACKING = "SAIU_DA_LISTA_A_ENVIAR"


def preview_financial_importation(file_path: str, report_type: str, data_envio_real: date | None = None) -> dict:
    importer = ShopeeFinancialImporter()

    if report_type == "pedidos_enviados":
        orders = importer.preview_orders(file_path, data_envio_real=data_envio_real)
        orders_valid = [order for order in orders if not order.esta_cancelado]
        existing = _existing_order_ids()
        current_ids = {order.pedido_id for order in orders_valid if order.pedido_id}
        currently_open = _current_open_order_ids()
        new_ids = current_ids - existing
        continuing_ids = current_ids & currently_open
        leaving_ids = currently_open - current_ids

        valor_total = sum(order.valor_total for order in orders_valid)
        liquido_aberto = sum(order.valor_liquido_estimado for order in orders_valid)
        novo_aberto = sum(order.valor_liquido_estimado for order in orders_valid if order.pedido_id in new_ids)
        rows = [
            {
                "pedido_id": order.pedido_id,
                "status": order.status_pedido,
                "data": order.data_prevista_envio or order.data_criacao,
                "valor": order.valor_total,
                "liquido": order.valor_liquido_estimado,
                "obs": "novo" if order.pedido_id in new_ids else "continua aberto / não dobra",
            }
            for order in orders[:200]
        ]
        return {
            "report_type": report_type,
            "count": len(orders_valid),
            "valor_total": valor_total,
            "valor_total_aberto": valor_total,
            "valor_total_rastreado": 0,
            "valor_liquido": 0,
            "saldo_possivel_aberto": liquido_aberto,
            "taxas": 0,
            "pedidos_com_rastreio": 0,
            "pedidos_sem_rastreio": len(orders_valid),
            "novos": len(new_ids),
            "continuam": len(continuing_ids),
            "sairam_da_fila": len(leaving_ids),
            "novo_aberto": novo_aberto,
            "rows": rows,
        }

    if report_type == "pagamentos_shopee":
        transactions = importer.preview_transactions(file_path)
        existing_uids = _existing_transaction_uids()
        new_transactions = [t for t in transactions if _transaction_uid(t) not in existing_uids]
        repeated = len(transactions) - len(new_transactions)
        entradas = sum(t.valor for t in new_transactions if normalize_text(t.direcao) == "entrada")
        saques = sum(abs(t.valor) for t in new_transactions if t.is_saque)
        ads = sum(abs(t.valor) for t in new_transactions if t.is_ads and t.valor < 0)
        ajustes_pedido = sum(abs(t.valor) for t in new_transactions if t.is_ajuste_desconto_pedido)
        debitos_sem_saque = sum(abs(t.valor) for t in new_transactions if t.is_saida_sem_saque)
        pedidos = sum(1 for t in new_transactions if t.is_entrada_com_pedido)
        rows = [
            {
                "pedido_id": transaction.pedido_id,
                "status": transaction.tipo_transacao,
                "data": transaction.data_movimento,
                "valor": transaction.valor,
                "liquido": transaction.balanca_apos_transacoes,
                "obs": "nova: " + _transaction_obs(transaction) if _transaction_uid(transaction) not in existing_uids else "repetida / ignorada",
            }
            for transaction in transactions[:200]
        ]
        return {
            "report_type": report_type,
            "count": len(transactions),
            "novas": len(new_transactions),
            "repetidas": repeated,
            "valor_total": entradas,
            "valor_liquido": entradas - saques - debitos_sem_saque,
            "taxas": saques,
            "saques": saques,
            "ads": ads,
            "ajustes_pedido": ajustes_pedido,
            "debitos_sem_saque": debitos_sem_saque,
            "pedidos": pedidos,
            "rows": rows,
        }

    raise ValueError(f"Tipo de relatório financeiro desconhecido: {report_type}")


def save_financial_importation(
    file_path: str,
    report_type: str,
    tipo_periodo: str,
    data_inicio: date,
    data_fim: date,
    mode: str = "perguntar",
) -> int:
    path = Path(file_path)
    mes_ref = mes_referencia_from_date(data_inicio)
    importer = ShopeeFinancialImporter()

    with get_connection() as conn:
        if mode == "substituir" and report_type != "pedidos_enviados":
            _delete_existing_same_period(conn, report_type, tipo_periodo, data_inicio, data_fim)

        importacao_id = _create_importation(conn, path, report_type, tipo_periodo, data_inicio, data_fim, mes_ref)

        if report_type == "pedidos_enviados":
            orders = importer.preview_orders(path, data_envio_real=data_fim)
            _consolidate_orders_snapshot(conn, importacao_id, orders, data_fim)
            _reconcile_all_orders(conn)
            apply_manual_cancellations(conn)
            return importacao_id

        if report_type == "pagamentos_shopee":
            transactions = importer.preview_transactions(path)
            _save_transactions(conn, importacao_id, transactions)
            _reconcile_all_orders(conn)
            apply_manual_cancellations(conn)
            return importacao_id

        raise ValueError(f"Tipo de relatório financeiro desconhecido: {report_type}")


def find_financial_importations_same_period(
    report_type: str,
    tipo_periodo: str,
    data_inicio: date,
    data_fim: date,
) -> list[dict]:
    return fetch_all(
        """
        SELECT * FROM importacoes
        WHERE tipo_relatorio = ?
          AND tipo_periodo = ?
          AND data_inicio = ?
          AND data_fim = ?
          AND status = 'confirmada'
        ORDER BY criado_em DESC
        """,
        (report_type, tipo_periodo, data_inicio.isoformat(), data_fim.isoformat()),
    )


def _existing_order_ids() -> set[str]:
    return {
        row["pedido_id"]
        for row in fetch_all("SELECT pedido_id FROM shopee_pedidos_financeiros")
        if row.get("pedido_id")
    }


def _current_open_order_ids() -> set[str]:
    return {
        row["pedido_id"]
        for row in fetch_all("SELECT pedido_id FROM shopee_pedidos_financeiros WHERE status_financeiro = 'em_aberto'")
        if row.get("pedido_id")
    }


def _existing_transaction_uids() -> set[str]:
    rows = fetch_all(
        """
        SELECT
            COALESCE(
                transaction_uid,
                data_movimento || '|' || tipo_transacao || '|' || COALESCE(descricao, '') || '|' ||
                COALESCE(pedido_id, '') || '|' || COALESCE(direcao, '') || '|' || valor || '|' || balanca_apos_transacoes
            ) AS uid
        FROM shopee_transacoes
        """
    )
    return {row["uid"] for row in rows if row.get("uid")}


def _create_importation(
    conn: sqlite3.Connection,
    path: Path,
    report_type: str,
    tipo_periodo: str,
    data_inicio: date,
    data_fim: date,
    mes_ref: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO importacoes (
            arquivo_nome, caminho_arquivo, tipo_relatorio, tipo_periodo, data_inicio, data_fim,
            mes_referencia, status, criado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmada', ?)
        """,
        (
            path.name,
            str(path),
            report_type,
            tipo_periodo,
            data_inicio.isoformat(),
            data_fim.isoformat(),
            mes_ref,
            now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def _delete_existing_same_period(
    conn: sqlite3.Connection,
    report_type: str,
    tipo_periodo: str,
    data_inicio: date,
    data_fim: date,
) -> None:
    rows = conn.execute(
        """
        SELECT id FROM importacoes
        WHERE tipo_relatorio = ?
          AND tipo_periodo = ?
          AND data_inicio = ?
          AND data_fim = ?
          AND status = 'confirmada'
        """,
        (report_type, tipo_periodo, data_inicio.isoformat(), data_fim.isoformat()),
    ).fetchall()
    for row in rows:
        conn.execute("DELETE FROM despesas WHERE origem_importacao_id = ?", (row["id"],))
        conn.execute("DELETE FROM shopee_saques WHERE importacao_id = ?", (row["id"],))
        conn.execute("DELETE FROM shopee_transacoes WHERE importacao_id = ?", (row["id"],))
        conn.execute("DELETE FROM importacoes WHERE id = ?", (row["id"],))


def _consolidate_orders_snapshot(
    conn: sqlite3.Connection,
    importacao_id: int,
    orders: list[FinancialOrder],
    snapshot_date: date,
) -> None:
    timestamp = now_iso()
    valid_orders = [order for order in orders if not order.esta_cancelado]
    current_ids = {order.pedido_id for order in valid_orders if order.pedido_id}

    for order in valid_orders:
        _upsert_open_order(conn, importacao_id, order, timestamp)

    if not current_ids:
        return

    placeholders = ",".join("?" for _ in current_ids)
    params = [SNAPSHOT_SENT_TRACKING, snapshot_date.isoformat(), timestamp, *current_ids]
    conn.execute(
        f"""
        UPDATE shopee_pedidos_financeiros
        SET status_financeiro = 'em_espera',
            numero_rastreio = CASE
                WHEN numero_rastreio IS NOT NULL AND TRIM(numero_rastreio) <> '' THEN numero_rastreio
                ELSE ?
            END,
            data_envio_real = CASE
                WHEN data_envio_real IS NOT NULL AND TRIM(data_envio_real) <> '' THEN data_envio_real
                ELSE ?
            END,
            atualizado_em = ?
        WHERE status_financeiro = 'em_aberto'
          AND pedido_id NOT IN ({placeholders})
        """,
        params,
    )


def _upsert_open_order(
    conn: sqlite3.Connection,
    importacao_id: int,
    order: FinancialOrder,
    timestamp: str,
) -> None:
    conn.execute(
        """
        INSERT INTO shopee_pedidos_financeiros (
            pedido_id, importacao_id, status_pedido, numero_rastreio, data_criacao, data_pagamento,
            data_prevista_envio, data_envio_real, valor_total, total_global, taxa_transacao,
            comissao_bruta, comissao_liquida, taxa_servico_bruta, taxa_servico_liquida,
            valor_liquido_estimado, status_financeiro, criado_em, atualizado_em
        ) VALUES (?, ?, ?, '', ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, 'em_aberto', ?, ?)
        ON CONFLICT(pedido_id) DO UPDATE SET
            importacao_id = excluded.importacao_id,
            status_pedido = excluded.status_pedido,
            data_criacao = excluded.data_criacao,
            data_pagamento = excluded.data_pagamento,
            data_prevista_envio = excluded.data_prevista_envio,
            valor_total = excluded.valor_total,
            total_global = excluded.total_global,
            taxa_transacao = excluded.taxa_transacao,
            comissao_bruta = excluded.comissao_bruta,
            comissao_liquida = excluded.comissao_liquida,
            taxa_servico_bruta = excluded.taxa_servico_bruta,
            taxa_servico_liquida = excluded.taxa_servico_liquida,
            valor_liquido_estimado = excluded.valor_liquido_estimado,
            status_financeiro = CASE
                WHEN shopee_pedidos_financeiros.status_financeiro IN ('liberado', 'divergente', 'cancelado')
                THEN shopee_pedidos_financeiros.status_financeiro
                ELSE 'em_aberto'
            END,
            numero_rastreio = CASE
                WHEN shopee_pedidos_financeiros.status_financeiro IN ('liberado', 'divergente', 'cancelado')
                THEN shopee_pedidos_financeiros.numero_rastreio
                ELSE ''
            END,
            data_envio_real = CASE
                WHEN shopee_pedidos_financeiros.status_financeiro IN ('liberado', 'divergente', 'cancelado')
                THEN shopee_pedidos_financeiros.data_envio_real
                ELSE ''
            END,
            atualizado_em = excluded.atualizado_em
        """,
        (
            order.pedido_id,
            importacao_id,
            order.status_pedido,
            order.data_criacao,
            order.data_pagamento,
            order.data_prevista_envio,
            order.valor_total,
            order.total_global,
            order.taxa_transacao,
            order.comissao_bruta,
            order.comissao_liquida,
            order.taxa_servico_bruta,
            order.taxa_servico_liquida,
            order.valor_liquido_estimado,
            timestamp,
            timestamp,
        ),
    )

    conn.execute("DELETE FROM shopee_itens_pedido WHERE pedido_id = ?", (order.pedido_id,))
    for item in order.itens:
        conn.execute(
            """
            INSERT INTO shopee_itens_pedido (
                pedido_id, importacao_id, produto_nome, sku, variacao_nome,
                quantidade, subtotal_produto, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.pedido_id,
                importacao_id,
                item.produto_nome,
                item.sku,
                item.variacao_nome,
                item.quantidade,
                item.subtotal_produto,
                timestamp,
            ),
        )


def _transaction_uid(transaction: BalanceTransaction) -> str:
    raw = "|".join(
        [
            str(transaction.data_movimento or ""),
            str(transaction.tipo_transacao or ""),
            str(transaction.descricao or ""),
            str(transaction.pedido_id or ""),
            str(transaction.direcao or ""),
            f"{float(transaction.valor or 0):.2f}",
            f"{float(transaction.balanca_apos_transacoes or 0):.2f}",
            f"{float(transaction.valor_ajustado or 0):.2f}",
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _save_transactions(
    conn: sqlite3.Connection,
    importacao_id: int,
    transactions: list[BalanceTransaction],
) -> None:
    timestamp = now_iso()

    for transaction in transactions:
        uid = _transaction_uid(transaction)
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO shopee_transacoes (
                importacao_id, transaction_uid, data_movimento, tipo_transacao, descricao,
                pedido_id, direcao, valor, status, balanca_apos_transacoes,
                valor_ajustado, status_conciliacao, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendente', ?)
            """,
            (
                importacao_id,
                uid,
                transaction.data_movimento,
                transaction.tipo_transacao,
                transaction.descricao,
                transaction.pedido_id or None,
                transaction.direcao,
                transaction.valor,
                transaction.status,
                transaction.balanca_apos_transacoes,
                transaction.valor_ajustado,
                timestamp,
            ),
        )
        if cursor.rowcount == 0:
            continue

        if transaction.is_saque:
            transaction_id = _find_transaction_id(conn, transaction)
            conn.execute(
                """
                INSERT OR IGNORE INTO shopee_saques (
                    transacao_id, importacao_id, data_saque, valor,
                    saldo_apos_transacao, status, criado_em
                ) VALUES (?, ?, ?, ?, ?, 'a_conciliar', ?)
                """,
                (
                    transaction_id,
                    importacao_id,
                    transaction.data_movimento,
                    abs(transaction.valor),
                    transaction.balanca_apos_transacoes,
                    timestamp,
                ),
            )

        if transaction.is_ads and transaction.valor < 0:
            _save_ads_expense(conn, importacao_id, transaction, timestamp)


def _save_ads_expense(
    conn: sqlite3.Connection,
    importacao_id: int,
    transaction: BalanceTransaction,
    timestamp: str,
) -> None:
    expense_date = str(transaction.data_movimento or "")[:10]
    if not expense_date:
        return
    try:
        mes_ref = mes_referencia_from_date(date.fromisoformat(expense_date))
    except ValueError:
        return

    reference = f"shopee_ads:{_transaction_uid(transaction)}"
    exists = conn.execute(
        "SELECT id FROM despesas WHERE origem_referencia = ? LIMIT 1",
        (reference,),
    ).fetchone()
    if exists:
        return

    conn.execute(
        """
        INSERT INTO despesas (
            data, mes_referencia, categoria, descricao, valor,
            incide_dre, origem_importacao_id, origem_referencia, criado_em
        ) VALUES (?, ?, 'Shopee Ads', ?, ?, 1, ?, ?, ?)
        """,
        (
            expense_date,
            mes_ref,
            transaction.descricao or "Recarga por compra de ADS",
            abs(transaction.valor),
            importacao_id,
            reference,
            timestamp,
        ),
    )


def _find_transaction_id(conn: sqlite3.Connection, transaction: BalanceTransaction) -> int | None:
    uid = _transaction_uid(transaction)
    row = conn.execute(
        """
        SELECT id FROM shopee_transacoes
        WHERE transaction_uid = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (uid,),
    ).fetchone()
    if row:
        return int(row["id"])

    row = conn.execute(
        """
        SELECT id FROM shopee_transacoes
        WHERE data_movimento = ?
          AND tipo_transacao = ?
          AND descricao = ?
          AND COALESCE(pedido_id, '') = COALESCE(?, '')
          AND direcao = ?
          AND valor = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            transaction.data_movimento,
            transaction.tipo_transacao,
            transaction.descricao,
            transaction.pedido_id or None,
            transaction.direcao,
            transaction.valor,
        ),
    ).fetchone()
    return int(row["id"]) if row else None


def _reconcile_all_orders(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()

    conn.execute(
        """
        UPDATE shopee_pedidos_financeiros
        SET valor_pago_real = 0,
            data_liberacao_shopee = NULL,
            diferenca = 0,
            status_financeiro = CASE
                WHEN LOWER(status_pedido) LIKE '%cancel%' THEN 'cancelado'
                WHEN status_financeiro = 'em_espera' THEN 'em_espera'
                ELSE 'em_aberto'
            END,
            atualizado_em = ?
        WHERE status_financeiro NOT IN ('em_aberto', 'em_espera', 'cancelado')
        """,
        (timestamp,),
    )

    payments = conn.execute(
        """
        SELECT
            pedido_id,
            SUM(valor) AS valor_pago,
            MIN(data_movimento) AS primeira_liberacao
        FROM shopee_transacoes
        WHERE pedido_id IS NOT NULL
          AND TRIM(pedido_id) <> ''
          AND LOWER(tipo_transacao) NOT LIKE '%saque%'
        GROUP BY pedido_id
        """
    ).fetchall()

    for payment in payments:
        order = conn.execute(
            """
            SELECT pedido_id, valor_liquido_estimado, status_financeiro
            FROM shopee_pedidos_financeiros
            WHERE pedido_id = ?
            """,
            (payment["pedido_id"],),
        ).fetchone()
        if not order:
            continue
        if order["status_financeiro"] == "cancelado":
            continue

        valor_pago = float(payment["valor_pago"] or 0)
        estimado = float(order["valor_liquido_estimado"] or 0)
        diferenca = round(valor_pago - estimado, 2)
        status = "liberado" if abs(diferenca) <= 0.05 else "divergente"

        conn.execute(
            """
            UPDATE shopee_pedidos_financeiros
            SET valor_pago_real = ?,
                data_liberacao_shopee = ?,
                diferenca = ?,
                status_financeiro = ?,
                atualizado_em = ?
            WHERE pedido_id = ?
            """,
            (
                valor_pago,
                payment["primeira_liberacao"],
                diferenca,
                status,
                timestamp,
                payment["pedido_id"],
            ),
        )

    conn.execute(
        """
        UPDATE shopee_transacoes
        SET status_conciliacao = CASE
            WHEN LOWER(tipo_transacao) LIKE '%saque%' THEN 'saque'
            WHEN LOWER(tipo_transacao || ' ' || descricao) LIKE '%ads%' THEN 'shopee_ads'
            WHEN pedido_id IS NOT NULL AND TRIM(pedido_id) <> ''
                 AND LOWER(direcao) <> 'entrada' THEN 'ajuste_pedido'
            WHEN pedido_id IS NULL OR TRIM(pedido_id) = '' THEN 'sem_pedido'
            WHEN EXISTS (
                SELECT 1 FROM shopee_pedidos_financeiros p
                WHERE p.pedido_id = shopee_transacoes.pedido_id
            ) THEN 'conciliado'
            ELSE 'sem_pedido'
        END
        """
    )


def _transaction_obs(transaction: BalanceTransaction) -> str:
    if transaction.is_saque:
        return "saque para banco"
    if transaction.is_ads:
        return "Shopee Ads / despesa DRE"
    if transaction.is_ajuste_desconto_pedido:
        return "desconto/ajuste do pedido"
    return transaction.direcao
