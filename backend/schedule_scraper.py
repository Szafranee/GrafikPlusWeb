import logging
from typing import Optional, List
from datetime import datetime, timedelta
import os
import requests

from backend.config import ScheduleConfig, ScraperConfig
from backend.schedule_parser import ScheduleParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        # logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)


class LoginError(Exception):
    """Raised when login fails"""
    pass


class ScheduleFetchError(Exception):
    """Raised when fetching schedule fails"""
    pass


class ScheduleScraper:
    def __init__(self, schedule_config: ScheduleConfig):
        self.config = ScraperConfig()
        self.session = requests.Session()
        self.schedule_data = []
        self.schedule_config = schedule_config

    @staticmethod
    def __convert_date_to_url_format(date: str) -> str:
        """Convert date to URL format from dates like '01/01/2025'"""
        day, month, year = date.split('.')
        return f"{month}%2F{day}%2F{year}%2000%3A00%3A00"

    @staticmethod
    def __parse_date(date_str: str) -> datetime:
        """Parse date string in format DD.MM.YYYY to datetime object"""
        year, month, day = map(int, date_str.split('-'))
        return datetime(year, month, day)

    @staticmethod
    def __format_date(date: datetime) -> str:
        """Format datetime object to string in format DD.MM.YYYY"""
        return date.strftime("%d.%m.%Y")

    def __get_dates_in_range(self) -> List[str]:
        """Get first day of each week in range from start_date to end_date"""
        start_date = self.__parse_date(self.schedule_config.start_date)
        end_date = self.__parse_date(self.schedule_config.end_date)

        # If end_date is before start_date, swap them
        if end_date < start_date:
            start_date, end_date = end_date, start_date

        # Get first day of each week in range
        dates = []

        # Adjust start_date to the beginning of the week (Monday)
        # In Python, weekday() returns 0 for Monday, 6 for Sunday
        days_to_subtract = start_date.weekday()
        current_date = start_date - timedelta(days=days_to_subtract)

        # Iterate through weeks until we pass the end_date
        while current_date <= end_date:
            dates.append(self.__format_date(current_date))
            # Move to next Monday
            current_date += timedelta(days=7)

        return dates

    def __login(self) -> bool:
        """Perform login to the system"""
        try:
            payload = {
                'username': self.schedule_config.username,
                'password': self.schedule_config.password
            }
            response = self.session.post(
                self.config.login_url,
                data=payload,
                timeout=self.config.request_timeout
            )
            response.raise_for_status()

            # Check for error message in response
            error_message = "Niepoprawny identyfikator lub hasło."
            if error_message in response.text:
                logging.error("Invalid credentials")
                return False

            logging.info("Login successful")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Login error: {e}")
            return False

    def __fetch_schedule(self, date: str) -> Optional[str]:
        """Fetch schedule HTML content for a specific date"""
        schedule_url = self.config.personal_schedule_url if self.schedule_config.is_personal else self.config.general_schedule_url

        date_url = self.__convert_date_to_url_format(date)

        schedule_url += f"?date={date_url}"  # Add date to URL

        try:
            response = self.session.get(
                schedule_url,
                timeout=self.config.request_timeout
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching schedule for date {date}: {e}")
            return None

    def scrape_schedule(self):
        """Main execution function"""
        if not self.__login():
            logging.error("Login failed")
            raise LoginError({"title": "Błąd uwierzytelniania", "message": "Niepoprawny identyfikator lub hasło."})

        # Get first day of each week in range
        dates = self.__get_dates_in_range()

        # Create a directory for temporary files if needed
        temp_dir = os.path.join(self.schedule_config.output_dir, "temp_schedules")
        os.makedirs(temp_dir, exist_ok=True)

        all_data = []

        # Fetch schedule for each week
        for date in dates:
            logging.info(f"Fetching schedule for week starting {date}")
            html_content = self.__fetch_schedule(date)
            if not html_content:
                logging.error(f"Failed to fetch schedule for week starting {date}")
                continue

            # Parse the schedule
            parser = ScheduleParser(html_content, self.schedule_config)
            parser.parse_schedule()

            # Add the parsed data to the combined data
            all_data.extend(parser.get_parsed_data())

        if not all_data:
            logging.error("No schedule data was fetched")
            raise ScheduleFetchError(
                {"title": "Błąd pobierania grafiku", "message": "Z jakiegoś powodu nie udało się pobrać planu. :("})

        # Save the combined data
        try:
            # Create a new parser with the combined data
            combined_parser = ScheduleParser("", self.schedule_config)
            combined_parser.set_parsed_data(all_data)
            combined_parser.save_to_xlsx()
        except PermissionError as e:
            raise PermissionError({"title": e.args[0]["title"],
                                   "message": e.args[0]["message"]})

        logging.info(f"Schedule saved to {self.schedule_config.output_filename}")

        # Clean up temporary files
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except Exception as e:
            logging.warning(f"Failed to clean up temporary files: {e}")