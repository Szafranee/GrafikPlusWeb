from flask import Blueprint, request, jsonify, send_file, current_app
from backend.config import ScheduleConfig
from backend.schedule_scraper import ScheduleScraper
import tempfile
import os
import shutil

api_blueprint = Blueprint('api', __name__)

@api_blueprint.route('/health', methods=['GET'])
def health_check():
    """Test endpoint to check if API is working"""
    return jsonify({"status": "ok"})

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
            output_filename='schedule.xlsx',
            start_date=data['startDate'],
            end_date=data['endDate'],
            is_personal=data['isPersonal']
        )

        try:
            # Get schedule
            scraper = ScheduleScraper(config)
            scraper.scrape_schedule()

            # Get file path
            file_path = os.path.join(temp_dir, 'schedule.xlsx')

            # Check if file exists
            if not os.path.exists(file_path):
                return jsonify({
                    "title": "Błąd generowania pliku",
                    "message": "Nie udało się wygenerować pliku grafiku"
                }), 500

            # Return file and ensure it's closed after sending
            return send_file(
                file_path,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='grafik.xlsx'
            )

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