from dataclasses import dataclass
from pathlib import Path

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

    def get_full_output_path(self) -> Path:
        return Path(self.output_dir) / self.output_filename

@dataclass
class ScraperConfig:
    """Configuration storage class for web scraping operations"""
    login_url: str = 'https://gpt.canalplus.pl/Account/Login'
    general_schedule_url: str = 'https://gpt.canalplus.pl/Schedule/Editing'
    personal_schedule_url: str = 'https://gpt.canalplus.pl/User/Schedule'
    parser: str = 'html.parser'
    encoding: str = 'utf-8'
    request_timeout: int = 30