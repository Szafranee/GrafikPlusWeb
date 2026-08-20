import unittest
from pathlib import Path
from unittest.mock import patch

from backend.config import ScheduleConfig
from backend.schedule_parser import ScheduleParser


FIXTURES = Path(__file__).parent / "fixtures"


def _config(is_personal: bool) -> ScheduleConfig:
    return ScheduleConfig(
        username="jan.kowalski",
        password="secret",
        output_dir=".",
        output_filename="test.xlsx",
        start_date="2026-05-18",
        end_date="2026-05-18",
        is_personal=is_personal,
        use_template_export=False,
    )


class ScheduleParserTests(unittest.TestCase):
    def test_personal_schedule_contract_and_overnight_duration(self):
        config = _config(is_personal=True)
        html = (FIXTURES / "personal_schedule.html").read_text(encoding="utf-8")

        with patch.object(
            config,
            "get_program_titles_dict",
            return_value={"MECZ TESTOWY": "Liga Polska"},
        ):
            parser = ScheduleParser(html, config)
            parser.parse_schedule()

        self.assertEqual(
            parser.get_parsed_data(),
            [
                {
                    "date": "18.05.2026",
                    "program_title": "Liga Polska",
                    "description": "MECZ TESTOWY",
                    "activity": "",
                    "duration": 2.5,
                    "start_time": "22:30",
                    "end_time": "01:00",
                }
            ],
        )

    def test_general_schedule_contract_includes_editor(self):
        config = _config(is_personal=False)
        html = (FIXTURES / "general_schedule.html").read_text(encoding="utf-8")

        with patch.object(
            config,
            "get_program_titles_dict",
            return_value={"MECZ TESTOWY": "Liga Polska"},
        ):
            parser = ScheduleParser(html, config)
            parser.parse_schedule()

        self.assertEqual(
            parser.get_parsed_data(),
            [
                {
                    "date": "18.05.2026",
                    "program_title": "Liga Polska",
                    "description": "MECZ TESTOWY",
                    "activity": "",
                    "duration": 2.5,
                    "start_time": "22:30",
                    "end_time": "01:00",
                    "editor": "Jan Montażysta",
                }
            ],
        )

    def test_incomplete_schedule_row_is_ignored_without_crashing(self):
        config = _config(is_personal=False)
        html = """
            <table>
                <tr><th class="gpt-table-section-header">poniedziałek, 18 maja 2026</th></tr>
                <tr><td><span>Niepełny wpis</span></td></tr>
            </table>
        """

        parser = ScheduleParser(html, config)
        parser.parse_schedule()

        self.assertEqual(parser.get_parsed_data(), [])


if __name__ == "__main__":
    unittest.main()
