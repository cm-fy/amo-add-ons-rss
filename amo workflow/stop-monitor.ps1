<#
Stop the monitor process started by `start-monitor.ps1` using the PID file.
#>
$PidFile = Join-Path $PSScriptRoot 'monitor.pid'
if (-Not (Test-Path $PidFile)) { Write-Output "No PID file found at $PidFile"; exit 0 }

$pid = Get-Content $PidFile | Select-Object -First 1
try {
    Stop-Process -Id $pid -Force -ErrorAction Stop
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Output "Stopped monitor pid=$pid"
} catch {
    Write-Output "Failed to stop pid=$pid: $_"
}
