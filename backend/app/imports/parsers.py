import csv
import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.imports.columns import recognized_header_count


class ImportFileError(ValueError):
    pass


@dataclass
class ParsedFile:
    file_format: str
    worksheet_names: list[str]
    selected_worksheet: str | None
    headers: list[str]
    rows: list[tuple[int, dict[str, Any], list[dict[str, str]]]]


def _safe_cell(value: Any, maximum: int) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    if len(text) > maximum:
        raise ImportFileError("A cell exceeds the configured length limit")
    return text or None


def detect_format(filename: str, content_type: str | None, sample: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".docx"}:
        raise ImportFileError("Unsupported import format; use CSV, XLSX, or DOCX")
    if not sample:
        raise ImportFileError("The uploaded file is empty")
    if suffix == ".xlsx":
        if not sample.startswith(b"PK\x03\x04"):
            raise ImportFileError("File content does not match the XLSX extension")
        if content_type and content_type not in {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"}:
            raise ImportFileError("File content type does not match the XLSX extension")
        return "xlsx"
    if suffix == ".docx":
        if not sample.startswith(b"PK\x03\x04"):
            raise ImportFileError("File content does not match the DOCX extension")
        if content_type and content_type not in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/octet-stream",
        }:
            raise ImportFileError("File content type does not match the DOCX extension")
        return "docx"
    if sample.startswith((b"PK\x03\x04", b"MZ", b"%PDF", b"\x89PNG", b"GIF8")) or b"\x00" in sample:
        raise ImportFileError("File content does not match the CSV extension")
    if content_type and content_type not in {"text/csv", "text/plain", "application/csv", "application/vnd.ms-excel", "application/octet-stream"}:
        raise ImportFileError("File content type does not match the CSV extension")
    return "csv"


def _header_row_index(records: list[list[Any]]) -> int | None:
    candidates = [
        (index, row)
        for index, row in enumerate(records[:20])
        if any(value is not None and str(value).strip() for value in row)
    ]
    if not candidates:
        return None
    recognized = [(index, recognized_header_count([str(value or "").strip() for value in row])) for index, row in candidates]
    best_index, best_count = max(recognized, key=lambda item: item[1])
    return best_index if best_count >= 2 else candidates[0][0]


def _header_layout(values: list[Any], maximum_columns: int, file_label: str) -> tuple[list[str], list[int]]:
    headers = [str(value).strip() if value is not None else "" for value in values]
    while headers and not headers[-1]:
        headers.pop()
    if not headers or len(headers) > maximum_columns or not any(headers):
        raise ImportFileError(f"{file_label} header is empty or invalid")
    indices = [index for index, header in enumerate(headers) if header]
    if not indices:
        raise ImportFileError(f"{file_label} header is empty or invalid")
    return [headers[index] for index in indices], indices


def _csv_file(path: Path, limits: dict) -> ParsedFile:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFileError("CSV must use UTF-8 encoding") from exc
    if not text.strip():
        raise ImportFileError("The uploaded file is empty")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    csv.field_size_limit(limits["maximum_cell_length"])
    try:
        records = list(csv.reader(io.StringIO(text, newline=""), dialect=dialect, strict=True))
    except (csv.Error, OverflowError) as exc:
        raise ImportFileError("CSV structure is malformed") from exc
    header_index = _header_row_index(records)
    if header_index is None:
        raise ImportFileError("A meaningful header row was not found")
    headers, header_indices = _header_layout(records[header_index], limits["maximum_columns"], "CSV")
    rows = []
    for source_row, values in enumerate(records[header_index + 1:], start=header_index + 2):
        if not any(str(value).strip() for value in values):
            continue
        warnings = []
        if any(index < len(values) and str(values[index]).strip() for index in range(max(header_indices) + 1) if index not in header_indices):
            warnings.append({"field": "row", "code": "unheaded_column", "message": "Values in columns without headers were ignored"})
        if any(index >= len(values) for index in header_indices):
            warnings.append({"field": "row", "code": "column_count", "message": "Row column count differs from the header"})
        if any(str(value).strip() for value in values[max(header_indices) + 1:]):
            warnings.append({"field": "row", "code": "column_count", "message": "Row column count differs from the header"})
        row = {
            header: _safe_cell(values[index] if index < len(values) else "", limits["maximum_cell_length"])
            for header, index in zip(headers, header_indices)
        }
        rows.append((source_row, row, warnings))
        if len(rows) > limits["maximum_rows"]:
            raise ImportFileError("File exceeds the configured row limit")
    if not rows:
        raise ImportFileError("The file contains no data rows")
    return ParsedFile("csv", [], None, headers, rows)


