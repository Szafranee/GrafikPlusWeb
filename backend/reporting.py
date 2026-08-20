import json
import logging
import os
import posixpath
import re
import tempfile
import threading
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lxml import etree


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTANCE_DIR = PROJECT_ROOT / "instance"
SETTINGS_PATH = INSTANCE_DIR / "report_settings.json"
MANAGED_TEMPLATE_PATH = INSTANCE_DIR / "report_template.xlsx"
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "report_template.xlsx"

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NSMAP = {"m": MAIN_NS, "r": OFFICE_REL_NS}
WORKBOOK_PATH = "xl/workbook.xml"

CELL_RE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*)$")
COLUMN_RE = re.compile(r"^[A-Z]{1,3}$")
POLISH_MONTHS = (
    "STYCZEŃ",
    "LUTY",
    "MARZEC",
    "KWIECIEŃ",
    "MAJ",
    "CZERWIEC",
    "LIPIEC",
    "SIERPIEŃ",
    "WRZESIEŃ",
    "PAŹDZIERNIK",
    "LISTOPAD",
    "GRUDZIEŃ",
)


class ReportConfigurationError(ValueError):
    pass


class ReportGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReportSettings:
    worksheet: str = "Raport"
    start_row: int = 7
    end_row: int = 500
    date_column: str = "E"
    program_title_column: str = "F"
    description_column: str = "G"
    activity_column: str = "H"
    hours_column: str = "J"
    full_name_cell: str = "F3"
    month_cell: str = "H2"
    year_cell: str = "H3"
    activity_value: str = "MONTAŻ"

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "ReportSettings":
        allowed = {item.name for item in fields(cls)}
        normalized = {key: value for key, value in values.items() if key in allowed}
        for key in (
            "date_column",
            "program_title_column",
            "description_column",
            "activity_column",
            "hours_column",
            "full_name_cell",
            "month_cell",
            "year_cell",
        ):
            if key in normalized and isinstance(normalized[key], str):
                normalized[key] = normalized[key].strip().upper()
        if "worksheet" in normalized and isinstance(normalized["worksheet"], str):
            normalized["worksheet"] = normalized["worksheet"].strip()
        if "activity_value" in normalized and isinstance(normalized["activity_value"], str):
            normalized["activity_value"] = normalized["activity_value"].strip()
        try:
            normalized["start_row"] = int(normalized.get("start_row", cls.start_row))
            normalized["end_row"] = int(normalized.get("end_row", cls.end_row))
            settings = cls(**normalized)
        except (TypeError, ValueError) as exc:
            raise ReportConfigurationError("Invalid report settings.") from exc
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.worksheet:
            raise ReportConfigurationError("Worksheet name cannot be empty.")
        if self.start_row < 1 or self.end_row < self.start_row:
            raise ReportConfigurationError("The report row range is invalid.")
        if self.end_row - self.start_row > 10_000:
            raise ReportConfigurationError("The report row range is too large.")

        columns = (
            self.date_column,
            self.program_title_column,
            self.description_column,
            self.activity_column,
            self.hours_column,
        )
        if any(not COLUMN_RE.fullmatch(column) for column in columns):
            raise ReportConfigurationError("Data columns must use Excel column letters.")
        if len(set(columns)) != len(columns):
            raise ReportConfigurationError("Each report field must use a different column.")

        cells = (self.full_name_cell, self.month_cell, self.year_cell)
        if any(not CELL_RE.fullmatch(cell) for cell in cells):
            raise ReportConfigurationError("Metadata positions must be valid Excel cells.")
        if not self.activity_value:
            raise ReportConfigurationError("Activity cannot be empty.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReportIdentity:
    full_name: str
    month: str
    year: int
    filename: str


class ReportSettingsStore:
    _lock = threading.RLock()

    def __init__(self, settings_path: Path = SETTINGS_PATH):
        self.settings_path = settings_path

    def load(self) -> ReportSettings:
        with self._lock:
            if not self.settings_path.exists():
                return ReportSettings()
            try:
                values = json.loads(self.settings_path.read_text(encoding="utf-8"))
                return ReportSettings.from_dict(values)
            except (OSError, json.JSONDecodeError, ReportConfigurationError) as exc:
                logging.error("Failed to load report settings: %s", exc)
                raise ReportConfigurationError("Stored report settings are invalid.") from exc

    def save(self, values: dict[str, Any]) -> ReportSettings:
        settings = ReportSettings.from_dict(values)
        template_path = get_report_template_path(required=False)
        if template_path:
            validate_template_file(template_path, settings.worksheet)

        with self._lock:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.settings_path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(settings.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, self.settings_path)
        return settings


def template_export_enabled() -> bool:
    value = os.environ.get("USE_TEMPLATE_EXPORT", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def get_report_template_path(required: bool = True) -> Path | None:
    candidates = [MANAGED_TEMPLATE_PATH]
    configured_path = os.environ.get("REPORT_TEMPLATE_PATH", "").strip()
    if configured_path:
        path = Path(configured_path)
        candidates.append(path if path.is_absolute() else PROJECT_ROOT / path)
    candidates.append(DEFAULT_TEMPLATE_PATH)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if required:
        raise ReportGenerationError(
            "Report template is missing. Upload it in the admin panel."
        )
    return None


def get_application_now() -> datetime:
    timezone_name = os.environ.get("APP_TIMEZONE", "Europe/Warsaw")
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError as exc:
        raise ReportConfigurationError(
            f"Unknown application timezone: {timezone_name}"
        ) from exc


def build_report_identity(
    username: str,
    activity: str = "MONTAŻ",
    current_time: datetime | None = None,
) -> ReportIdentity:
    login_parts = [part.strip() for part in username.strip().split(".") if part.strip()]
    if len(login_parts) < 2:
        raise ReportConfigurationError(
            "Login must use the imie.nazwisko format to generate the report."
        )

    first_name = login_parts[0].capitalize()
    last_name = " ".join(part.capitalize() for part in login_parts[1:])
    now = current_time or get_application_now()
    month = POLISH_MONTHS[now.month - 1]
    safe_first_name = _filename_component(first_name)
    safe_last_name = _filename_component(last_name)
    safe_activity = _filename_component(activity)
    filename = (
        f"{safe_last_name}_{safe_first_name}_{safe_activity}_RAPORT_{month}_{now.year}.xlsx"
    ).upper()
    return ReportIdentity(
        full_name=f"{first_name} {last_name}",
        month=month,
        year=now.year,
        filename=filename,
    )


def _filename_component(value: str) -> str:
    normalized = re.sub(r"[^\w-]+", "_", value, flags=re.UNICODE).strip("_")
    if not normalized:
        raise ReportConfigurationError("A report filename component is empty.")
    return normalized


def validate_template_file(path: Path, worksheet: str) -> None:
    try:
        with ZipFile(path) as workbook:
            _validate_archive(workbook)
            _resolve_worksheet_path(workbook, worksheet)
    except (BadZipFile, KeyError, etree.XMLSyntaxError) as exc:
        raise ReportConfigurationError("The uploaded file is not a valid XLSX template.") from exc


def validate_template_bytes(data: bytes, worksheet: str) -> None:
    try:
        with ZipFile(BytesIO(data)) as workbook:
            _validate_archive(workbook)
            _resolve_worksheet_path(workbook, worksheet)
    except (BadZipFile, KeyError, etree.XMLSyntaxError) as exc:
        raise ReportConfigurationError("The uploaded file is not a valid XLSX template.") from exc


def install_template(data: bytes, original_filename: str) -> Path:
    if not original_filename.lower().endswith(".xlsx"):
        raise ReportConfigurationError("The report template must be an XLSX file.")
    settings = ReportSettingsStore().load()
    validate_template_bytes(data, settings.worksheet)
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=INSTANCE_DIR, suffix=".xlsx.tmp", delete=False
    ) as temporary_file:
        temporary_file.write(data)
        temporary_path = Path(temporary_file.name)
    os.replace(temporary_path, MANAGED_TEMPLATE_PATH)
    return MANAGED_TEMPLATE_PATH


def generate_template_report(
    schedule_data: list[dict[str, Any]],
    username: str,
    output_path: Path,
    settings: ReportSettings | None = None,
    current_time: datetime | None = None,
) -> ReportIdentity:
    settings = settings or ReportSettingsStore().load()
    settings.validate()
    identity = build_report_identity(username, settings.activity_value, current_time)
    capacity = settings.end_row - settings.start_row + 1
    if len(schedule_data) > capacity:
        raise ReportGenerationError(
            f"The report contains {len(schedule_data)} rows, but the template allows {capacity}."
        )

    template_path = get_report_template_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output_path: Path | None = None

    try:
        with ZipFile(template_path, "r") as source:
            _validate_archive(source)
            worksheet_path = _resolve_worksheet_path(source, settings.worksheet)
            worksheet_xml = source.read(worksheet_path)
            updated_xml = _populate_worksheet(
                worksheet_xml, schedule_data, settings, identity
            )
            updated_workbook_xml = _enable_automatic_recalculation(
                source.read(WORKBOOK_PATH)
            )

            with tempfile.NamedTemporaryFile(
                dir=output_path.parent,
                suffix=".xlsx.tmp",
                delete=False,
            ) as temporary_output:
                temporary_output_path = Path(temporary_output.name)

            with ZipFile(
                temporary_output_path, "w", compression=ZIP_DEFLATED
            ) as destination:
                destination.comment = source.comment
                for archive_item in source.infolist():
                    if archive_item.filename == worksheet_path:
                        content = updated_xml
                    elif archive_item.filename == WORKBOOK_PATH:
                        content = updated_workbook_xml
                    else:
                        content = source.read(archive_item.filename)
                    destination.writestr(archive_item, content)
            os.replace(temporary_output_path, output_path)
            temporary_output_path = None
    except (BadZipFile, KeyError, etree.XMLSyntaxError, OSError) as exc:
        logging.exception("Failed to generate the template report")
        raise ReportGenerationError("Failed to generate the report from its template.") from exc
    finally:
        if temporary_output_path is not None:
            temporary_output_path.unlink(missing_ok=True)

    return identity


def _validate_archive(workbook: ZipFile) -> None:
    entries = workbook.infolist()
    if len(entries) > 2_000:
        raise ReportConfigurationError("The XLSX archive contains too many files.")
    if sum(entry.file_size for entry in entries) > 100 * 1024 * 1024:
        raise ReportConfigurationError("The uncompressed XLSX template is too large.")
    required = {"[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
    if not required.issubset(workbook.namelist()):
        raise ReportConfigurationError("The XLSX template is incomplete.")


def _xml_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        remove_blank_text=False,
        recover=False,
    )


def _enable_automatic_recalculation(workbook_xml: bytes) -> bytes:
    """Tell spreadsheet applications to fully recalculate formulas on open."""
    root = etree.fromstring(workbook_xml, _xml_parser())
    calc_properties = root.find(f"{{{MAIN_NS}}}calcPr")
    if calc_properties is None:
        calc_properties = etree.Element(f"{{{MAIN_NS}}}calcPr")
        trailing_elements = {
            f"{{{MAIN_NS}}}oleSize",
            f"{{{MAIN_NS}}}customWorkbookViews",
            f"{{{MAIN_NS}}}pivotCaches",
            f"{{{MAIN_NS}}}webPublishing",
            f"{{{MAIN_NS}}}fileRecoveryPr",
            f"{{{MAIN_NS}}}webPublishObjects",
            f"{{{MAIN_NS}}}extLst",
        }
        for index, child in enumerate(root):
            if child.tag in trailing_elements:
                root.insert(index, calc_properties)
                break
        else:
            root.append(calc_properties)

    calc_properties.set("calcMode", "auto")
    calc_properties.set("calcCompleted", "0")
    calc_properties.set("calcOnSave", "1")
    calc_properties.set("fullCalcOnLoad", "1")
    calc_properties.set("forceFullCalc", "1")
    return etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )


