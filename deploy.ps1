# ============================================================
#  deploy.ps1 - Deployment script for GrafikPlusWeb
#
#  Usage:
#    .\deploy.ps1                      -> interactive menu (default: changed files)
#    .\deploy.ps1 -Preset changed      -> only files changed vs server (default)
#    .\deploy.ps1 -Preset all          -> all files
#    .\deploy.ps1 -Preset backend      -> backend files only
#    .\deploy.ps1 -Files "app.py","requirements.txt"  -> specific files
#    .\deploy.ps1 -Preset backend -NoRestart           -> skip restart
# ============================================================

param(
    [string]$Preset    = "",
    [string[]]$Files   = @(),
    [switch]$NoRestart
)

# ── Load configuration ──────────────────────────────────────
$ConfigFile = Join-Path $PSScriptRoot "deploy.config.ps1"
if (-not (Test-Path $ConfigFile)) {
    Write-Host "[ERROR] Missing deploy.config.ps1 - copy deploy.config.ps1.example and fill in server details." -ForegroundColor Red
    exit 1
}
. $ConfigFile

# ── Validate configuration ──────────────────────────────────
if ($SERVER_HOST -eq "your-server.com" -or $SERVER_USER -eq "user") {
    Write-Host "[ERROR] Please fill in server details in deploy.config.ps1" -ForegroundColor Red
    exit 1
}

# ── Predefined file sets ────────────────────────────────────
# $ALL_FILES and $PRESETS are defined in deploy.config.ps1

# ── SSH helper args ──────────────────────────────────────────
function Get-SshArgs {
    $sshParams = @("-p", $SERVER_PORT, "-o", "StrictHostKeyChecking=no")
    if ($SSH_KEY -ne "") { $sshParams += @("-i", $SSH_KEY) }
    return $sshParams
}

function Get-ScpArgs {
    $scpParams = @("-P", $SERVER_PORT, "-o", "StrictHostKeyChecking=no")
    if ($SSH_KEY -ne "") { $scpParams += @("-i", $SSH_KEY) }
    return $scpParams
}

