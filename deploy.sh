#!/usr/bin/env bash
# ============================================================
#  deploy.sh - Deployment script for GrafikPlusWeb (Linux/macOS)
#
#  Usage:
#    ./deploy.sh                        -> interactive menu (default: changed files)
#    ./deploy.sh --preset changed       -> only files changed vs server (default)
#    ./deploy.sh --preset all           -> all files
#    ./deploy.sh --preset backend       -> backend files only
#    ./deploy.sh --files "app.py,pyproject.toml"  -> specific files
#    ./deploy.sh --preset dependencies -> dependencies + remote uv sync
#    ./deploy.sh --preset backend --no-restart      -> skip restart
#    ./deploy.sh --preset all --dry-run              -> preview without upload
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/deploy.config.sh"

# ── Load configuration ──────────────────────────────────────
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "[ERROR] Missing deploy.config.sh - copy deploy.config.sh.example and fill in server details."
    exit 1
fi
# shellcheck source=deploy.config.sh
source "$CONFIG_FILE"

# ── Validate configuration ──────────────────────────────────
if [[ "$SERVER_HOST" == "your-server.com" || "$SERVER_USER" == "user" ]]; then
    echo "[ERROR] Please fill in server details in deploy.config.sh"
    exit 1
fi

# ── SSH/SCP helper ───────────────────────────────────────────
# Usage: build_ssh_args; then use "${SSH_ARGS[@]}"
#        build_scp_args; then use "${SCP_ARGS[@]}"
build_ssh_args() {
    SSH_ARGS=(-p "$SERVER_PORT" -o "StrictHostKeyChecking=${SSH_HOST_KEY_POLICY:-accept-new}")
    if [[ -n "$SSH_KEY" ]]; then SSH_ARGS+=(-i "$SSH_KEY"); fi
}

build_scp_args() {
    SCP_ARGS=(-P "$SERVER_PORT" -o "StrictHostKeyChecking=${SSH_HOST_KEY_POLICY:-accept-new}")
    if [[ -n "$SSH_KEY" ]]; then SCP_ARGS+=(-i "$SSH_KEY"); fi
}

DEFAULT_NEVER_DEPLOY_PATTERNS=(
    ".git" ".git/*" "*/.git" "*/.git/*"
    ".env" ".env.*" "*/.env" "*/.env.*"
    "deploy.config.ps1" "deploy.config.sh"
    "instance" "instance/*" "*/instance" "*/instance/*"
    ".venv" ".venv/*" "*/.venv" "*/.venv/*"
    ".uv" ".uv/*" "*/.uv" "*/.uv/*"
    "venv" "venv/*" "*/venv" "*/venv/*"
    "env" "env/*" "*/env" "*/env/*"
    "__pycache__" "*/__pycache__" "*/__pycache__/*"
    ".pytest_cache" ".pytest_cache/*"
    "*.pyc" "*.pyo" "*.log"
)

DEFAULT_AUTO_DEPLOY_EXCLUDE_PATTERNS=(
    ".github" ".github/*" ".idea" ".idea/*"
    "tests" "tests/*" "docs" "docs/*"
    "README*" "LICENSE" "DEPLOYMENT.md" ".gitignore"
    ".env.example"
    "deploy.ps1" "deploy.sh"
    "deploy.config.ps1.example" "deploy.config.sh.example"
    "backend/data/program_titles.csv"
)

NEVER_DEPLOY_PATTERNS=("${DEFAULT_NEVER_DEPLOY_PATTERNS[@]}")
if declare -p EXTRA_NEVER_DEPLOY_PATTERNS >/dev/null 2>&1; then
    NEVER_DEPLOY_PATTERNS+=("${EXTRA_NEVER_DEPLOY_PATTERNS[@]}")
fi

