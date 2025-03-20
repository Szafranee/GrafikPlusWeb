from typing import Dict
import csv
import logging
import os
from datetime import datetime


class ProgramTitles:
    _instance = None
    _titles_dict: Dict[str, str] = None
    _last_modified: float = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProgramTitles, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_titles(cls, csv_path: str) -> Dict[str, str]:
        """Get program titles dictionary with automatic refresh on file change"""
        try:
            # Check if file has been modified
            current_modified_time = os.path.getmtime(csv_path)
            
            # Load dictionary if it's first time or file was modified
            if cls._titles_dict is None or current_modified_time > cls._last_modified:
                logging.info(f"Loading titles from CSV (last modified: {datetime.fromtimestamp(current_modified_time)})")
                cls._titles_dict = cls._load_titles(csv_path)
                cls._last_modified = current_modified_time
                
        except OSError as e:
            logging.error(f"Error checking file modification time: {e}")
            if cls._titles_dict is None:
                cls._titles_dict = {}
                
        return cls._titles_dict

    @classmethod
    def reload_titles(cls, csv_path: str) -> None:
        """Force reload of program titles"""
        cls._titles_dict = cls._load_titles(csv_path)
        try:
            cls._last_modified = os.path.getmtime(csv_path)
        except OSError as e:
            logging.error(f"Error checking file modification time during reload: {e}")
            cls._last_modified = 0

    @staticmethod
    def _load_titles(csv_path: str) -> Dict[str, str]:
        """Load program titles from CSV file"""
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')  # Dodajemy delimiter=';'
                titles = {rows[0]: rows[1].strip('"') for rows in reader}
            logging.info(f"Program titles loaded successfully: {len(titles)} entries")
            return titles
        except FileNotFoundError:
            logging.error(f"File not found: {csv_path}")
            return {}
        except Exception as e:
            logging.error(f"Error loading program titles: {e}")
            return {}
