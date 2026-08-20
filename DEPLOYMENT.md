# Deployment

GrafikPlusWeb includes equivalent deployment scripts for PowerShell (`deploy.ps1`) and Bash (`deploy.sh`). They upload selected files over SCP, synchronize production dependencies with `uv` when needed, and trigger a Phusion Passenger restart.

## Configuration

Create the platform-specific configuration file from its committed example:

```powershell
Copy-Item deploy.config.ps1.example deploy.config.ps1
```

```bash
cp deploy.config.sh.example deploy.config.sh
```

Set the SSH user, host, port, optional private-key path, and absolute remote application directory. The generated configuration files are ignored by Git because they may contain server details.

The default restart command creates the Passenger `tmp` directory and touches `tmp/restart.txt`. Keep this command unless the hosting environment requires a different Passenger-compatible path.

## Usage

Run either script without arguments to open the interactive menu:

```powershell
.\deploy.ps1
```

```bash
./deploy.sh
```

The default interactive choice is `changed`. Both scripts display the selected files and request confirmation before uploading them.

### Flags

| Purpose | PowerShell | Bash |
| --- | --- | --- |
| Select a preset | `-Preset <name>` | `--preset <name>` |
| Upload explicit paths | `-Files "a.py","b.py"` | `--files "a.py,b.py"` |
| Skip the Passenger restart | `-NoRestart` | `--no-restart` |
| Preview without uploading | `-DryRun` | `--dry-run` |

Skipping the restart does not skip environment synchronization and startup validation.

### Presets

| Preset | Contents and behavior |
| --- | --- |
| `changed` | Discovers deployable Git files automatically, compares their local and remote MD5 hashes, and uploads only new or modified files. |
| `all` | Uploads every automatically discovered deployable Git file. |
| `dependencies` | Uploads `pyproject.toml` and `uv.lock`, runs remote `uv sync`, and restarts Passenger unless restart is disabled. |
| `backend` | Uploads the application entry points and `backend/`. |
| `frontend` | Uploads `frontend/`. |
| `python` | Uploads the configured Python source files. |
| `csv` | Uploads the program-title mapping CSV. |
| `static` | Uploads frontend static assets. |
| `config` | Uploads `backend/config.py`. |

The interactive `custom` option searches for paths by full or partial name. Explicit file lists are also available through the flags above.

### Automatic file discovery

The `changed`, `all`, `backend`, `frontend`, `python`, and `static` presets are
built automatically from files returned by `git ls-files --cached --others
--exclude-standard`. New tracked files and new non-ignored files therefore do
not need to be added to deployment configuration manually.

The scripts apply two exclusion levels:

- secrets and runtime state such as `.env`, `deploy.config.*`, `instance/`,
  virtual environments, caches, bytecode, and logs can never be uploaded;
- tests, documentation, repository metadata, deployment tooling, and
  `backend/data/program_titles.csv` are excluded from automatic presets.

The production program-title dictionary is intentionally protected from broad
deployments because it can be changed through the admin panel. Deploy it only
with the dedicated `csv` preset or an explicit file selection. Add exceptional
project-specific rules through `EXTRA_NEVER_DEPLOY_PATTERNS`,
`EXTRA_AUTO_DEPLOY_EXCLUDE_PATTERNS`, or `CUSTOM_DEPLOY_PRESETS` in the local
ignored config file.

Use a dry run to inspect the resolved file list without connecting to the
server, uploading files, synchronizing dependencies, or restarting Passenger:

```powershell
.\deploy.ps1 -Preset all -DryRun
```

```bash
./deploy.sh --preset all --dry-run
```

Before every restart, the script synchronizes the environment and runs a startup
preflight. This is intentionally done even for frontend-only deployments: `uv
sync` is idempotent, and the check prevents Passenger from restarting with a
stale, incomplete, or ABI-incompatible virtual environment.

```bash
uv sync --locked --no-dev
.venv/bin/python -c 'from lxml import etree; from app import create_app; create_app()'
```

The preflight also checks that `.venv` uses the Python minor version pinned in
`.python-version`. If synchronization, version validation, or application import
fails, deployment exits without restarting Passenger. Directory uploads are
expanded into individual files; `.venv/`, `.uv/`, and `__pycache__/` are always
excluded from SCP.

## Remote Requirements

The server must provide:

- SSH access for the configured account and SCP support.
- `uv` available on the non-interactive SSH `PATH`.
- The Python version declared in `.python-version`, either installed or installable by `uv`.
- A Phusion Passenger application rooted at `REMOTE_APP_DIR` with permission to create and update `tmp/restart.txt`.
- Permission to create the application directory tree and its `.venv` environment.

You can verify the server setup with:

```bash
ssh user@host 'uv --version'
```

## Examples

```powershell
.\deploy.ps1 -Preset changed
.\deploy.ps1 -Preset dependencies
.\deploy.ps1 -Files "app.py","passenger_wsgi.py" -NoRestart
```

```bash
./deploy.sh --preset changed
./deploy.sh --preset dependencies
./deploy.sh --files "app.py,passenger_wsgi.py" --no-restart
```
