from flask import Flask, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from backend.api.routes import api_blueprint
from backend.admin import admin_blueprint
from backend.config import DEFAULT_INSTALLATION_FILENAME
import os
from pathlib import Path

def create_app():
    # Path to the base directory
    base_dir = Path(__file__).parent
    load_dotenv(base_dir / '.env')

    app = Flask(__name__,
                static_folder=str(base_dir / 'frontend/static'),
                template_folder=str(base_dir / 'frontend/templates'))

    # Enable CORS
    CORS(app)

    # Production settings
    app.config.update(
        ENV='production',
        DEBUG=False,
        TESTING=False,
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-key-change-in-production'),
        PREFERRED_URL_SCHEME='https',
        MAX_CONTENT_LENGTH=32 * 1024 * 1024
    )

    # Basic configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

    @app.route('/')
    def index():
        try:
            return render_template(
                'index.html',
                default_installation_filename=DEFAULT_INSTALLATION_FILENAME,
            )
        except Exception as e:
            return f"Error loading template: {str(e)}"

    app.register_blueprint(api_blueprint, url_prefix='/api')
    app.register_blueprint(admin_blueprint, url_prefix='/admin')

    return app
