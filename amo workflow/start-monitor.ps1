<#
Start the monitor as a detached background process and write its PID to monitor.pid
#>
$PidFile = Join-Path $PSScriptRoot 'monitor.pid'
$MonitorScript = Join-Path $PSScriptRoot 'monitor.ps1'

if (-Not (Test-Path $MonitorScript)) { Write-Error "monitor.ps1 not found at $MonitorScript"; exit 1 }

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'pwsh'
$psi.Arguments = "-NoProfile -WindowStyle Hidden -File `"$MonitorScript`""
$psi.UseShellExecute = $true

$p = [System.Diagnostics.Process]::Start($psi)
if ($p -ne $null) {
    $p.Id | Out-File -FilePath $PidFile -Encoding ascii
    Write-Output "Started monitor pid=$($p.Id)"
} else {
    Write-Error "Failed to start monitor process"
}
