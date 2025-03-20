import os
from dataclasses import dataclass
from pathlib import Path
from backend.program_titles import ProgramTitles

@dataclass
class ScheduleConfig:
    # Authentication data
    username: str
    password: str

    # Export settings
    output_dir: str
    output_filename: str

    # Schedule preferences
    start_date: str
    end_date: str
    is_personal: bool

    # Program titles file
    program_titles_csv: str = os.path.join(os.path.dirname(__file__), "data", "program_titles.csv")


    def get_full_output_path(self) -> Path:
        return Path(self.output_dir) / self.output_filename

    def get_program_titles_dict(self) -> dict:
        """Get program titles using singleton"""
        return ProgramTitles().get_titles(self.program_titles_csv)

@dataclass
class ScraperConfig:
    """Configuration storage class for web scraping operations"""
    login_url: str = 'https://gpt.canalplus.pl/Account/Login'
    general_schedule_url: str = 'https://gpt.canalplus.pl/Schedule/Editing'
    personal_schedule_url: str = 'https://gpt.canalplus.pl/User/Schedule'
    parser: str = 'html.parser'
    encoding: str = 'utf-8'
    request_timeout: int = 30
