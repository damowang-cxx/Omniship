import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Iterable


GOODS_DESCRIPTION_COLUMN_INDEX = 19  # S
RECIPIENT_NAME_COLUMN_INDEX = 10  # J
ADDRESS_COLUMN_INDEX = 12  # L
VALUE_EUR_COLUMN_INDEX = 21  # U
MAX_RECIPIENT_ADDRESS_VALUE_EUR = Decimal("150")

BANNED_GOODS_DESCRIPTION_TERMS = [
    "Building block",
    "material package",
    "Alloy wheel",
    "Controller",
    "Navigator",
    "TENT",
    "STOOL",
    "Hip reverse mould",
    "Drill Bit",
    "Ceramic record",
    "Decorative buckle",
    "Vacuum cleaner",
    "Face cleaner machine",
    "LAMP",
    "SANDBAG",
    "TAILPLANE",
    "Tennis ball machine",
    "Car diagnostic tool",
    "CANOPY",
    "GENERATOR",
    "BILLBOARD",
    "HOME MASSAGER",
    "MASSAGE INSTRUMENT",
    "Massage",
    "Leg Massage",
    "Exhaust pipe",
    "Nail Polisher",
    "DRAWING BOARD",
    "BICYCLE WHEELS",
    "mannequin",
    "Suitcase",
    "monitor",
    "Self-adhesive label",
    "Drive wheel",
    "Welding machine",
]


class PreAlertValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PreAlertRow:
    row_number: int
    recipient_name: str
    address: str
    goods_description: str
    value_eur_raw: object


def validate_pre_alert_excel(
    *,
    filename: str,
    content: bytes,
) -> None:
    rows = list(_read_rows(filename=filename, content=content))
    validation_errors = [
        *_find_banned_goods_descriptions(rows),
        *_find_recipient_address_value_errors(rows),
    ]
    if validation_errors:
        raise PreAlertValidationError(
            "Pre Alert validation failed: " + "; ".join(validation_errors[:20])
        )


def _read_rows(*, filename: str, content: bytes) -> Iterable[PreAlertRow]:
    extension = Path(filename).suffix.lower()
    try:
        if extension == ".xlsx":
            return _read_xlsx_rows(content)
        if extension == ".xls":
            return _read_xls_rows(content)
    except Exception as exc:
        raise PreAlertValidationError(
            "Upload Pre Alert File could not be read as an Excel workbook"
        ) from exc

    raise PreAlertValidationError("Upload Pre Alert File must be an Excel workbook")


def _read_xlsx_rows(content: bytes) -> list[PreAlertRow]:
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
    sheet = workbook.active
    rows = []
    for row_number, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True),
        start=2,
    ):
        rows.append(_build_row(row_number, row))
    workbook.close()
    return rows


def _read_xls_rows(content: bytes) -> list[PreAlertRow]:
    import xlrd

    workbook = xlrd.open_workbook(file_contents=content)
    sheet = workbook.sheet_by_index(0)
    rows = []
    for row_index in range(1, sheet.nrows):
        rows.append(_build_row(row_index + 1, sheet.row_values(row_index)))
    return rows


def _build_row(row_number: int, row: tuple | list) -> PreAlertRow:
    return PreAlertRow(
        row_number=row_number,
        recipient_name=_cell_text(_cell(row, RECIPIENT_NAME_COLUMN_INDEX)),
        address=_cell_text(_cell(row, ADDRESS_COLUMN_INDEX)),
        goods_description=_cell_text(_cell(row, GOODS_DESCRIPTION_COLUMN_INDEX)),
        value_eur_raw=_cell(row, VALUE_EUR_COLUMN_INDEX),
    )


def _cell(row: tuple | list, one_based_index: int):
    index = one_based_index - 1
    return row[index] if len(row) > index else None


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _find_banned_goods_descriptions(rows: list[PreAlertRow]) -> list[str]:
    errors = []
    for row in rows:
        if not row.goods_description:
            continue
        matched_terms = [
            term
            for term in _unique_banned_terms()
            if _contains_term(row.goods_description, term)
        ]
        if matched_terms:
            errors.append(
                f"S列 GoodsDescription row {row.row_number} contains prohibited term(s): "
                + ", ".join(matched_terms[:5])
            )
    return errors[:10]


def _find_recipient_address_value_errors(rows: list[PreAlertRow]) -> list[str]:
    grouped: dict[tuple[str, str], list[tuple[PreAlertRow, Decimal]]] = defaultdict(list)
    errors = []

    for row in rows:
        amount = _parse_decimal(row.value_eur_raw)
        if amount is None:
            if _cell_text(row.value_eur_raw):
                errors.append(f"U列 value row {row.row_number} is not a valid number")
            continue

        recipient_key = _normalize_group_key(row.recipient_name)
        address_key = _normalize_group_key(row.address)
        if recipient_key or address_key:
            grouped[(recipient_key, address_key)].append((row, amount))

    for group_rows in grouped.values():
        total = sum((amount for _, amount in group_rows), Decimal("0"))
        if total > MAX_RECIPIENT_ADDRESS_VALUE_EUR:
            first_row = group_rows[0][0]
            row_numbers = ", ".join(str(row.row_number) for row, _ in group_rows[:8])
            errors.append(
                "同一收件人/地址的 U列申报金额超过 150 EUR: "
                f"rows {row_numbers}, recipient {first_row.recipient_name or '-'}, "
                f"address {first_row.address or '-'}, total {total.normalize()} EUR"
            )

    return errors[:10]


def _parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None

    text = str(value).strip()
    if not text:
        return None
    text = text.replace("€", "").replace("EUR", "").replace("eur", "").strip()
    text = text.replace(" ", "")
    if "," in text and "." not in text and text.count(",") == 1:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _normalize_group_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _contains_term(text: str, term: str) -> bool:
    normalized_text = re.sub(r"\s+", " ", text.strip().lower())
    normalized_term = re.sub(r"\s+", " ", term.strip().lower())
    pattern = r"(?<![a-z0-9])" + re.escape(normalized_term).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def _unique_banned_terms() -> list[str]:
    seen = set()
    unique_terms = []
    for term in BANNED_GOODS_DESCRIPTION_TERMS:
        key = term.strip().lower()
        if key not in seen:
            seen.add(key)
            unique_terms.append(term)
    return unique_terms
