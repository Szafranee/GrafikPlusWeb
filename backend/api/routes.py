from pathlib import Path
from urllib.parse import quote
import unicodedata

from flask import Blueprint, request, jsonify, current_app
from backend.config import DEFAULT_INSTALLATION_FILENAME, ScheduleConfig
from backend.reporting import (
    POLISH_MONTHS,
    ReportSettingsStore,
    get_application_now,
    template_export_enabled,
)
from backend.schedule_scraper import ScheduleScraper
import tempfile
import os
import shutil

api_blueprint = Blueprint('api', __name__)

XLSX_MIMETYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _xlsx_download_response(file_data: bytes, filename: str):
    """Return XLSX bytes without invoking the server's file-wrapper extension."""
    safe_filename = filename.replace('\r', '').replace('\n', '')
    ascii_filename = (
        unicodedata.normalize('NFKD', safe_filename)
        .encode('ascii', 'ignore')
        .decode('ascii')
        .replace('\\', '_')
        .replace('"', '_')
    ) or DEFAULT_INSTALLATION_FILENAME
    disposition = f'attachment; filename="{ascii_filename}"'
    if ascii_filename != safe_filename:
        encoded_filename = quote(safe_filename, safe='!#$&+-.^_`|~')
        disposition += f"; filename*=UTF-8''{encoded_filename}"

    response = current_app.response_class(file_data, mimetype=XLSX_MIMETYPE)
    response.headers['Content-Disposition'] = disposition
    return response

@api_blueprint.route('/health', methods=['GET'])
def health_check():
    """Test endpoint to check if API is working"""
    return jsonify({"status": "ok"})

@api_blueprint.route('/export-config', methods=['GET'])
def export_config():
    """Expose non-sensitive export mode information to the main form."""
    now = get_application_now()
    settings = ReportSettingsStore().load()
    return jsonify({
        "templateExportEnabled": template_export_enabled(),
        "activityValue": settings.activity_value,
        "month": POLISH_MONTHS[now.month - 1],
        "year": now.year,
    })

@api_blueprint.route('/schedule', methods=['POST'])
def get_schedule():
    """Main endpoint for downloading the schedule"""
    temp_dir = None
    try:
        # Get and validate input data
        data = request.get_json()
        if not data:
            return jsonify({
                "title": "Błąd danych",
                "message": "Nie przesłano żadnych danych"
            }), 400

        # Validate required fields
        required_fields = ['username', 'password', 'startDate', 'endDate', 'isPersonal']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                "title": "Brak wymaganych pól",
                "message": f"Brakujące pola: {', '.join(missing_fields)}"
            }), 400

        # Create temporary directory
        temp_dir = tempfile.mkdtemp()

        # Create config
        config = ScheduleConfig(
            username=data['username'],
            password=data['password'],
            output_dir=temp_dir,
            output_filename=DEFAULT_INSTALLATION_FILENAME,
            start_date=data['startDate'],
            end_date=data['endDate'],
            is_personal=data['isPersonal']
        )

        try:
            # Get schedule
            scraper = ScheduleScraper(config)
            download_filename = scraper.scrape_schedule()

            # Get file path
            file_path = config.get_full_output_path()

            # Check if file exists
            if not os.path.exists(file_path):
                return jsonify({
                    "title": "Błąd generowania pliku",
                    "message": "Nie udało się wygenerować pliku grafiku"
                }), 500

            # Return file and ensure it's closed after sending
            file_data = Path(file_path).read_bytes()
            return _xlsx_download_response(file_data, download_filename)

        except Exception as e:
            # Handle scraper specific errors
            if hasattr(e, 'args') and isinstance(e.args[0], dict):
                error_dict = e.args[0]
                return jsonify({
                    "title": error_dict.get('title', 'Błąd'),
                    "message": error_dict.get('message', str(e))
                }), 400

            # Handle generic errors
            return jsonify({
                "title": "Błąd pobierania grafiku",
                "message": str(e)
            }), 400

    except Exception as e:
        # Handle unexpected errors
        current_app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            "title": "Nieoczekiwany błąd",
            "message": str(e)
        }), 500

    finally:
        # Clean up temporary directory if it exists
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                current_app.logger.error(f"Failed to remove temporary directory: {e}")