def _xlsx_file(path: Path, limits: dict, worksheet: str | None) -> ParsedFile:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ImportFileError("File content is not a valid XLSX workbook")
            if any(name.lower().endswith("vbaproject.bin") for name in names):
                raise ImportFileError("Macro-enabled workbooks are not supported")
            if len(names) > 5000 or sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ImportFileError("Workbook expanded content exceeds the safety limit")
        workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    except ImportFileError:
        raise
    except Exception as exc:
        raise ImportFileError("Workbook is corrupt, unreadable, or password protected") from exc
    try:
        names = workbook.sheetnames
        if not names or len(names) > limits["maximum_worksheets"]:
            raise ImportFileError("Workbook has no usable worksheet or exceeds the worksheet limit")
        selected = worksheet
        if selected is None:
            for candidate in names:
                candidate_rows = workbook[candidate].iter_rows()
                if any(any(cell.value is not None and str(cell.value).strip() for cell in row) for _, row in zip(range(20), candidate_rows)):
                    selected = candidate
                    break
        if selected is None:
            raise ImportFileError("Workbook has no suitable worksheet")
        if selected not in names:
            raise ImportFileError("Selected worksheet does not exist")
        sheet = workbook[selected]
        first_rows = list(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 20)))
        header_index = _header_row_index([[cell.value for cell in row] for row in first_rows])
        if header_index is None:
            raise ImportFileError("A meaningful header row was not found")
        header_row = header_index + 1
        headers, header_indices = _header_layout(
            [cell.value for cell in first_rows[header_index]], limits["maximum_columns"], "Workbook"
        )
        rows = []
        for source_row, cells in enumerate(sheet.iter_rows(min_row=header_row + 1), start=header_row + 1):
            if not any(cell.value is not None and str(cell.value).strip() for cell in cells):
                continue
            warnings = []
            values = {}
            for header, index in zip(headers, header_indices):
                cell = cells[index] if index < len(cells) else None
                if cell is None:
                    values[header] = None
                    continue
                if cell.data_type == "f":
                    warnings.append({"field": header, "code": "formula_ignored", "message": "Formula was not evaluated"})
                    values[header] = None
                else:
                    values[header] = _safe_cell(cell.value, limits["maximum_cell_length"])
            if any(
                cell.value is not None and str(cell.value).strip()
                for index, cell in enumerate(cells[: max(header_indices) + 1])
                if index not in header_indices
            ):
                warnings.append({"field": "row", "code": "unheaded_column", "message": "Values in columns without headers were ignored"})
            rows.append((source_row, values, warnings))
            if len(rows) > limits["maximum_rows"]:
                raise ImportFileError("Workbook exceeds the configured row limit")
        if not rows:
            raise ImportFileError("The worksheet contains no data rows")
        return ParsedFile("xlsx", names, selected, headers, rows)
    finally:
        workbook.close()


def parse_file(path: Path, file_format: str, limits: dict, worksheet: str | None = None) -> ParsedFile:
    if file_format == "csv":
        return _csv_file(path, limits)
    if file_format == "xlsx":
        return _xlsx_file(path, limits, worksheet)
    if file_format == "docx":
        return _docx_file(path, limits)
    raise ImportFileError("Unsupported import format")


def _docx_file(path: Path, limits: dict) -> ParsedFile:
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ImportFileError("File content is not a valid DOCX document")
            if len(names) > 5000 or sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ImportFileError("Document expanded content exceeds the safety limit")
            document = ET.fromstring(archive.read("word/document.xml"))
    except ImportFileError:
        raise
    except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError, RuntimeError) as exc:
        raise ImportFileError("Word document is corrupt, unreadable, or password protected") from exc

    for table in document.findall(".//w:tbl", namespace):
        records = []
        for row in table.findall("./w:tr", namespace):
            cells = []
            for cell in row.findall("./w:tc", namespace):
                text = " ".join(value.strip() for value in cell.itertext() if value.strip())
                cells.append(text)
            if any(value.strip() for value in cells):
                records.append(cells)
        headers = [value.strip() for value in records[0]] if records else []
        if not headers:
            continue
        if len(headers) > limits["maximum_columns"] or any(not value for value in headers):
            raise ImportFileError("Word table header is empty or invalid")
        rows = []
        for source_row, values in enumerate(records[1:], start=2):
            warnings = []
            if len(values) != len(headers):
                warnings.append({"field": "row", "code": "column_count", "message": "Row column count differs from the header"})
            padded = (values + [""] * len(headers))[:len(headers)]
            row = {header: _safe_cell(value, limits["maximum_cell_length"]) for header, value in zip(headers, padded)}
            if not any(row.values()):
                continue
            rows.append((source_row, row, warnings))
            if len(rows) > limits["maximum_rows"]:
                raise ImportFileError("Word table exceeds the configured row limit")
        if rows:
            return ParsedFile("docx", [], None, headers, rows)
    raise ImportFileError("Word document must contain a table with column headings and inventory rows")