def _resolve_worksheet_path(workbook: ZipFile, worksheet: str) -> str:
    workbook_root = etree.fromstring(workbook.read("xl/workbook.xml"), _xml_parser())
    relationship_root = etree.fromstring(
        workbook.read("xl/_rels/workbook.xml.rels"), _xml_parser()
    )
    relationship_targets = {
        relationship.get("Id"): relationship.get("Target")
        for relationship in relationship_root.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }

    for sheet in workbook_root.xpath("//m:sheets/m:sheet", namespaces=NSMAP):
        if sheet.get("name") != worksheet:
            continue
        relationship_id = sheet.get(f"{{{OFFICE_REL_NS}}}id")
        target = relationship_targets.get(relationship_id)
        if not target:
            break
        normalized = posixpath.normpath(posixpath.join("xl", target.lstrip("/")))
        if target.startswith("/"):
            normalized = target.lstrip("/")
        if (
            not normalized.startswith("xl/worksheets/")
            or normalized not in workbook.namelist()
        ):
            break
        return normalized
    raise ReportConfigurationError(f"Worksheet '{worksheet}' was not found in the template.")


def _populate_worksheet(
    worksheet_xml: bytes,
    schedule_data: list[dict[str, Any]],
    settings: ReportSettings,
    identity: ReportIdentity,
) -> bytes:
    root = etree.fromstring(worksheet_xml, _xml_parser())
    sheet_data = root.find(f"{{{MAIN_NS}}}sheetData")
    if sheet_data is None:
        raise ReportConfigurationError("The report worksheet does not contain sheet data.")

    data_columns = (
        settings.date_column,
        settings.program_title_column,
        settings.description_column,
        settings.activity_column,
        settings.hours_column,
    )
    for row_number in range(settings.start_row, settings.end_row + 1):
        row = _find_row(sheet_data, row_number)
        if row is None:
            continue
        for column in data_columns:
            cell = _find_cell(row, f"{column}{row_number}")
            if cell is not None:
                _clear_cell_value(cell)

    _write_inline_string(sheet_data, settings.full_name_cell, identity.full_name)
    _write_inline_string(sheet_data, settings.month_cell, identity.month)
    _write_number(sheet_data, settings.year_cell, identity.year)

    for offset, entry in enumerate(schedule_data):
        row_number = settings.start_row + offset
        report_date = datetime.strptime(entry["date"], "%d.%m.%Y").date()
        _write_number(
            sheet_data,
            f"{settings.date_column}{row_number}",
            _excel_date_serial(report_date),
        )
        _write_inline_string(
            sheet_data,
            f"{settings.program_title_column}{row_number}",
            str(entry.get("program_title", "")),
        )
        _write_inline_string(
            sheet_data,
            f"{settings.description_column}{row_number}",
            str(entry.get("description", "")),
        )
        _write_inline_string(
            sheet_data,
            f"{settings.activity_column}{row_number}",
            settings.activity_value,
        )
        _write_number(
            sheet_data,
            f"{settings.hours_column}{row_number}",
            float(entry["duration"]),
        )

    return etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )


