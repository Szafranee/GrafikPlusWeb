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

Skipping the restart does not skip `uv sync` when dependency metadata is deployed.

### Presets

| Preset | Contents and behavior |
| --- | --- |
| `changed` | Compares local and remote MD5 hashes for every tracked file and uploads only new or modified files. |
| `all` | Uploads application files, `.python-version`, dependency metadata, backend code, and frontend assets. |
| `dependencies` | Uploads `pyproject.toml` and `uv.lock`, runs remote `uv sync`, and restarts Passenger unless restart is disabled. |
| `backend` | Uploads the application entry points and `backend/`. |
| `frontend` | Uploads `frontend/`. |
| `python` | Uploads the configured Python source files. |
| `csv` | Uploads the program-title mapping CSV. |
| `static` | Uploads frontend static assets. |
| `config` | Uploads `backend/config.py`. |

The interactive `custom` option searches for paths by full or partial name. Explicit file lists are also available through the flags above.

When `pyproject.toml` or `uv.lock` is selected directly, included by a preset, or detected as changed, the script runs this command after upload:

```bash
cd "${REMOTE_APP_DIR}" && uv sync --frozen --no-dev
```

If dependency synchronization fails, the deployment exits without restarting the application. Directory uploads are expanded into individual files; `.venv/`, `.uv/`, and `__pycache__/` are always excluded from SCP.

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
