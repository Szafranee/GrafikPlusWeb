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

# 2. Include only the .venv site-packages matching Passenger's Python ABI.
# Pure-Python dependencies can appear to work across minor versions, while
# compiled extensions (for example lxml.etree) fail with a misleading import
# error. Never add a site-packages directory from a different Python version.
runtime_python_dir = f"python{sys.version_info.major}.{sys.version_info.minor}"
venv_site_packages = os.path.join(
    APP_DIR, ".venv", "lib", runtime_python_dir, "site-packages"
)
available_venv_versions = glob.glob(
    os.path.join(APP_DIR, ".venv", "lib", "python*", "site-packages")
)

venv_mismatch = None
if os.path.isdir(venv_site_packages):
    site.addsitedir(venv_site_packages)
elif available_venv_versions:
    available = ", ".join(
        os.path.basename(os.path.dirname(path)) for path in available_venv_versions
    )
    venv_mismatch = (
        "Passenger/.venv Python mismatch: Passenger uses "
        f"{sys.version_info.major}.{sys.version_info.minor}, but .venv contains: "
        f"{available}. Recreate .venv with the Passenger Python version."
    )

# 3. Safely import the application with error handling
try:
    if venv_mismatch:
        raise RuntimeError(venv_mismatch)
    from run import application
except Exception:
    error_traceback = traceback.format_exc()
    print(error_traceback, file=sys.stderr, flush=True)

    def application(environ, start_response):
        status = '500 Internal Server Error'
        output = (
            "<h2>Application Startup Error</h2>"
            "<p>Szczegóły zapisano w logu stderr aplikacji.</p>"
        ).encode('utf-8')
        response_headers = [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Content-Length', str(len(output)))
        ]
        start_response(status, response_headers)
        return [output]
