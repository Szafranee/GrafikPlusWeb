from flask import Flask, render_template
from flask_cors import CORS
from backend.api.routes import api_blueprint
import os

class Config:
    """Base config"""
    SECRET_KEY = os.environ.get('SECRET_KEY', None)
    DEBUG = False
    TESTING = False

class DevelopmentConfig(Config):
    """Development config"""
    SECRET_KEY = 'dev-key-only-for-development'
    DEBUG = True
    CORS_ORIGINS = ['http://localhost:5000']

class ProductionConfig(Config):
    """Production config"""
    DEBUG = False
    if not Config.SECRET_KEY:
        raise ValueError("No SECRET_KEY set for production environment")
    CORS_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '').split(',')

def create_app():
    env = os.environ.get('FLASK_ENV', 'development')
    if env == 'production':
        config = ProductionConfig
    else:
        config = DevelopmentConfig

    app = Flask(__name__,
                static_folder='../frontend/static',
                template_folder='../frontend/templates')

    app.config.from_object(config)

    # Initialize CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": config.CORS_ORIGINS,
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type"]
        }
    })

    # Register blueprints
    app.register_blueprint(api_blueprint, url_prefix='/api')

    @app.route('/')
    def index():
        return render_template('index.html')

    return app