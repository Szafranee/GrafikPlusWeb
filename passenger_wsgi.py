import sys
import os
import site
import glob
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Add the project directories to sys.path
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

backend_dir = os.path.join(APP_DIR, "backend")
if os.path.exists(backend_dir) and backend_dir not in sys.path:
    sys.path.insert(1, backend_dir)

# 2. Include libraries from the local .venv environment created by uv
venv_site_packages = glob.glob(os.path.join(APP_DIR, ".venv", "lib", "python*", "site-packages"))
if venv_site_packages:
    site.addsitedir(venv_site_packages[0])

# 3. Safely import the application with error handling
try:
    from run import application
except Exception:
    error_traceback = traceback.format_exc()

    def application(environ, start_response):
        status = '500 Internal Server Error'
        output = f"<h2>Application Startup Error</h2><pre>{error_traceback}</pre>".encode('utf-8')
        response_headers = [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Content-Length', str(len(output)))
        ]
        start_response(status, response_headers)
        return [output]
