import sys, os

# Add the application directory to the Python path
INTERP = os.path.expanduser("/virtualenv/bin/python")
if os.path.exists(INTERP):
    os.execl(INTERP, INTERP, *sys.argv)

cwd = os.getcwd()
sys.path.append(cwd)
sys.path.append(cwd + '/backend')  # Optional but good for nested imports

# Point to the application object
# We import 'application' from 'run.py' because 'app.py' uses a factory pattern (create_app)
from run import application

