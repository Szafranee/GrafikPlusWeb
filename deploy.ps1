# ============================================================
#  deploy.ps1 - Deployment script for GrafikPlusWeb
#
#  Usage:
#    .\deploy.ps1                      -> interactive menu (default: changed files)
#    .\deploy.ps1 -Preset changed      -> only files changed vs server (default)
#    .\deploy.ps1 -Preset all          -> all files
#    .\deploy.ps1 -Preset backend      -> backend files only
#    .\deploy.ps1 -Files "app.py","pyproject.toml"  -> specific files
#    .\deploy.ps1 -Preset dependencies -> dependencies + remote uv sync
#    .\deploy.ps1 -Preset backend -NoRestart           -> skip restart
#    .\deploy.ps1 -Preset all -DryRun                   -> preview without upload
# ============================================================

param(
    [string]$Preset    = "",
    [string[]]$Files   = @(),
    [switch]$NoRestart,
    [switch]$DryRun
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

# ── SSH helper args ──────────────────────────────────────────
function Get-SshArgs {
    $hostKeyPolicy = if ($SSH_HOST_KEY_POLICY) { $SSH_HOST_KEY_POLICY } else { "accept-new" }
    $sshParams = @("-p", $SERVER_PORT, "-o", "StrictHostKeyChecking=$hostKeyPolicy")
    if ($SSH_KEY -ne "") { $sshParams += @("-i", $SSH_KEY) }
    return $sshParams
}

function Get-ScpArgs {
    $hostKeyPolicy = if ($SSH_HOST_KEY_POLICY) { $SSH_HOST_KEY_POLICY } else { "accept-new" }
    $scpParams = @("-P", $SERVER_PORT, "-o", "StrictHostKeyChecking=$hostKeyPolicy")
    if ($SSH_KEY -ne "") { $scpParams += @("-i", $SSH_KEY) }
    return $scpParams
}

function Test-PathMatchesAnyPattern {
    param(
        [string]$Path,
        [string[]]$Patterns
    )

    $normalizedPath = (($Path -replace '\\', '/') -replace '^\./', '').TrimEnd('/')
    foreach ($pattern in $Patterns) {
        if ($normalizedPath -like $pattern) { return $true }
    }
    return $false
}

$DefaultNeverDeployPatterns = @(
    ".git", ".git/*", "*/.git", "*/.git/*",
    ".env", ".env.*", "*/.env", "*/.env.*",
    "deploy.config.ps1", "deploy.config.sh",
    "instance", "instance/*", "*/instance", "*/instance/*",
    ".venv", ".venv/*", "*/.venv", "*/.venv/*",
    ".uv", ".uv/*", "*/.uv", "*/.uv/*",
    "venv", "venv/*", "*/venv", "*/venv/*",
    "env", "env/*", "*/env", "*/env/*",
    "__pycache__", "*/__pycache__", "*/__pycache__/*",
    ".pytest_cache", ".pytest_cache/*",
    "*.pyc", "*.pyo", "*.log"
)

$DefaultAutoDeployExcludePatterns = @(
    ".github", ".github/*", ".idea", ".idea/*",
    "tests", "tests/*", "docs", "docs/*",
    "README*", "LICENSE", "DEPLOYMENT.md", ".gitignore",
    ".env.example",
    "deploy.ps1", "deploy.sh",
    "deploy.config.ps1.example", "deploy.config.sh.example",
    "backend/data/program_titles.csv"
)

$NeverDeployPatterns = @($DefaultNeverDeployPatterns)
if (Get-Variable -Name EXTRA_NEVER_DEPLOY_PATTERNS -ErrorAction SilentlyContinue) {
    $NeverDeployPatterns += @($EXTRA_NEVER_DEPLOY_PATTERNS)
}

$AutoDeployExcludePatterns = @($DefaultAutoDeployExcludePatterns)
if (Get-Variable -Name EXTRA_AUTO_DEPLOY_EXCLUDE_PATTERNS -ErrorAction SilentlyContinue) {
    $AutoDeployExcludePatterns += @($EXTRA_AUTO_DEPLOY_EXCLUDE_PATTERNS)
}

function Test-ExcludedPath {
    param([string]$Path)

    return Test-PathMatchesAnyPattern -Path $Path -Patterns $NeverDeployPatterns
}

function Test-AutoDeployExcludedPath {
    param([string]$Path)

    return (Test-ExcludedPath $Path) -or
        (Test-PathMatchesAnyPattern -Path $Path -Patterns $AutoDeployExcludePatterns)
}

function Get-RepositoryFiles {
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCommand) {
        throw "Git is required to discover deployable project files."
    }

    $gitFiles = & git -C $PSScriptRoot ls-files --cached --others --exclude-standard
    if ($LASTEXITCODE -ne 0) {
        throw "Could not list repository files with git ls-files."
    }

    return @(
        $gitFiles |
            ForEach-Object { $_ -replace '\\', '/' } |
            Where-Object {
                $_ -and
                (Test-Path -LiteralPath (Join-Path $PSScriptRoot $_) -PathType Leaf) -and
                -not (Test-AutoDeployExcludedPath $_)
            } |
            Sort-Object -Unique
    )
}

