from copy import copy
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.drawing.image import Image as ExcelImage

from app.db.models import Invoice


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "assets" / "invoice_template.xlsx"
DETAIL_START_ROW = 13
DETAIL_MAX_LINES = 30


def _copy_row_style(sheet, source_row: int, target_row: int) -> None:
    sheet.row_dimensions[target_row].height = sheet.row_dimensions[source_row].height
    for column in range(1, 8):
        source = sheet.cell(source_row, column)
        target = sheet.cell(target_row, column)
        if source.has_style:
            target._style = copy(source._style)
        if source.number_format:
            target.number_format = source.number_format
        if source.alignment:
            target.alignment = copy(source.alignment)


def _prepare_detail_area(sheet) -> tuple[int, int]:
    """Extend the reference template's 26 detail rows to the agreed 30 rows."""
    # The original bank block starts inside the rows being converted into the
    # additional four detail lines, so release the merge before touching cells.
    for merged in list(sheet.merged_cells.ranges):
        if str(merged) == "A41:G43":
            sheet.unmerge_cells(str(merged))

    # The supplied template contains example waybills (including "duty" rows)
    # in its detail table. Preserve the table formatting, but always remove every
    # example value/formula before inserting the selected invoice lines.
    for row in range(DETAIL_START_ROW, DETAIL_START_ROW + DETAIL_MAX_LINES):
        for column in range(1, 8):
            sheet.cell(row, column).value = None

    for row in range(39, 43):
        _copy_row_style(sheet, 38, row)

    total_row = 43
    for column in range(1, 8):
        source = sheet.cell(39, column)
        target = sheet.cell(total_row, column)
        if source.has_style:
            target._style = copy(source._style)
        if source.alignment:
            target.alignment = copy(source.alignment)
        if source.number_format:
            target.number_format = source.number_format

    # The source template merges A41:G43 for bank information. Recreate it below
    # the extended detail table without modifying the stored template itself.
    for row in range(41, 48):
        for column in range(1, 8):
            sheet.cell(row, column).value = None
    sheet.merge_cells("A45:G47")
    return total_row, 45


def _bank_text(snapshot: dict) -> str:
    return "\n".join(
        [
            f"Beneficiary Name: {snapshot['beneficiaryName']}",
            f"Bank Account :{snapshot['bankAccount']}",
            f"Bank name and code: {snapshot['bankNameAndCode']}",
            f"Branch code: {snapshot['branchCode']}",
            f"Swift/BIC:{snapshot['swiftBic']}",
            f"Bank Address: {snapshot['bankAddress']}",
        ]
    )


def build_invoice_workbook(invoice: Invoice) -> bytes:
    workbook = load_workbook(TEMPLATE_PATH)
    sheet = workbook.active
    total_row, bank_row = _prepare_detail_area(sheet)
    payer = invoice.payer_snapshot
    issuer = invoice.issuer_snapshot

    sheet["F2"] = invoice.invoice_number
    sheet["G2"] = invoice.issued_date.strftime("%Y.%m.%d")
    sheet["A7"] = f"{payer['companyName']}\n{payer['addressInfo']}"
    sheet["F7"] = f"{issuer['issuerCompanyName']}\n{issuer['issuerAddressInfo']}"
    sheet["A9"] = (
        f"賬單金額€ {invoice.total_amount:,.2f}  EUR"
        f"(到期日 {invoice.due_date.year}年{invoice.due_date.month}月{invoice.due_date.day}日)"
    )

    for index, line in enumerate(invoice.lines, start=DETAIL_START_ROW):
        sheet.cell(index, 1).value = line.waybill_number
        sheet.cell(index, 3).value = line.quantity
        sheet.cell(index, 4).value = float(line.unit_rate)
        sheet.cell(index, 7).value = float(line.amount)
        sheet.cell(index, 4).number_format = "0.00"
        sheet.cell(index, 7).number_format = "#,##0.00"

    sheet.cell(total_row, 6).value = "應付金額"
    sheet.cell(total_row, 7).value = float(invoice.total_amount)
    sheet.cell(total_row, 7).number_format = "#,##0.00"
    sheet.cell(bank_row, 1).value = _bank_text(issuer)

    if invoice.stamp_storage_path and invoice.stamp_position:
        stamp_path = Path(invoice.stamp_storage_path)
        if stamp_path.is_file():
            image = ExcelImage(stamp_path)
            image.width = int(invoice.stamp_position.get("width", 86))
            image.height = int(invoice.stamp_position.get("height", 86))
            sheet.add_image(image, invoice.stamp_position.get("anchor", "E20"))

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
