import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from lxml import etree
from openpyxl import load_workbook

from backend.config import ScheduleConfig
from backend.reporting import (
    NSMAP,
    ReportConfigurationError,
    WORKBOOK_PATH,
    _resolve_worksheet_path,
    build_report_identity,
    generate_template_report,
)
from backend.schedule_parser import ScheduleParser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = PROJECT_ROOT / "report_template.xlsx"


class ReportingTests(unittest.TestCase):
    def test_identity_uses_login_and_current_month(self):
        identity = build_report_identity(
            "jan.kowalski",
            current_time=datetime(2026, 5, 20, 12, 0),
        )

        self.assertEqual(identity.full_name, "Jan Kowalski")
        self.assertEqual(identity.month, "MAJ")
        self.assertEqual(identity.year, 2026)
        self.assertEqual(
            identity.filename,
            "KOWALSKI_JAN_MONTAŻ_RAPORT_MAJ_2026.XLSX",
        )

    def test_identity_rejects_login_without_last_name(self):
        with self.assertRaises(ReportConfigurationError):
            build_report_identity("jan")

    def test_template_report_only_updates_data_and_calculation_settings(self):
        data = [
            {
                "date": "18.05.2026",
                "program_title": "Liga Polska",
                "description": "Mecz testowy",
                "duration": 2.5,
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "result.xlsx"
            missing_managed_template = Path(directory) / "managed.xlsx"
            with (
                patch("backend.reporting.MANAGED_TEMPLATE_PATH", missing_managed_template),
                patch("backend.reporting.DEFAULT_TEMPLATE_PATH", TEMPLATE_PATH),
                patch.dict(os.environ, {}, clear=False),
            ):
                os.environ.pop("REPORT_TEMPLATE_PATH", None)
                generate_template_report(
                    data,
                    "jan.kowalski",
                    output_path,
                    current_time=datetime(2026, 5, 20, 12, 0),
                )

            with ZipFile(TEMPLATE_PATH) as source, ZipFile(output_path) as result:
                worksheet_path = _resolve_worksheet_path(source, "Raport")
                self.assertEqual(source.namelist(), result.namelist())
                changed_entries = [
                    name
                    for name in source.namelist()
                    if source.read(name) != result.read(name)
                ]
                self.assertEqual(
                    set(changed_entries), {worksheet_path, WORKBOOK_PATH}
                )
                self.assertEqual(
                    source.read(worksheet_path).count(b"<f"),
                    result.read(worksheet_path).count(b"<f"),
                )

                root = etree.fromstring(result.read(worksheet_path))
                self.assertEqual(self._cell_text(root, "F3"), "Jan Kowalski")
                self.assertEqual(self._cell_text(root, "H2"), "MAJ")
                self.assertEqual(self._cell_value(root, "H3"), "2026")
                self.assertEqual(self._cell_value(root, "E7"), "46160")
                self.assertEqual(self._cell_text(root, "F7"), "Liga Polska")
                self.assertEqual(self._cell_text(root, "G7"), "Mecz testowy")
                self.assertEqual(self._cell_text(root, "H7"), "MONTAŻ")
                self.assertEqual(self._cell_value(root, "J7"), "2.5")

                workbook_root = etree.fromstring(result.read(WORKBOOK_PATH))
                calculation = workbook_root.xpath(
                    "/m:workbook/m:calcPr", namespaces=NSMAP
                )[0]
                self.assertEqual(calculation.get("calcMode"), "auto")
                self.assertEqual(calculation.get("calcCompleted"), "0")
                self.assertEqual(calculation.get("calcOnSave"), "1")
                self.assertEqual(calculation.get("fullCalcOnLoad"), "1")
                self.assertEqual(calculation.get("forceFullCalc"), "1")

    def test_legacy_export_remains_available(self):
        with tempfile.TemporaryDirectory() as directory:
            config = ScheduleConfig(
                username="jan.kowalski",
                password="secret",
                output_dir=directory,
                output_filename="legacy.xlsx",
                start_date="2026-05-18",
                end_date="2026-05-18",
                is_personal=True,
                use_template_export=False,
            )
            parser = ScheduleParser("", config)
            parser.set_parsed_data(
                [
                    {
                        "date": "18.05.2026",
                        "program_title": "Liga Polska",
                        "description": "Mecz testowy",
                        "activity": "",
                        "duration": 2.5,
                        "start_time": "10:00",
                        "end_time": "12:30",
                    }
                ]
            )

            self.assertEqual(parser.save_to_xlsx(), "legacy.xlsx")
            workbook = load_workbook(Path(directory) / "legacy.xlsx", read_only=True)
            self.assertEqual(workbook.active["A2"].value, "18.05.2026")
            workbook.close()

    @staticmethod
    def _cell(root, reference):
        return root.xpath(f"//m:c[@r='{reference}']", namespaces=NSMAP)[0]

    @classmethod
    def _cell_text(cls, root, reference):
        return "".join(
            cls._cell(root, reference).xpath(".//m:t/text()", namespaces=NSMAP)
        )

    @classmethod
    def _cell_value(cls, root, reference):
        values = cls._cell(root, reference).xpath("./m:v/text()", namespaces=NSMAP)
        return values[0] if values else None


if __name__ == "__main__":
    unittest.main()