function Get-PresetFiles {
    param([string]$Name)

    switch ($Name) {
        "all" { return @($ALL_FILES) }
        "backend" {
            return @($ALL_FILES | Where-Object {
                $_ -like "backend/*" -or $_ -in @("app.py", "run.py", "passenger_wsgi.py")
            })
        }
        "frontend" { return @($ALL_FILES | Where-Object { $_ -like "frontend/*" }) }
        "python" { return @($ALL_FILES | Where-Object { $_ -like "*.py" }) }
        "dependencies" { return @("pyproject.toml", "uv.lock") }
        "csv" { return @("backend/data/program_titles.csv") }
        "static" { return @($ALL_FILES | Where-Object { $_ -like "frontend/static/*" }) }
        "config" { return @("backend/config.py") }
        default { return $null }
    }
}

$ALL_FILES = @(Get-RepositoryFiles)
if ($ALL_FILES.Count -eq 0) {
    throw "No deployable files were discovered."
}
$BuiltInPresetNames = @(
    "all", "backend", "frontend", "python",
    "dependencies", "csv", "static", "config"
)

function Test-PresetExists {
    param([string]$Name)

    if ($Name -in $BuiltInPresetNames) { return $true }
    return (
        (Get-Variable -Name CUSTOM_DEPLOY_PRESETS -ErrorAction SilentlyContinue) -and
        $CUSTOM_DEPLOY_PRESETS.ContainsKey($Name)
    )
}

function Resolve-PresetFiles {
    param([string]$Name)

    if ($Name -in $BuiltInPresetNames) { return @(Get-PresetFiles $Name) }
    return @($CUSTOM_DEPLOY_PRESETS[$Name])
}