# ── Smart File Search ────────────────────────────────────────
function Find-ProjectFile {
    param([string]$SearchTerm)

    # 1. Check if it is already a valid exact path
    if (Test-Path (Join-Path $PSScriptRoot $SearchTerm)) {
        return $SearchTerm
    }

    # 2. Search recursively for files with that name
    $filter = "*$SearchTerm*"
    $foundFiles = Get-ChildItem -Path $PSScriptRoot -Recurse -Filter $filter -File -ErrorAction SilentlyContinue |
               Where-Object { $_.FullName -notmatch "\\(__pycache__|\.git|venv|env)\\" }

    if ($foundFiles.Count -eq 1) {
        # Found exactly one match
        $relativePath = $foundFiles[0].FullName.Substring($PSScriptRoot.Length + 1).Replace('\', '/')
        Write-Host "  -> Found: $relativePath" -ForegroundColor Cyan
        return $relativePath
    } elseif ($foundFiles.Count -gt 1) {
        # Found multiple matches - ask user
        Write-Host "  [?] Multiple files found for '$SearchTerm':" -ForegroundColor Yellow
        for ($i = 0; $i -lt $foundFiles.Count; $i++) {
            $rel = $foundFiles[$i].FullName.Substring($PSScriptRoot.Length + 1).Replace('\', '/')
            Write-Host "      [$($i+1)] $rel" -ForegroundColor White
        }
        Write-Host "      [A] All of them" -ForegroundColor White
        
        $selection = Read-Host "      Select (e.g. '1', '1,3', 'A')"

        if ($selection.ToUpper() -eq "A") {
             return $foundFiles | ForEach-Object { $_.FullName.Substring($PSScriptRoot.Length + 1).Replace('\', '/') }
        }

        # Split by comma or space
        $indices = $selection -split '[, ]' | Where-Object { $_ -ne "" }
        $selectedPaths = @()

        foreach ($idx in $indices) {
            if ($idx -match "^[0-9]+$" -and [int]$idx -le $foundFiles.Count -and [int]$idx -gt 0) {
                 $selectedPaths += $foundFiles[[int]$idx - 1].FullName.Substring($PSScriptRoot.Length + 1).Replace('\', '/')
            }
        }

        if ($selectedPaths.Count -gt 0) {
            return $selectedPaths
        } else {
            Write-Host "      Invalid selection, skipping." -ForegroundColor Red
        }
    } else {
        Write-Host "  [X] File not found: $SearchTerm" -ForegroundColor Red
    }
    return $null
}

# ── Detect changed files ─────────────────────────────────────
# Compares MD5 hashes of all files in $ALL_FILES between local and remote.
# Returns list of files that are new or have changed content.
function Get-ChangedFiles {
    Write-Host ""
    Write-Host "Checking for changes against server..." -ForegroundColor DarkGray

    # Construct remote file list for md5sum
    # Use relative paths to avoid massive command lines if possible, but here we use absolute for safety
    # $remoteCheckList = ($ALL_FILES | ForEach-Object { "${REMOTE_APP_DIR}/$_" }) -join " "

    # Improved Bash command:
    # 1. cd to app dir
    # 2. run md5sum on each file
    # 3. output format: HASH  FILENAME
    $remoteCmd = "cd ${REMOTE_APP_DIR} && md5sum $ALL_FILES 2>/dev/null"
    
    $SshArgs = Get-SshArgs
    $remoteOutput = ssh @SshArgs "$SERVER_USER@$SERVER_HOST" $remoteCmd

    # Parse remote hashes into a hashtable { "relative/path" => "md5hash" }
    $remoteHashes = @{}
    if ($remoteOutput) {
        $remoteOutput -split "`n" | ForEach-Object {
            $line = $_.Trim()
            if ($line -match '^([0-9a-f]{32})\s+(.+)$') {
                $hash = $Matches[1]
                $path = $Matches[2].Trim()
                # Remove ./ prefix if present
                if ($path.StartsWith("./")) { $path = $path.Substring(2) }
                $remoteHashes[$path] = $hash
            }
        }
    }

    # Compare with local hashes
    $changed = @()
    foreach ($file in $ALL_FILES) {
        $localPath = Join-Path $PSScriptRoot $file
        if (-not (Test-Path $localPath)) { continue }

        $localHash = (Get-FileHash -Algorithm MD5 -Path $localPath).Hash.ToLower()
        
        # Normalize file path keys (replace \ with /)
        $lookupKey = $file -replace '\\', '/'
        
        $remoteHash = $remoteHashes[$lookupKey]

        if (-not $remoteHashes.ContainsKey($lookupKey)) {
            Write-Host "  [NEW]     $file" -ForegroundColor Green
            $changed += $file
        } elseif ($localHash -ne $remoteHash) {
            Write-Host "  [CHANGED] $file" -ForegroundColor Yellow
            $changed += $file
        } else {
            Write-Host "  [OK]      $file" -ForegroundColor DarkGray
        }
    }
    
    if ($changed.Count -eq 0) {
        Write-Host "  All files are up to date." -ForegroundColor Green
    }
    
    return $changed
}

# ── Function: upload a file or directory ────────────────────
function Send-Item {
    param([string]$LocalItem)

    $LocalPath = Join-Path $PSScriptRoot $LocalItem

    if (-not (Test-Path $LocalPath)) {
        Write-Host "  [SKIP] Not found: $LocalItem" -ForegroundColor Yellow
        return
    }

    $ScpArgs = Get-ScpArgs

    if ((Get-Item $LocalPath).PSIsContainer) {
        # Directory - recursive; scp into parent dir on remote
        $LocalPath = $LocalPath.TrimEnd('\').TrimEnd('/')
        $RemoteDir = "$SERVER_USER@${SERVER_HOST}:$(($REMOTE_APP_DIR + '/' + $LocalItem).TrimEnd('/') | Split-Path -Parent)"
        $ScpArgs += @("-r", $LocalPath, $RemoteDir)
    } else {
        # File - ensure remote directory exists first
        $RemoteDir = ($REMOTE_APP_DIR + "/" + $LocalItem) | Split-Path -Parent
        $RemoteDir = $RemoteDir -replace '\\', '/'
        $SshArgs = Get-SshArgs
        $SshArgs += @("$SERVER_USER@$SERVER_HOST", "mkdir -p '$RemoteDir'")
        ssh @SshArgs 2>$null
        $ScpArgs += @($LocalPath, "$SERVER_USER@${SERVER_HOST}:$REMOTE_APP_DIR/$LocalItem")
    }

    Write-Host "  -> $LocalItem" -ForegroundColor Cyan -NoNewline

    $result = scp @ScpArgs 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK]" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR]" -ForegroundColor Red
        Write-Host "     $result" -ForegroundColor DarkRed
    }
}

# ── Interactive menu ─────────────────────────────────────────
function Show-Menu {
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Magenta
    Write-Host "  $APP_NAME - Deploy to server" -ForegroundColor Magenta
    Write-Host "  $SERVER_USER@$SERVER_HOST -> $REMOTE_APP_DIR" -ForegroundColor DarkGray
    Write-Host "==================================================" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "  Select what to deploy:" -ForegroundColor White
    Write-Host ""
    Write-Host "  [0] changed   - only files changed vs server (DEFAULT)" -ForegroundColor Cyan
    Write-Host "  [1] all       - everything (backend + frontend)" -ForegroundColor Yellow
    Write-Host "  [2] backend   - app.py, run.py, backend/" -ForegroundColor Yellow
    Write-Host "  [3] frontend  - frontend/" -ForegroundColor Yellow
    Write-Host "  [4] python    - .py files only" -ForegroundColor Yellow
    Write-Host "  [5] csv       - backend/data/program_titles.csv" -ForegroundColor Yellow
    Write-Host "  [6] static    - frontend/static/ (CSS, JS, img)" -ForegroundColor Yellow
    Write-Host "  [7] config    - backend/config.py" -ForegroundColor Yellow
    Write-Host "  [8] custom    - enter paths manually (SMART SEARCH)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  [Q] Quit" -ForegroundColor DarkGray
    Write-Host ""

    $choice = Read-Host "Choice [0]"
    if ($choice -eq "") { $choice = "0" }

    switch ($choice.ToUpper()) {
        "0" { return "changed" }
        "1" { return "all" }
        "2" { return "backend" }
        "3" { return "frontend" }
        "4" { return "python" }
        "5" { return "csv" }
        "6" { return "static" }
        "7" { return "config" }
        "8" { return "custom" }
        "Q" { exit 0 }
        default {
            Write-Host "Unknown option." -ForegroundColor Red
            return Show-Menu
        }
    }
}

# ── Main logic ───────────────────────────────────────────────
Write-Host ""

$itemsToSend = @()

if ($Files.Count -gt 0) {
    # Mode: -Files "a.py","b.py"
    $itemsToSend = $Files
    $selectedPreset = "custom"
} elseif ($Preset -ne "") {
    # Mode: -Preset <name>
    if ($Preset -eq "changed") {
        $itemsToSend = @(Get-ChangedFiles)
        $selectedPreset = "changed"
    } elseif (-not $PRESETS.ContainsKey($Preset)) {
        Write-Host "[ERROR] Unknown preset: $Preset" -ForegroundColor Red
        Write-Host "Available: changed, $($PRESETS.Keys -join ', ')" -ForegroundColor Yellow
        exit 1
    } else {
        $itemsToSend = $PRESETS[$Preset]
        $selectedPreset = $Preset
    }
} else {
    # Interactive mode
    $selectedPreset = Show-Menu

    if ($selectedPreset -eq "changed") {
        $itemsToSend = @(Get-ChangedFiles)
        
        # If no changes explicitly found, ask user if they want to force anything
        if ($itemsToSend.Count -eq 0) {
             Write-Host ""
             $force = Read-Host "  No changes detected. Force deploy specific files? [y/N]"
             if ($force.ToUpper() -eq "Y") {
                 $selectedPreset = "custom" # Fall through to custom logic below
             } else {
                 Write-Host "Exiting." -ForegroundColor Gray
                 exit 0
             }
        }
    } 
    
    if ($selectedPreset -eq "custom") {
        Write-Host ""
        Write-Host "Enter filenames to search (e.g. 'schedule', 'app.py'):" -ForegroundColor White
        $userInput = Read-Host "Files"
        
        $rawInputs = $userInput -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
        $resolvedFiles = @()
        
        foreach ($inputTerm in $rawInputs) {
             $found = Find-ProjectFile $inputTerm
             if ($found) {
                 if ($found -is [array]) {
                     $resolvedFiles += $found
                 } else {
                     $resolvedFiles += $found
                 }
             }
        }
        
        # Remove duplicates
        $itemsToSend = $resolvedFiles | Select-Object -Unique
    } elseif ($selectedPreset -ne "changed") {
        $itemsToSend = $PRESETS[$selectedPreset]
    }
}

# Nothing to send?
if ($itemsToSend.Count -eq 0) {
    Write-Host ""
    Write-Host "No files to deploy!" -ForegroundColor Yellow
    exit 0
}

# Summary before sending
Write-Host ""
Write-Host "Target: $SERVER_USER@$SERVER_HOST -> $REMOTE_APP_DIR" -ForegroundColor DarkGray
Write-Host "Files to send ($($itemsToSend.Count)):" -ForegroundColor White
$itemsToSend | ForEach-Object { Write-Host "  - $_" -ForegroundColor DarkCyan }
Write-Host ""

$confirm = Read-Host "Continue? [Y/n]"
if ($confirm -ne "" -and $confirm.ToUpper() -ne "Y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

# Upload
Write-Host ""
Write-Host "Uploading files..." -ForegroundColor White
foreach ($item in $itemsToSend) {
    Send-Item -LocalItem ($item -replace '\\', '/')
}

# Restart service
if (-not $NoRestart -and $RESTART_COMMAND -ne "") {
    Write-Host ""
    Write-Host "Restarting application on server..." -ForegroundColor White

    $SshArgs = Get-SshArgs
    $SshArgs += @("$SERVER_USER@$SERVER_HOST", $RESTART_COMMAND)
    ssh @SshArgs
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Application restarted successfully." -ForegroundColor Green
    } else {
        Write-Host "Restart failed - check manually." -ForegroundColor Red
    }
} elseif ($NoRestart) {
    Write-Host ""
    Write-Host "Restart skipped (-NoRestart)." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Deploy complete!" -ForegroundColor Green
Write-Host ""

