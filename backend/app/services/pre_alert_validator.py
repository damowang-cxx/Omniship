import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Iterable


RECIPIENT_NAME_COLUMN_INDEX = 12  # L
ADDRESS_COLUMN_INDEX = 13  # M
VALUE_EUR_COLUMN_INDEX = 23  # W
MAX_RECIPIENT_ADDRESS_VALUE_EUR = Decimal("150")


class PreAlertValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PreAlertRow:
    row_number: int
    recipient_name: str
    address: str
    value_eur_raw: object


def validate_pre_alert_excel(
    *,
    filename: str,
    content: bytes,
) -> None:
    rows = list(_read_rows(filename=filename, content=content))
    validation_errors = _find_recipient_address_value_errors(rows)
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
    try:
        sheet = workbook.active
        return [
            _build_row(row_number, row)
            for row_number, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True),
                start=2,
            )
        ]
    finally:
        workbook.close()


def _read_xls_rows(content: bytes) -> list[PreAlertRow]:
    import xlrd

    workbook = xlrd.open_workbook(file_contents=content)
    sheet = workbook.sheet_by_index(0)
    return [
        _build_row(row_index + 1, sheet.row_values(row_index))
        for row_index in range(1, sheet.nrows)
    ]


def _build_row(row_number: int, row: tuple | list) -> PreAlertRow:
    return PreAlertRow(
        row_number=row_number,
        recipient_name=_cell_text(_cell(row, RECIPIENT_NAME_COLUMN_INDEX)),
        address=_cell_text(_cell(row, ADDRESS_COLUMN_INDEX)),
        value_eur_raw=_cell(row, VALUE_EUR_COLUMN_INDEX),
    )


def _cell(row: tuple | list, one_based_index: int):
    index = one_based_index - 1
    return row[index] if len(row) > index else None


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _find_recipient_address_value_errors(rows: list[PreAlertRow]) -> list[str]:
    grouped: dict[tuple[str, str], list[tuple[PreAlertRow, Decimal]]] = defaultdict(list)
    errors = []

    for row in rows:
        raw_amount = _cell_text(row.value_eur_raw)
        if not row.recipient_name and not row.address and not raw_amount:
            continue

        amount = _parse_decimal(row.value_eur_raw)
        if amount is None:
            if raw_amount:
                errors.append(f"L/M/W row {row.row_number} amount is not a valid number")
            continue

        if not row.recipient_name or not row.address:
            errors.append(
                f"L/M/W row {row.row_number} recipient name and address are required when amount is present"
            )
            continue

        grouped[(_normalize_group_key(row.recipient_name), _normalize_group_key(row.address))].append(
            (row, amount)
        )

    for group_rows in grouped.values():
        total = sum((amount for _, amount in group_rows), Decimal("0"))
        if total > MAX_RECIPIENT_ADDRESS_VALUE_EUR:
            first_row = group_rows[0][0]
            row_numbers = ", ".join(str(row.row_number) for row, _ in group_rows[:8])
            errors.append(
                "同一收件人/地址的 W 列申报金额超过 150 EUR: "
                f"rows {row_numbers}, recipient {first_row.recipient_name}, "
                f"address {first_row.address}, total {_format_decimal(total)} EUR"
            )

    return errors[:10]


def _parse_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None

    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"(?i)\beur\b|€", "", text).strip()
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


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