AUTO_DEPLOY_EXCLUDE_PATTERNS=("${DEFAULT_AUTO_DEPLOY_EXCLUDE_PATTERNS[@]}")
if declare -p EXTRA_AUTO_DEPLOY_EXCLUDE_PATTERNS >/dev/null 2>&1; then
    AUTO_DEPLOY_EXCLUDE_PATTERNS+=("${EXTRA_AUTO_DEPLOY_EXCLUDE_PATTERNS[@]}")
fi

path_matches_patterns() {
    local normalized="${1#./}" pattern
    normalized="${normalized//\\//}"
    normalized="${normalized%/}"
    shift
    for pattern in "$@"; do
        if [[ $normalized == $pattern ]]; then return 0; fi
    done
    return 1
}

is_excluded_path() {
    path_matches_patterns "$1" "${NEVER_DEPLOY_PATTERNS[@]}"
}

is_auto_deploy_excluded_path() {
    is_excluded_path "$1" ||
        path_matches_patterns "$1" "${AUTO_DEPLOY_EXCLUDE_PATTERNS[@]}"
}

discover_repository_files() {
    command -v git >/dev/null 2>&1 || {
        echo "[ERROR] Git is required to discover deployable project files." >&2
        return 1
    }

    local path
    while IFS= read -r path; do
        [[ -f "$SCRIPT_DIR/$path" ]] || continue
        is_auto_deploy_excluded_path "$path" && continue
        printf '%s\n' "$path"
    done < <(git -C "$SCRIPT_DIR" ls-files --cached --others --exclude-standard)
}