function ConvertTo-ShellLiteral {
    param([string]$Value)

    $escaped = $Value.Replace("'", "'`"'`"'")
    return "'$escaped'"
}

function Test-DependencyFilesIncluded {
    param([string[]]$Items)

    foreach ($item in $Items) {
        $normalizedItem = ($item -replace '\\', '/') -replace '^\./', ''
        $normalizedItem = $normalizedItem.TrimEnd('/')

        if ($normalizedItem -in @('pyproject.toml', 'uv.lock')) {
            return $true
        }

        $localPath = Join-Path $PSScriptRoot $item
        if ((Test-Path -LiteralPath $localPath -PathType Container) -and
            ((Test-Path -LiteralPath (Join-Path $localPath 'pyproject.toml') -PathType Leaf) -or
             (Test-Path -LiteralPath (Join-Path $localPath 'uv.lock') -PathType Leaf))) {
            return $true
        }
    }

    return $false
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
               Where-Object { $_.FullName -notmatch "\\(__pycache__|\.git|\.venv|\.uv|venv|env)\\" }

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
# Compares MD5 hashes of all automatically discovered deployable files.
# Returns list of files that are new or have changed content.
function Get-ChangedFiles {
    Write-Host ""
    Write-Host "Checking for changes against server..." -ForegroundColor DarkGray

    $remoteDirectory = ConvertTo-ShellLiteral $REMOTE_APP_DIR
    $remoteFiles = ($ALL_FILES | ForEach-Object { ConvertTo-ShellLiteral $_ }) -join " "
    $remoteCmd = "cd -- $remoteDirectory && md5sum -- $remoteFiles 2>/dev/null || true"
    
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

    $LocalItem = $LocalItem -replace '\\', '/'
    if (Test-ExcludedPath $LocalItem) {
        Write-Host "  [SKIP] Excluded path: $LocalItem" -ForegroundColor DarkGray
        return
    }

    $LocalPath = Join-Path $PSScriptRoot $LocalItem

    if (-not (Test-Path $LocalPath)) {
        Write-Host "  [SKIP] Not found: $LocalItem" -ForegroundColor Yellow
        return
    }

    if ((Get-Item $LocalPath).PSIsContainer) {
        # Upload directory contents individually so excluded directories are never passed to SCP.
        Get-ChildItem -LiteralPath $LocalPath -Recurse -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                $relativePath = $_.FullName.Substring($PSScriptRoot.Length + 1) -replace '\\', '/'
                if (-not (Test-ExcludedPath $relativePath)) {
                    Send-Item -LocalItem $relativePath
                }
            }
        return
    }

    # Ensure the remote directory exists before uploading the file.
    $RemoteDir = ($REMOTE_APP_DIR + "/" + $LocalItem) | Split-Path -Parent
    $RemoteDir = $RemoteDir -replace '\\', '/'
    $SshArgs = Get-SshArgs
    $SshArgs += @("$SERVER_USER@$SERVER_HOST", "mkdir -p '$RemoteDir'")
    ssh @SshArgs 2>$null

    $ScpArgs = Get-ScpArgs
    $ScpArgs += @($LocalPath, "$SERVER_USER@${SERVER_HOST}:$REMOTE_APP_DIR/$LocalItem")

    Write-Host "  -> $LocalItem" -ForegroundColor Cyan -NoNewline

    $result = scp @ScpArgs 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK]" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR]" -ForegroundColor Red
        Write-Host "     $result" -ForegroundColor DarkRed
        $script:UploadFailed = $true
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
    Write-Host "  [1] all       - all deployable Git files (automatic)" -ForegroundColor Yellow
    Write-Host "  [2] backend   - app.py, run.py, backend/" -ForegroundColor Yellow
    Write-Host "  [3] frontend  - frontend/" -ForegroundColor Yellow
    Write-Host "  [4] python    - .py files only" -ForegroundColor Yellow
    Write-Host "  [5] csv       - backend/data/program_titles.csv" -ForegroundColor Yellow
    Write-Host "  [6] static    - frontend/static/ (CSS, JS, img)" -ForegroundColor Yellow
    Write-Host "  [7] config    - backend/config.py" -ForegroundColor Yellow
    Write-Host "  [8] dependencies - pyproject.toml + uv.lock (runs uv sync)" -ForegroundColor Yellow
    Write-Host "  [9] custom    - enter paths manually (SMART SEARCH)" -ForegroundColor Yellow
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
        "8" { return "dependencies" }
        "9" { return "custom" }
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
$script:UploadFailed = $false

if ($Files.Count -gt 0) {
    # Mode: -Files "a.py","b.py"
    $itemsToSend = $Files
    $selectedPreset = "custom"
} elseif ($Preset -ne "") {
    # Mode: -Preset <name>
    if ($Preset -eq "changed") {
        $itemsToSend = @(Get-ChangedFiles)
        $selectedPreset = "changed"
    } elseif (-not (Test-PresetExists $Preset)) {
        Write-Host "[ERROR] Unknown preset: $Preset" -ForegroundColor Red
        $availablePresets = @($BuiltInPresetNames)
        if (Get-Variable -Name CUSTOM_DEPLOY_PRESETS -ErrorAction SilentlyContinue) {
            $availablePresets += @($CUSTOM_DEPLOY_PRESETS.Keys)
        }
        Write-Host "Available: changed, $($availablePresets -join ', ')" -ForegroundColor Yellow
        exit 1
    } else {
        $itemsToSend = @(Resolve-PresetFiles $Preset)
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
        $itemsToSend = @(Resolve-PresetFiles $selectedPreset)
    }
}

# Nothing to send?
$itemsToSend = @(
    $itemsToSend |
        ForEach-Object { ($_ -replace '\\', '/') -replace '^\./', '' } |
        Where-Object {
            if (Test-ExcludedPath $_) {
                Write-Host "  [SKIP] Protected path: $_" -ForegroundColor DarkGray
                return $false
            }
            return $true
        } |
        Select-Object -Unique
)

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

if ($DryRun) {
    Write-Host "Dry run complete - no files were uploaded and the application was not restarted." -ForegroundColor Green
    exit 0
}

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

if ($script:UploadFailed) {
    Write-Host "Upload failed; dependency synchronization and restart were skipped." -ForegroundColor Red
    exit 1
}

# Always synchronize and validate the project environment before restart.
# uv sync is exact and idempotent, so a no-op deployment stays inexpensive,
# while a stale or ABI-incompatible .venv is repaired before Passenger sees it.
Write-Host ""
Write-Host "Synchronizing and validating the production environment..." -ForegroundColor White

$remoteDirectory = ConvertTo-ShellLiteral $REMOTE_APP_DIR
$SyncCommand = @"
cd -- $remoteDirectory &&
uv sync --locked --no-dev &&
EXPECTED_PYTHON=`$(tr -d '[:space:]' < .python-version) &&
ACTUAL_PYTHON=`$(.venv/bin/python -c 'import sys; print(sys.version_info.major,sys.version_info.minor,sep=chr(46))') &&
test "`$ACTUAL_PYTHON" = "`$EXPECTED_PYTHON" &&
.venv/bin/python -c 'from lxml import etree; from app import create_app; create_app()'
"@
$SshArgs = Get-SshArgs
$SshArgs += @("$SERVER_USER@$SERVER_HOST", $SyncCommand)
ssh @SshArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "Environment synchronization or startup preflight failed; application was not restarted." -ForegroundColor Red
    exit 1
}
Write-Host "Production environment validated successfully." -ForegroundColor Green

# Trigger a Phusion Passenger restart.
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

