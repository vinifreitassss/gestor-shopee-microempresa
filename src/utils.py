import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text)
    return text


def money_to_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "--"}:
        return 0.0
    text = text.replace("R$", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    try:
        return float(Decimal(text))
    except (InvalidOperation, ValueError):
        return 0.0


def int_to_safe(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text or text in {"-", "--"}:
        return 0
    text = re.sub(r"[^0-9\-]", "", text)
    try:
        return int(text)
    except ValueError:
        return 0


def mes_referencia_from_date(dt: date | datetime | str) -> str:
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt).date()
    if isinstance(dt, datetime):
        dt = dt.date()
    return f"{dt.year:04d}-{dt.month:02d}"


def brl(value: float | int | None) -> str:
    number = float(value or 0)
    formatted = f"{number:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def percent(value: float | int | None) -> str:
    return f"{float(value or 0):.2f}%".replace(".", ",")
