[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$demoTaskName = 'SPIA-Demo-Server'
$demoRoot = $PSScriptRoot
$demoBackend = Join-Path $demoRoot 'spi-chatbot\backend'
$demoPython = Join-Path $demoBackend '.venv\Scripts\python.exe'
$demoRunner = Join-Path $demoBackend 'run_demo.py'

$demoIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$demoWindowsPrincipal = [System.Security.Principal.WindowsPrincipal]::new(
    $demoIdentity
)

if (-not $demoWindowsPrincipal.IsInRole(
    [System.Security.Principal.WindowsBuiltInRole]::Administrator
)) {
    throw 'Open Windows PowerShell using Run as administrator, then run this script again.'
}

foreach ($demoPath in @($demoPython, $demoRunner)) {
    if (-not (Test-Path -LiteralPath $demoPath -PathType Leaf)) {
        throw "Required file is missing: $demoPath"
    }
}

if (Get-ScheduledTask `
    -TaskName $demoTaskName `
    -TaskPath '\' `
    -ErrorAction SilentlyContinue
) {
    throw 'SPIA-Demo-Server already exists. Stop here; do not register a duplicate task.'
}

if (Get-NetTCPConnection `
    -LocalPort 8000 `
    -State Listen `
    -ErrorAction SilentlyContinue
) {
    throw 'Port 8000 is already in use. Stop the manually running backend with Ctrl+C first.'
}

& $demoPython -m py_compile $demoRunner

if ($LASTEXITCODE -ne 0) {
    throw 'run_demo.py failed compilation. Share the error above.'
}

$demoPythonLiteral = $demoPython.Replace("'", "''")
$demoRunnerLiteral = $demoRunner.Replace("'", "''")

$demoCommand = "& '$demoPythonLiteral' -u '$demoRunnerLiteral' --host 0.0.0.0 --background; exit `$LASTEXITCODE"

$demoEncoded = [Convert]::ToBase64String(
    [System.Text.Encoding]::Unicode.GetBytes($demoCommand)
)

$demoPowerShell = Join-Path `
    $env:WINDIR `
    'System32\WindowsPowerShell\v1.0\powershell.exe'

$demoAction = New-ScheduledTaskAction `
    -Execute $demoPowerShell `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand $demoEncoded" `
    -WorkingDirectory $demoBackend

$demoTrigger = New-ScheduledTaskTrigger `
    -AtLogOn `
    -User $demoIdentity.Name

$demoPrincipal = New-ScheduledTaskPrincipal `
    -UserId $demoIdentity.Name `
    -LogonType Interactive `
    -RunLevel Limited

$demoSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $demoTaskName `
    -TaskPath '\' `
    -Action $demoAction `
    -Trigger $demoTrigger `
    -Principal $demoPrincipal `
    -Settings $demoSettings `
    -Description 'SPIA fictional demo server; runs after this Windows user signs in.' |
    Out-Null

Start-ScheduledTask -TaskName $demoTaskName -TaskPath '\'

Write-Host 'REGISTERED: SPIA-Demo-Server; startup requested.'

$demoReady = $false

for ($demoAttempt = 0; $demoAttempt -lt 20; $demoAttempt++) {
    try {
        $demoResponse = Invoke-WebRequest `
            -Uri 'http://127.0.0.1:8000/' `
            -UseBasicParsing `
            -TimeoutSec 2

        if ($demoResponse.StatusCode -eq 200) {
            $demoReady = $true
            break
        }
    }
    catch {
        # The process may still be starting.
    }

    Start-Sleep -Milliseconds 500
}

if (-not $demoReady) {
    throw "The task was registered, but the server did not respond. Check $demoBackend\logs\demo-server.log"
}

Write-Host 'PASS: the background server responded on port 8000.'
Write-Host 'Verify http://127.0.0.1:8000 in your browser.'
Write-Host "Server log: $(Join-Path $demoBackend 'logs\demo-server.log')"