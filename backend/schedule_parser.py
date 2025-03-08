import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import pandas as pd
from bs4 import BeautifulSoup

from backend.config import ScheduleConfig


class ScheduleParser:
    def __init__(self, html_content: str, schedule_config: ScheduleConfig):
        self.soup = BeautifulSoup(html_content, 'html.parser')
        self.schedule_data = []
        self.schedule_config = schedule_config

    @staticmethod
    def __calculate_duration(start_time: str, end_time: str) -> float:
        """Calculate duration between two times, handling day changes"""
        start = datetime.strptime(start_time, '%H:%M')
        end = datetime.strptime(end_time, '%H:%M')

        if end < start:
            end += timedelta(days=1)

        duration = end - start
        hours = duration.total_seconds() / 3600
        return round(hours, 2)

    @staticmethod
    def __convert_date(date: str) -> str:
        """Convert date to ISO format from dates like 'poniedziałek, 1 stycznia 2025'"""
        date_parts = date.split(', ')
        date_string = date_parts[1]
        day, month, year = date_string.split(' ')

        months = {
            'stycznia': '01',
            'lutego': '02',
            'marca': '03',
            'kwietnia': '04',
            'maja': '05',
            'czerwca': '06',
            'lipca': '07',
            'sierpnia': '08',
            'września': '09',
            'października': '10',
            'listopada': '11',
            'grudnia': '12'
        }

        month = months[month]
        return f"{day}.{month}.{year}"

    @staticmethod
    def __is_date_row(row) -> bool:
        """Check if the row contains a date header"""
        return bool(row.find('th', class_='gpt-table-section-header'))

    def __get_date_from_row(self, row) -> Optional[str]:
        """Extract and convert date from a date row"""
        date_header = row.find('th', class_='gpt-table-section-header')
        if date_header:
            return self.__convert_date(date_header.text.strip())
        return None

    def parse_general_schedule(self) -> List[Dict]:
        """Parse schedule data from HTML content with sequential row processing"""
        current_date = None
        all_rows = self.soup.find_all('tr')

        for row in all_rows:
            # Check if this is a date row
            if self.__is_date_row(row):
                current_date = self.__get_date_from_row(row)
                continue

            # Skip rows without date context
            if not current_date:
                continue

            cells = row.find_all('td')
            if not cells:
                continue

            program_cell = row.find('span')
            if not program_cell:
                continue

            try:
                program_description = program_cell.text.strip()

                time_cell = cells[4].find('tr', class_='text-bold')
                if not time_cell:
                    continue

                times = time_cell.text.strip().replace('\xa0', ' ').split(' ')
                start_time = times[0].replace('\n', '')
                end_time = times[2].replace('\n', '')
                duration = self.__calculate_duration(start_time, end_time)
                editor = cells[11].text.strip()

                # program_title and activity columns are always empty because that's what the "client" wanted
                self.schedule_data.append({
                    'date': current_date,
                    'program_title': '', # Always empty
                    'description': program_description,
                    'activity': '', # Always empty
                    'duration': duration,
                    'start_time': start_time,
                    'end_time': end_time,
                    'editor': editor
                })
            except AttributeError as e:
                logging.warning(f"Error parsing row: {e}")
                continue
            except IndexError:
                continue

        return self.schedule_data

    def parse_personal_schedule(self) -> List[Dict]:
        """Parse personal schedule data with sequential row processing"""
        current_date = None
        all_rows = self.soup.find_all('tr')

        for row in all_rows:
            # Check if this is a date row
            if self.__is_date_row(row):
                current_date = self.__get_date_from_row(row)
                continue

            # Skip rows without date context
            if not current_date:
                continue

            try:
                program_table = row.find('td')
                if not program_table:
                    continue

                program_table = program_table.find('table')
                if not program_table:
                    continue

                program_cell = program_table.find('span')
                if not program_cell:
                    continue

                program_description = program_cell.text.strip()

                time_cell = row.find('span', class_='text-bold')
                if not time_cell:
                    continue

                # Parse time information
                times = time_cell.text.strip().split('-')
                if len(times) != 2:
                    continue

                start_time = times[0].strip().replace('\xa0', '')
                end_time = times[1].strip().replace('\xa0', '')
                duration = self.__calculate_duration(start_time, end_time)

                # program_title and activity columns are always empty because that's what the "client" wanted
                self.schedule_data.append({
                    'date': current_date,
                    'program_title': '', # Always empty
                    'description': program_description,
                    'activity': '', # Always empty
                    'duration': duration,
                    'start_time': start_time,
                    'end_time': end_time,
                })
            except (AttributeError, IndexError) as e:
                logging.warning(f"Error parsing row: {e}")
                continue

        return self.schedule_data

    def parse_schedule(self) -> None:
        """Parse schedule data from HTML content"""
        if self.schedule_config.is_personal:
            self.parse_personal_schedule()
        else:
            self.parse_general_schedule()

    def get_parsed_data(self) -> List[Dict]:
        """Return the parsed schedule data"""
        return self.schedule_data

    def set_parsed_data(self, data: List[Dict]) -> None:
        """Set the parsed schedule data directly"""
        self.schedule_data = data

    def save_to_xlsx(self) -> None:
        """Save parsed schedule to Excel file with proper Polish locale handling"""
        headers = ['Data', 'Tytuł programu', 'Opis', 'Czynność', 'Liczba godzin', 'Od', 'Do'] if self.schedule_config.is_personal \
            else ['Data', 'Tytuł programu', 'Opis', 'Czynność', 'Liczba godzin', 'Od', 'Do', 'Montażysta']

        output_file_path = self.schedule_config.get_full_output_path()
        output_dir = Path(self.schedule_config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Prepare data for DataFrame
        data = []
        for entry in self.schedule_data:
            row = [
                entry['date'],
                entry['program_title'],
                entry['description'],
                entry['activity'],
                float(entry['duration']),
                entry['start_time'],
                entry['end_time']
            ]
            if not self.schedule_config.is_personal:
                row.append(entry['editor'])
            data.append(row)

        df = pd.DataFrame(data, columns=headers)

        try:
            writer = pd.ExcelWriter(
                output_file_path,
                engine='openpyxl'
            )

            # Save DataFrame to Excel
            df.to_excel(writer, index=False)

            # Access the sheet
            worksheet = writer.sheets['Sheet1']

            # Formating the hours column
            col_idx = headers.index('Liczba godzin') + 1
            for row in range(2, len(df) + 2):
                cell = worksheet.cell(row=row, column=col_idx)
                # Format the cell as number with two decimal places
                cell.number_format = '#,##0.00'

                # We make sure that the value is a float
                try:
                    cell.value = float(cell.value)
                except (ValueError, TypeError):
                    logging.warning(f"Could not convert value {cell.value} to float")

            # Adjust column widths
            for idx, col in enumerate(worksheet.columns, 1):
                max_length = 0
                column = worksheet.column_dimensions[chr(64 + idx)]

                for cell in col:
                    try:
                        max_length = max(max_length, len(str(cell.value)))
                    except TypeError:
                        pass

                adjusted_width = (max_length + 2)
                column.width = adjusted_width

            writer.close()
            logging.info(f"Schedule saved successfully to {output_file_path}")

        except PermissionError:
            logging.error(f"Permission denied when saving to {output_file_path}")
            raise PermissionError({"title": "Błąd w dostępie do pliku!",
                                   "message": f"Brak uprawnień do zapisu pliku: \nSprawdź, czy {output_file_path} nie jest otwarty w innym programie."})
        except Exception as e:
            logging.error(f"Error saving Excel file: {str(e)}")
            raise Exception({"title": "Nieznany błąd zapisu pliku!",
                             "message": "Coś poszło nie tak podczas zapisu pliku. Spróbuj ponownie."})