def _excel_date_serial(value: date) -> int:
    return (value - date(1899, 12, 30)).days


def _find_row(sheet_data: etree._Element, row_number: int) -> etree._Element | None:
    rows = sheet_data.xpath(f"m:row[@r='{row_number}']", namespaces=NSMAP)
    return rows[0] if rows else None


def _ensure_row(sheet_data: etree._Element, row_number: int) -> etree._Element:
    existing = _find_row(sheet_data, row_number)
    if existing is not None:
        return existing
    row = etree.Element(f"{{{MAIN_NS}}}row", r=str(row_number))
    for index, candidate in enumerate(sheet_data.findall(f"{{{MAIN_NS}}}row")):
        if int(candidate.get("r", "0")) > row_number:
            sheet_data.insert(index, row)
            return row
    sheet_data.append(row)
    return row


def _find_cell(row: etree._Element, reference: str) -> etree._Element | None:
    cells = row.xpath(f"m:c[@r='{reference}']", namespaces=NSMAP)
    return cells[0] if cells else None


def _ensure_cell(sheet_data: etree._Element, reference: str) -> etree._Element:
    match = CELL_RE.fullmatch(reference)
    if not match:
        raise ReportConfigurationError(f"Invalid Excel cell reference: {reference}")
    column, row_text = match.groups()
    row = _ensure_row(sheet_data, int(row_text))
    existing = _find_cell(row, reference)
    if existing is not None:
        return existing

    cell = etree.Element(f"{{{MAIN_NS}}}c", r=reference)
    column_index = _column_index(column)
    for index, candidate in enumerate(row.findall(f"{{{MAIN_NS}}}c")):
        candidate_match = CELL_RE.fullmatch(candidate.get("r", ""))
        if candidate_match and _column_index(candidate_match.group(1)) > column_index:
            row.insert(index, cell)
            return cell
    row.append(cell)
    return cell


def _column_index(column: str) -> int:
    result = 0
    for character in column:
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def _clear_cell_value(cell: etree._Element) -> None:
    cell.attrib.pop("t", None)
    for child in list(cell):
        if child.tag in {
            f"{{{MAIN_NS}}}f",
            f"{{{MAIN_NS}}}v",
            f"{{{MAIN_NS}}}is",
        }:
            cell.remove(child)


def _write_inline_string(
    sheet_data: etree._Element, reference: str, value: str
) -> None:
    cell = _ensure_cell(sheet_data, reference)
    _clear_cell_value(cell)
    cell.set("t", "inlineStr")
    inline_string = etree.SubElement(cell, f"{{{MAIN_NS}}}is")
    text = etree.SubElement(inline_string, f"{{{MAIN_NS}}}t")
    if value != value.strip():
        text.set(f"{{{XML_NS}}}space", "preserve")
    text.text = value


def _write_number(
    sheet_data: etree._Element, reference: str, value: int | float
) -> None:
    cell = _ensure_cell(sheet_data, reference)
    _clear_cell_value(cell)
    cell_value = etree.SubElement(cell, f"{{{MAIN_NS}}}v")
    cell_value.text = format(value, ".15g")
