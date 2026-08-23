<#
.SYNOPSIS
    Runs a python entry-point script and reports the result via exit code.

.DESCRIPTION
    Generic launcher, extracted from the pricing pipeline (originally
    Invoke-PricingRun.ps1) so other domains (earnings, dividends,
    corporate events, ...) can reuse the same launch/wait/timeout/log
    mechanics without copy-pasting this script and risking drift between
    copies. Nothing in here is pricing-specific - it always was; this
    just makes that formal.

    VBA's job is: launch this script (via WshShell .Exec), then check the
    exit code and/or poll wherever the target script writes its own output.

    Exit codes:
      0  the target script completed and reported success
      1  the target script ran but reported failure - check the log file
      2  the python process could not be started at all (bad interpreter
         path, script not found, etc.) - nothing was attempted
      3  the run exceeded -TimeoutSeconds and was forcibly killed

.PARAMETER PythonExe
    Path to the venv's python.exe.

.PARAMETER ScriptPath
    Path to the python entry-point script to run. Also determines the
    log file's name prefix (see LogDirectory) - no separate parameter
    needed for that, since different entry points naturally want
    differently-named logs and this script's own filename already says
    which one ran.

.PARAMETER Workbook
    Exact filename of the already-open workbook to target, e.g.
    "snapshot.xlsm". Required, no default - forwarded straight through
    to the target script's own required --workbook argument.

.PARAMETER TimeoutSeconds
    Maximum time to wait before killing the python process. Default is a
    guess (120s) - adjust per entry point once real timing data exists.

.PARAMETER LogDirectory
    Where per-run log files are written. Old logs are pruned at the start
    of every run (see LogRetentionDays) - no separate scheduled task
    needed, since this script already runs on essentially every update.

.PARAMETER LogRetentionDays
    Log files older than this are deleted at the start of each run.
    Default 14 days - adjust if you want a longer or shorter window.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,

    [Parameter(Mandatory = $true)]
    [string]$ScriptPath,

    [Parameter(Mandatory = $true)]
    [string]$Workbook,

    [int]$TimeoutSeconds = 120,

    [string]$LogDirectory,

    [int]$LogRetentionDays = 7
)

$ErrorActionPreference = "Stop"

if (-not $LogDirectory) {
    $LogDirectory = Join-Path $PSScriptRoot "..\runtime\logs"
}

function Write-Log {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $Message"
    Write-Output $line
    Add-Content -Path $script:LogFile -Value $line
}

if (-not (Test-Path $LogDirectory)) {
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
}

# Prune anything older than the retention window before writing this
# run's own log - keeps the folder bounded without a separate scheduled
# task, since this runs on essentially every update anyway. A locked or
# otherwise undeletable file is skipped, not fatal to the actual run.
Get-ChildItem $LogDirectory -Filter "*.log" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$LogRetentionDays) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Log filename prefix comes from the target script's own name (e.g.
# "pricing_run_all" or a future "earnings_run_all"), not a hardcoded
# "pricing_run" - keeps logs from different entry points distinguishable
# in the same folder without needing a separate parameter for it.
$scriptStem = [System.IO.Path]::GetFileNameWithoutExtension($ScriptPath)
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDirectory "${scriptStem}_$timestamp.log"
$stdoutFile = "$LogFile.stdout.tmp"
$stderrFile = "$LogFile.stderr.tmp"

if (-not (Test-Path $PythonExe)) {
    Write-Log "ERROR: python.exe not found at '$PythonExe'"
    exit 2
}
if (-not (Test-Path $ScriptPath)) {
    Write-Log "ERROR: entry point script not found at '$ScriptPath'"
    exit 2
}

Write-Log "Starting run for '$Workbook': `"$PythonExe`" `"$ScriptPath`" (timeout ${TimeoutSeconds}s)"

try {
    $process = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList @("`"$ScriptPath`"", "--workbook", "`"$Workbook`"") `
        -WorkingDirectory (Join-Path $PSScriptRoot "..") `
        -NoNewWindow `
        -PassThru `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile
} catch {
    Write-Log "ERROR launching python process: $_"
    exit 2
}

$completed = $process.WaitForExit($TimeoutSeconds * 1000)

if (-not $completed) {
    Write-Log "TIMEOUT: exceeded ${TimeoutSeconds}s - killing process id $($process.Id)"
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 200  # let the redirected-output file handles release
    Get-Content $stdoutFile -ErrorAction SilentlyContinue | Add-Content $LogFile
    Get-Content $stderrFile -ErrorAction SilentlyContinue | Add-Content $LogFile
    Remove-Item $stdoutFile, $stderrFile -ErrorAction SilentlyContinue
    exit 3
}

Get-Content $stdoutFile -ErrorAction SilentlyContinue | Add-Content $LogFile
Get-Content $stderrFile -ErrorAction SilentlyContinue | Add-Content $LogFile
Remove-Item $stdoutFile, $stderrFile -ErrorAction SilentlyContinue

$exitCode = $process.ExitCode
Write-Log "Run finished with exit code $exitCode"

exit $exitCode