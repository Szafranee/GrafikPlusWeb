from app import create_app
import os

app = create_app()
application = app  # For WSGI compatibility

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=app.config['DEBUG']
    )