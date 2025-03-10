from flask import Flask, render_template
from flask_cors import CORS
from backend.api.routes import api_blueprint
import os
from pathlib import Path

def create_app():
    # Path to the base directory
    base_dir = Path(__file__).parent

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
        PREFERRED_URL_SCHEME='https'
    )

    # Basic configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

    @app.route('/')
    def index():
        try:
            return render_template('index.html')
        except Exception as e:
            return f"Error loading template: {str(e)}"

    app.register_blueprint(api_blueprint, url_prefix='/api')

    return app