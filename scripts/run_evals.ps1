param(
    [string]$Dataset = "",
    [string]$FailureModes = "",
    [string]$Policy = "",
    [string]$ReportDir = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$argsList = @("scripts/run_evals.py")

if ($Dataset) {
    $argsList += @("--dataset", $Dataset)
}
if ($FailureModes) {
    $argsList += @("--failure-modes", $FailureModes)
}
if ($Policy) {
    $argsList += @("--policy", $Policy)
}
if ($ReportDir) {
    $argsList += @("--report-dir", $ReportDir)
}

Push-Location $root
try {
    & python -X utf8 @argsList
}
finally {
    Pop-Location
}