command -v git >/dev/null 2>&1 || {
    echo "[ERROR] Git is required to discover deployable project files."
    exit 1
}
mapfile -t ALL_FILES < <(discover_repository_files)
if [[ ${#ALL_FILES[@]} -eq 0 ]]; then
    echo "[ERROR] No deployable files were discovered."
    exit 1
fi

BUILT_IN_PRESETS=(all backend frontend python dependencies csv static config)

preset_exists() {
    local name="$1" preset
    for preset in "${BUILT_IN_PRESETS[@]}"; do
        [[ "$name" == "$preset" ]] && return 0
    done
    declare -p CUSTOM_DEPLOY_PRESETS >/dev/null 2>&1 &&
        [[ -n "${CUSTOM_DEPLOY_PRESETS[$name]+defined}" ]]
}

get_preset_files() {
    local name="$1" file
    case "$name" in
        all) printf '%s\n' "${ALL_FILES[@]}" ;;
        backend)
            for file in "${ALL_FILES[@]}"; do
                [[ "$file" == backend/* || "$file" == "app.py" || "$file" == "run.py" || "$file" == "passenger_wsgi.py" ]] && printf '%s\n' "$file"
            done
            ;;
        frontend)
            for file in "${ALL_FILES[@]}"; do [[ "$file" == frontend/* ]] && printf '%s\n' "$file"; done
            ;;
        python)
            for file in "${ALL_FILES[@]}"; do [[ "$file" == *.py ]] && printf '%s\n' "$file"; done
            ;;
        dependencies) printf '%s\n' "pyproject.toml" "uv.lock" ;;
        csv) printf '%s\n' "backend/data/program_titles.csv" ;;
        static)
            for file in "${ALL_FILES[@]}"; do [[ "$file" == frontend/static/* ]] && printf '%s\n' "$file"; done
            ;;
        config) printf '%s\n' "backend/config.py" ;;
        *)
            local -a custom_files
            read -ra custom_files <<< "${CUSTOM_DEPLOY_PRESETS[$name]}"
            printf '%s\n' "${custom_files[@]}"
            ;;
    esac
}

selection_includes_dependencies() {
    local item normalized local_path
    for item in "$@"; do
        normalized="${item#./}"
        normalized="${normalized%/}"
        if [[ "$normalized" == "pyproject.toml" || "$normalized" == "uv.lock" ]]; then
            return 0
        fi

        local_path="$SCRIPT_DIR/$item"
        if [[ -d "$local_path" && ( -f "$local_path/pyproject.toml" || -f "$local_path/uv.lock" ) ]]; then
            return 0
        fi
    done

    return 1
}

# Finds exact paths first, then partial filename matches for interactive custom deploys.
find_project_file() {
    local term="$1"
    if [[ -e "$SCRIPT_DIR/$term" ]] && ! is_excluded_path "$term"; then
        printf '%s\n' "$term"
        return
    fi

    local found=false path relative_path
    while IFS= read -r -d '' path; do
        relative_path="${path#"$SCRIPT_DIR/"}"
        printf '%s\n' "$relative_path"
        found=true
    done < <(find "$SCRIPT_DIR" \
        \( -type d \( -name .git -o -name .venv -o -name .uv -o -name __pycache__ \) -prune \) -o \
        -type f -iname "*$term*" -print0)

    if [[ "$found" == false ]]; then
        echo "  [X] File not found: $term" >&2
    fi
}

# ── Detect changed files ─────────────────────────────────────
# Compares MD5 hashes of all automatically discovered deployable files.
# Prints files that are new or have changed content.
get_changed_files() {
    echo "" >&2
    echo "Checking for changes against server..." >&2

    local remote_files_str="" quoted_file quoted_remote_dir file
    for file in "${ALL_FILES[@]}"; do
        printf -v quoted_file '%q' "$file"
        remote_files_str+=" $quoted_file"
    done
    printf -v quoted_remote_dir '%q' "$REMOTE_APP_DIR"

    build_ssh_args

    # Fetch all remote hashes in a single SSH call.
    # We cd into the remote dir first so md5sum outputs relative paths cleanly.
    local remote_output
    remote_output="$(ssh "${SSH_ARGS[@]}" "$SERVER_USER@$SERVER_HOST" \
        "cd -- $quoted_remote_dir && md5sum -- $remote_files_str 2>/dev/null || true")"

    # Build associative array: relative_path -> hash
    declare -A remote_hashes
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local hash rel_path
        # Output format: HASH  filename
        hash="${line%% *}"
        rel_path="${line#*  }"
        # Clean up ./ prefix if present (md5sum sometimes adds it)
        rel_path="${rel_path#./}"

        if [[ -n "$hash" && -n "$rel_path" ]]; then
            remote_hashes["$rel_path"]="$hash"
        fi
    done <<< "$remote_output"

    # Compare with local hashes
    local -a changed=()
    for file in "${ALL_FILES[@]}"; do
        local local_path="$SCRIPT_DIR/$file"
        [[ ! -f "$local_path" ]] && continue

        local local_hash
        local_hash="$(md5sum "$local_path" | awk '{print $1}')"
        local remote_hash="${remote_hashes[$file]:-}"

        if [[ -z "$remote_hash" ]]; then
            printf "  [NEW]     %s\n" "$file" >&2
            changed+=("$file")
        elif [[ "$local_hash" != "$remote_hash" ]]; then
            printf "  [CHANGED] %s\n" "$file" >&2
            changed+=("$file")
        else
            printf "  [OK]      %s\n" "$file" >&2
        fi
    done

    # Output results to stdout for the caller to capture.
    if [[ ${#changed[@]} -gt 0 ]]; then
        printf '%s\n' "${changed[@]}"
    fi
}

# ── Function: upload a file or directory ────────────────────
send_item() {
    local item="$1"
    local local_path="$SCRIPT_DIR/$item"

    if is_excluded_path "$item"; then
        echo "  [SKIP] Excluded path: $item"
        return
    fi

    if [[ ! -e "$local_path" ]]; then
        echo "  [SKIP] Not found: $item"
        return
    fi

    if [[ -d "$local_path" ]]; then
        # Upload directory contents individually so excluded directories are never passed to SCP.
        local child relative_path
        while IFS= read -r -d '' child; do
            relative_path="${child#"$SCRIPT_DIR/"}"
            send_item "$relative_path"
        done < <(find "$local_path" \
            \( -type d \( -name .venv -o -name .uv -o -name __pycache__ \) -prune \) -o \
            -type f -print0)
        return
    fi

    build_ssh_args
    build_scp_args

    printf "  -> %s" "$item"

    # Ensure the remote directory exists before uploading the file.
    local remote_dir
    remote_dir="$REMOTE_APP_DIR/$(dirname "$item")"
    ssh "${SSH_ARGS[@]}" "$SERVER_USER@$SERVER_HOST" "mkdir -p ${remote_dir@Q}" 2>/dev/null || true
    if scp "${SCP_ARGS[@]}" "$local_path" "$SERVER_USER@$SERVER_HOST:$REMOTE_APP_DIR/$item" 2>&1; then
        echo "  [OK]"
    else
        echo "  [ERROR]"
        return 1
    fi
}

# ── Interactive menu ─────────────────────────────────────────
show_menu() {
    {
        echo ""
        echo "=================================================="
        echo "  $APP_NAME - Deploy to server"
        echo "  $SERVER_USER@$SERVER_HOST -> $REMOTE_APP_DIR"
        echo "=================================================="
        echo ""
        echo "  Select what to deploy:"
        echo ""
        echo "  [0] changed   - only files changed vs server (DEFAULT)"
        echo "  [1] all       - all deployable Git files (automatic)"
        echo "  [2] backend   - app.py, run.py, backend/"
        echo "  [3] frontend  - frontend/"
        echo "  [4] python    - .py files only"
        echo "  [5] csv       - backend/data/program_titles.csv"
        echo "  [6] static    - frontend/static/ (CSS, JS, img)"
        echo "  [7] config    - backend/config.py"
        echo "  [8] dependencies - pyproject.toml + uv.lock (runs uv sync)"
        echo "  [9] custom    - enter paths manually"
        echo ""
        echo "  [Q] Quit"
        echo ""
    } >&2
    read -rp "Choice [0]: " choice
    choice="${choice:-0}"

    case "${choice^^}" in
        0) echo "changed" ;;
        1) echo "all" ;;
        2) echo "backend" ;;
        3) echo "frontend" ;;
        4) echo "python" ;;
        5) echo "csv" ;;
        6) echo "static" ;;
        7) echo "config" ;;
        8) echo "dependencies" ;;
        9) echo "custom" ;;
        Q) exit 0 ;;
        *)
            echo "Unknown option." >&2
            show_menu
            ;;
    esac
}

# ── Parse arguments ──────────────────────────────────────────
PRESET=""
FILES_ARG=""
NO_RESTART=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --preset)     PRESET="$2";    shift 2 ;;
        --files)      FILES_ARG="$2"; shift 2 ;;
        --no-restart) NO_RESTART=true; shift ;;
        --dry-run)    DRY_RUN=true; shift ;;
        *) echo "[ERROR] Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Main logic ───────────────────────────────────────────────
echo ""

items_to_send=()

if [[ -n "$FILES_ARG" ]]; then
    # Mode: --files "a.py,b.py"
    IFS=',' read -ra items_to_send <<< "$FILES_ARG"
    selected_preset="custom"
elif [[ -n "$PRESET" ]]; then
    # Mode: --preset <name>
    if [[ "$PRESET" == "changed" ]]; then
        mapfile -t items_to_send < <(get_changed_files)
        selected_preset="changed"
    elif ! preset_exists "$PRESET"; then
        echo "[ERROR] Unknown preset: $PRESET"
        echo "Available: changed, ${BUILT_IN_PRESETS[*]}"
        exit 1
    else
        mapfile -t items_to_send < <(get_preset_files "$PRESET")
        selected_preset="$PRESET"
    fi
else
    # Interactive mode
    selected_preset="$(show_menu)"

    if [[ "$selected_preset" == "changed" ]]; then
        mapfile -t items_to_send < <(get_changed_files)
    elif [[ "$selected_preset" == "custom" ]]; then
        echo ""
        echo "Enter filenames to search (e.g. 'schedule', 'app.py'):"
        read -rp "Files: " user_input

        IFS=',' read -ra raw_inputs <<< "$user_input"
        items_to_send=()

        # We use a temporary associative array to prevent duplicates
        declare -A unique_files

        for term in "${raw_inputs[@]}"; do
            # Trim whitespace
            term="${term// /}"
            [[ -z "$term" ]] && continue

            # Call find_project_file (which may return multiple lines)
            while IFS= read -r found_path; do
                [[ -n "$found_path" ]] && unique_files["$found_path"]=1
            done < <(find_project_file "$term")
        done

        # Convert keys back to array
        items_to_send=("${!unique_files[@]}")
    else
        mapfile -t items_to_send < <(get_preset_files "$selected_preset")
    fi
fi

# Remove duplicates and enforce non-bypassable protection before showing the summary.
declare -A unique_selected_items=()
filtered_items=()
for item in "${items_to_send[@]}"; do
    item="${item#./}"
    item="${item//\\//}"
    if is_excluded_path "$item"; then
        echo "  [SKIP] Protected path: $item"
        continue
    fi
    if [[ -z "${unique_selected_items[$item]+defined}" ]]; then
        unique_selected_items["$item"]=1
        filtered_items+=("$item")
    fi
done
items_to_send=("${filtered_items[@]}")

# Nothing to send?
if [[ ${#items_to_send[@]} -eq 0 ]]; then
    echo ""
    echo "No files to deploy - everything is up to date!"
    exit 0
fi

# Summary before sending
echo ""
echo "Target: $SERVER_USER@$SERVER_HOST -> $REMOTE_APP_DIR"
echo "Files to send (${#items_to_send[@]}):"
for item in "${items_to_send[@]}"; do
    echo "  - $item"
done
echo ""

if [[ "$DRY_RUN" == true ]]; then
    echo "Dry run complete - no files were uploaded and the application was not restarted."
    exit 0
fi

read -rp "Continue? [Y/n] " confirm
confirm="${confirm:-Y}"
if [[ "${confirm^^}" != "Y" ]]; then
    echo "Cancelled."
    exit 0
fi

# Upload
echo ""
echo "Uploading files..."
for item in "${items_to_send[@]}"; do
    send_item "$item"
done

# Always synchronize and validate the project environment before restart.
# uv sync is exact and idempotent, and catches stale/broken binary extensions.
echo ""
echo "Synchronizing and validating the production environment..."
build_ssh_args
printf -v quoted_remote_dir '%q' "$REMOTE_APP_DIR"
preflight_command="cd -- $quoted_remote_dir && \
uv sync --locked --no-dev && \
EXPECTED_PYTHON=\$(tr -d '[:space:]' < .python-version) && \
ACTUAL_PYTHON=\$(.venv/bin/python -c 'import sys; print(sys.version_info.major,sys.version_info.minor,sep=chr(46))') && \
test \"\$ACTUAL_PYTHON\" = \"\$EXPECTED_PYTHON\" && \
.venv/bin/python -c 'from lxml import etree; from app import create_app; create_app()'"
if ssh "${SSH_ARGS[@]}" "$SERVER_USER@$SERVER_HOST" "$preflight_command"; then
    echo "Production environment validated successfully."
else
    echo "Environment synchronization or startup preflight failed; application was not restarted."
    exit 1
fi

# Trigger a Phusion Passenger restart.
if [[ "$NO_RESTART" == false && -n "$RESTART_COMMAND" ]]; then
    echo ""
    echo "Restarting application on server..."
    build_ssh_args
    if ssh "${SSH_ARGS[@]}" "$SERVER_USER@$SERVER_HOST" "bash -c ${RESTART_COMMAND@Q}"; then
        echo "Application restarted successfully."
    else
        echo "Restart failed - check manually."
    fi
elif [[ "$NO_RESTART" == true ]]; then
    echo ""
    echo "Restart skipped (--no-restart)."
fi

echo ""
echo "Deploy complete!"
echo ""
