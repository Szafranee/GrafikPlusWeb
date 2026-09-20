import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from backend.admin import _validate_program_titles
from backend.config import DEFAULT_INSTALLATION_FILENAME
from backend.reporting import ReportConfigurationError


class AdminTests(unittest.TestCase):
    def test_admin_requires_configuration(self):
        with patch.dict(
            os.environ, {"ADMIN_USERNAME": "", "ADMIN_PASSWORD": ""}, clear=False
        ):
            response = create_app().test_client().get("/admin/")
        self.assertEqual(response.status_code, 503)

    def test_admin_uses_http_basic_auth(self):
        with patch.dict(
            os.environ,
            {"ADMIN_USERNAME": "operator", "ADMIN_PASSWORD": "correct-secret"},
        ):
            client = create_app().test_client()
            unauthorized = client.get("/admin/")
            token = base64.b64encode(b"operator:correct-secret").decode("ascii")
            authorized = client.get(
                "/admin/", headers={"Authorization": f"Basic {token}"}
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertIn("Basic realm=", unauthorized.headers["WWW-Authenticate"])
        self.assertEqual(authorized.status_code, 200)
        self.assertIn("Panel administratora", authorized.get_data(as_text=True))

    def test_csv_validation(self):
        _validate_program_titles("Opis;Tytuł\nMECZ;Sport\n".encode(), "titles.csv")
        with self.assertRaises(ReportConfigurationError):
            _validate_program_titles(b"only-one-column\n", "titles.csv")

    def test_admin_can_download_current_template_and_program_titles(self):
        token = base64.b64encode(b"operator:correct-secret").decode("ascii")
        headers = {"Authorization": f"Basic {token}"}
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            template_path = directory_path / "template.xlsx"
            csv_path = directory_path / "program_titles.csv"
            template_path.write_bytes(b"template-content")
            csv_content = "Opis;Tytuł\nMECZ;Sport\n".encode("utf-8")
            csv_path.write_bytes(csv_content)

            with (
                patch.dict(
                    os.environ,
                    {"ADMIN_USERNAME": "operator", "ADMIN_PASSWORD": "correct-secret"},
                ),
                patch("backend.admin.get_report_template_path", return_value=template_path),
                patch("backend.admin.PROGRAM_TITLES_PATH", csv_path),
            ):
                client = create_app().test_client()
                template_response = client.get(
                    "/admin/template/download", headers=headers, buffered=True
                )
                csv_response = client.get(
                    "/admin/program-titles/download", headers=headers, buffered=True
                )

        self.assertEqual(template_response.status_code, 200)
        self.assertEqual(template_response.data, b"template-content")
        self.assertIn("attachment", template_response.headers["Content-Disposition"])
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response.data, csv_content)
        self.assertIn("attachment", csv_response.headers["Content-Disposition"])

    def test_export_config_contains_filename_preview_data(self):
        response = create_app().test_client().get("/api/export-config")

        self.assertEqual(response.status_code, 200)
        config = response.get_json()
        self.assertIsInstance(config["templateExportEnabled"], bool)
        self.assertIsInstance(config["activityValue"], str)
        self.assertTrue(config["activityValue"])
        self.assertTrue(config["month"])
        self.assertIsInstance(config["year"], int)

    def test_schedule_response_uses_generated_report_filename(self):
        class PassengerFileWrapper:
            def __init__(self, file_like, *_args):
                file_like.fileno()

        class FakeScraper:
            def __init__(self, config):
                self.config = config
                self.assert_default_filename = (
                    config.output_filename == DEFAULT_INSTALLATION_FILENAME
                )

            def scrape_schedule(self):
                if not self.assert_default_filename:
                    raise AssertionError("Unexpected default output filename")
                Path(self.config.output_dir, self.config.output_filename).write_bytes(
                    b"xlsx-content"
                )
                return "KOWALSKI_JAN_MONTAŻ_RAPORT_MAJ_2026.XLSX"

        with patch("backend.api.routes.ScheduleScraper", FakeScraper):
            response = create_app().test_client().post(
                "/api/schedule",
                json={
                    "username": "jan.kowalski",
                    "password": "secret",
                    "startDate": "2026-05-18",
                    "endDate": "2026-05-18",
                    "isPersonal": True,
                },
                environ_overrides={"wsgi.file_wrapper": PassengerFileWrapper},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"xlsx-content")
        self.assertIn(
            "KOWALSKI_JAN_",
            response.headers["Content-Disposition"],
        )


if __name__ == "__main__":
    unittest.main()
