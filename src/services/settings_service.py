from src.database import fetch_all, fetch_one, get_connection, now_iso


def get_setting_float(key: str, default: float = 0.0) -> float:
    row = fetch_one("SELECT valor FROM settings WHERE chave = ?", (key,))
    if not row:
        return default
    try:
        return float(str(row["valor"]).replace(",", "."))
    except ValueError:
        return default


def get_all_settings() -> dict[str, str]:
    rows = fetch_all("SELECT chave, valor FROM settings ORDER BY chave")
    return {row["chave"]: row["valor"] for row in rows}


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (chave, valor, atualizado_em)
            VALUES (?, ?, ?)
            ON CONFLICT(chave)
            DO UPDATE SET valor = excluded.valor, atualizado_em = excluded.atualizado_em
            """,
            (key, value, now_iso()),
        )
