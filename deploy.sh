#!/usr/bin/env bash
# ============================================================
#  deploy.sh - Deployment script for GrafikPlusWeb (Linux/macOS)
#
#  Usage:
#    ./deploy.sh                        -> interactive menu (default: changed files)
#    ./deploy.sh --preset changed       -> only files changed vs server (default)
#    ./deploy.sh --preset all           -> all files
#    ./deploy.sh --preset backend       -> backend files only
#    ./deploy.sh --files "app.py,requirements.txt"  -> specific files
#    ./deploy.sh --preset backend --no-restart      -> skip restart
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

# ── Tracked files and presets are defined in deploy.config.sh ──

# ── SSH/SCP helper ───────────────────────────────────────────
# Usage: build_ssh_args; then use "${SSH_ARGS[@]}"
#        build_scp_args; then use "${SCP_ARGS[@]}"
build_ssh_args() {
    SSH_ARGS=(-p "$SERVER_PORT" -o StrictHostKeyChecking=no)
    if [[ -n "$SSH_KEY" ]]; then SSH_ARGS+=(-i "$SSH_KEY"); fi
}

build_scp_args() {
    SCP_ARGS=(-P "$SERVER_PORT" -o StrictHostKeyChecking=no)
    if [[ -n "$SSH_KEY" ]]; then SCP_ARGS+=(-i "$SSH_KEY"); fi
}

# ── Detect changed files ─────────────────────────────────────
# Compares MD5 hashes of all files in ALL_FILES between local and remote.
# Prints files that are new or have changed content.
get_changed_files() {
    echo ""
    echo "Checking for changes against server..." >&2

    # Build remote file list as space-separated string
    local remote_files_str="${ALL_FILES[*]}"

    build_ssh_args

    # Fetch all remote hashes in a single SSH call.
    # We cd into the remote dir first so md5sum outputs relative paths cleanly.
    local remote_output
    remote_output="$(ssh "${SSH_ARGS[@]}" "$SERVER_USER@$SERVER_HOST" \
        "cd \"$REMOTE_APP_DIR\" && md5sum $remote_files_str 2>/dev/null || true")"

    # Build associative array: relative_path -> hash
    declare -A remote_hashes
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local hash rel_path
        # Output format: HASH  filename
        hash="${line%% *}"
        rel_path="${line##* }"
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

    # Output result to stdout (caller captures it)
    printf '%s\n' "${changed[@]}"
}

# ── Function: upload a file or directory ────────────────────
send_item() {
    local item="$1"
    local local_path="$SCRIPT_DIR/$item"

    if [[ ! -e "$local_path" ]]; then
        echo "  [SKIP] Not found: $item"
        return
    fi

    build_ssh_args
    build_scp_args

    printf "  -> %s" "$item"

    if [[ -d "$local_path" ]]; then
        # Directory - recursive; scp into parent directory on remote
        local remote_parent
        remote_parent="$REMOTE_APP_DIR/$(dirname "$item")"
        ssh "${SSH_ARGS[@]}" "$SERVER_USER@$SERVER_HOST" "mkdir -p ${remote_parent@Q}" 2>/dev/null || true
        if scp "${SCP_ARGS[@]}" -r "${local_path%/}" "$SERVER_USER@$SERVER_HOST:$remote_parent" 2>&1; then
            echo "  [OK]"
        else
            echo "  [ERROR]"
        fi
    else
        # File - ensure remote directory exists first
        local remote_dir
        remote_dir="$REMOTE_APP_DIR/$(dirname "$item")"
        ssh "${SSH_ARGS[@]}" "$SERVER_USER@$SERVER_HOST" "mkdir -p ${remote_dir@Q}" 2>/dev/null || true
        if scp "${SCP_ARGS[@]}" "$local_path" "$SERVER_USER@$SERVER_HOST:$REMOTE_APP_DIR/$item" 2>&1; then
            echo "  [OK]"
        else
            echo "  [ERROR]"
        fi
    fi
}

# ── Interactive menu ─────────────────────────────────────────
show_menu() {
    echo ""
    echo "=================================================="
    echo "  $APP_NAME - Deploy to server"
    echo "  $SERVER_USER@$SERVER_HOST -> $REMOTE_APP_DIR"
    echo "=================================================="
    echo ""
    echo "  Select what to deploy:"
    echo ""
    echo "  [0] changed   - only files changed vs server (DEFAULT)"
    echo "  [1] all       - everything (backend + frontend)"
    echo "  [2] backend   - app.py, run.py, backend/"
    echo "  [3] frontend  - frontend/"
    echo "  [4] python    - .py files only"
    echo "  [5] csv       - backend/data/program_titles.csv"
    echo "  [6] static    - frontend/static/ (CSS, JS, img)"
    echo "  [7] config    - backend/config.py"
    echo "  [8] custom    - enter paths manually"
    echo ""
    echo "  [Q] Quit"
    echo ""
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
        8) echo "custom" ;;
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

while [[ $# -gt 0 ]]; do
    case "$1" in
        --preset)     PRESET="$2";    shift 2 ;;
        --files)      FILES_ARG="$2"; shift 2 ;;
        --no-restart) NO_RESTART=true; shift ;;
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
    elif [[ -z "${PRESETS[$PRESET]+_}" ]]; then
        echo "[ERROR] Unknown preset: $PRESET"
        echo "Available: changed, ${!PRESETS[*]}"
        exit 1
    else
        read -ra items_to_send <<< "${PRESETS[$PRESET]}"
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
        read -ra items_to_send <<< "${PRESETS[$selected_preset]}"
    fi
fi

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

# Restart service
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

