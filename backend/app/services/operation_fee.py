"""Fixed declaration handling fee, independent of supplier validation/billing rules."""
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from struct import unpack_from

from app.schemas.supplier import SupplierVersionConfig

OPERATION_FEE_TYPE = "declaration_operation_fee"
CUSTOMS_FEE_TYPE = "customs_tax"
OPERATION_UNIT_RATE = Decimal("2.00")
LHR_WEIGHT_FEE_TYPE = "lhr_weight_handling"
LHR_CLEARANCE_FEE_TYPE = "lhr_clearance"
LHR_WEIGHT_RATE_GBP = Decimal("0.50")
LHR_CLEARANCE_RATE_EUR = Decimal("45.00")


def fee_name(fee_type: str | None) -> str:
    return {
        OPERATION_FEE_TYPE: "申报行操作费",
        LHR_WEIGHT_FEE_TYPE: "LHR 重量操作费",
        LHR_CLEARANCE_FEE_TYPE: "LHR 清关费",
    }.get(fee_type, "Customs tax")


def count_operation_rows(*, filename: str, content: bytes, config: SupplierVersionConfig) -> int:
    """Count nonblank physical rows after row 1 in the configured worksheet.

    Do not use data_start_row, row keys, validation results or deduplication.
    XLSX formulas count even without cached results.
    """
    def nonblank(values) -> bool:
        return any(value is not None and (not isinstance(value, str) or value.strip()) for value in values)

    try:
        extension = Path(filename).suffix.lower()
        if extension == ".xlsx":
            from openpyxl import load_workbook
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
            try:
                sheet = workbook[config.workbook.sheet_name] if config.workbook.sheet_mode == "named" else workbook.active
                return sum(nonblank(row) for row in sheet.iter_rows(min_row=2, values_only=True))
            finally:
                workbook.close()
        if extension == ".xls":
            import xlrd
            workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
            try:
                sheet = workbook.sheet_by_name(config.workbook.sheet_name) if config.workbook.sheet_mode == "named" else workbook.sheet_by_index(0)
                rows = {index for index in range(1, sheet.nrows) if nonblank(sheet.row_values(index))}
                # xlrd exposes formula RESULTS, so ="" would look like an empty
                # cell. Inspect FORMULA records in the selected BIFF sheet too.
                # xlrd is pinned; positions are absolute offsets in workbook.mem.
                sheet_index = workbook.sheet_names().index(sheet.name)
                data = workbook.mem
                position = workbook._sh_abs_posn[sheet_index]
                while data is not None and position + 4 <= len(data):
                    opcode, size = unpack_from("<HH", data, position)
                    position += 4
                    if opcode == 0x000A:  # worksheet EOF
                        break
                    if opcode in (0x0006, 0x0206, 0x0406) and size >= 2:
                        row_index = unpack_from("<H", data, position)[0]
                        if row_index >= 1:
                            rows.add(row_index)
                    position += size
                return len(rows)
            finally:
                workbook.release_resources()
        raise ValueError("Pre Alert File must be an XLS or XLSX workbook")
    except Exception as exc:
        raise ValueError(f"Cannot calculate declaration operation fee: {exc}") from exc
