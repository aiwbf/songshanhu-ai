param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("health", "ensure-gateway", "send-message", "agent-message", "browser-sequence")]
    [string]$Action,

    [string]$Channel,
    [string]$Target,
    [string]$Message,
    [string]$Agent = "main",
    [string]$SequenceFile,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:OpenClawCommand = if ([string]::IsNullOrWhiteSpace($env:OPENCLAW_COMMAND)) { "openclaw.cmd" } else { $env:OPENCLAW_COMMAND }

function Ensure-Value {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required for action '$Action'."
    }
}

function Ensure-OpenClaw {
    $cmd = Get-Command $script:OpenClawCommand -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "OpenClaw command not found: $script:OpenClawCommand"
    }
}

function Invoke-OpenClaw {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    Write-Host ">> $script:OpenClawCommand $($Args -join ' ')"
    & $script:OpenClawCommand @Args
    if ($LASTEXITCODE -ne 0) {
        throw "openclaw exited with code $LASTEXITCODE."
    }
}

function Run-BrowserSequence {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PlanPath
    )

    if (-not (Test-Path -LiteralPath $PlanPath)) {
        throw "Sequence file not found: $PlanPath"
    }

    $raw = Get-Content -LiteralPath $PlanPath -Raw
    $plan = $raw | ConvertFrom-Json
    if (-not $plan.steps) {
        throw "Sequence JSON must contain a 'steps' array."
    }
    $steps = @($plan.steps)

    $allowed = @(
        "start", "status", "open", "navigate", "snapshot", "click", "type", "press",
        "wait", "screenshot", "fill", "select", "close", "tabs", "focus",
        "scrollintoview", "highlight"
    )

    foreach ($step in $steps) {
        $hasCommand = $step.PSObject.Properties.Name -contains "command"
        if (-not $hasCommand -or [string]::IsNullOrWhiteSpace([string]$step.command)) {
            throw "Each step must include 'command'."
        }

        $command = [string]$step.command
        if ($allowed -notcontains $command) {
            throw "Unsupported browser command '$command'."
        }

        $args = @("browser", $command)
        $hasArgs = $step.PSObject.Properties.Name -contains "args"
        if ($hasArgs -and $null -ne $step.args) {
            if ($step.args -is [System.Array]) {
                foreach ($arg in $step.args) {
                    $args += [string]$arg
                }
            }
            else {
                $args += [string]$step.args
            }
        }

        $wantJson = $Json
        $hasJson = $step.PSObject.Properties.Name -contains "json"
        if ($hasJson -and $null -ne $step.json) {
            $wantJson = [bool]$step.json
        }
        if ($wantJson) {
            $args += "--json"
        }

        Invoke-OpenClaw -Args $args
    }
}

Ensure-OpenClaw

switch ($Action) {
    "health" {
        Invoke-OpenClaw -Args @("gateway", "health")
    }

    "ensure-gateway" {
        try {
            Invoke-OpenClaw -Args @("gateway", "health")
        }
        catch {
            Write-Host "Gateway not healthy. Enabling and running scheduled task..."
            & schtasks /change /tn "OpenClaw Gateway" /enable | Out-Host
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to enable scheduled task 'OpenClaw Gateway'."
            }

            & schtasks /run /tn "OpenClaw Gateway" | Out-Host
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to run scheduled task 'OpenClaw Gateway'."
            }

            Start-Sleep -Seconds 4
            Invoke-OpenClaw -Args @("gateway", "health")
        }
    }

    "send-message" {
        Ensure-Value -Name "Channel" -Value $Channel
        Ensure-Value -Name "Target" -Value $Target
        Ensure-Value -Name "Message" -Value $Message

        $args = @("message", "send", "--channel", $Channel, "--target", $Target, "--message", $Message)
        if ($Json) {
            $args += "--json"
        }
        Invoke-OpenClaw -Args $args
    }

    "agent-message" {
        Ensure-Value -Name "Message" -Value $Message
        $args = @("agent", "--agent", $Agent, "--message", $Message)
        if ($Json) {
            $args += "--json"
        }
        Invoke-OpenClaw -Args $args
    }

    "browser-sequence" {
        Ensure-Value -Name "SequenceFile" -Value $SequenceFile
        Run-BrowserSequence -PlanPath $SequenceFile
    }
}
