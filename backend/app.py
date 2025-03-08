from flask import Flask, render_template
from flask_cors import CORS
from backend.api.routes import api_blueprint

def create_app():
    app = Flask(__name__,
                static_folder='../frontend/static',
                template_folder='../frontend/templates')

    # Enable CORS
    CORS(app)

    # Register blueprints
    app.register_blueprint(api_blueprint, url_prefix='/api')

    @app.route('/')
    def index():
        return render_template('index.html')

    return app