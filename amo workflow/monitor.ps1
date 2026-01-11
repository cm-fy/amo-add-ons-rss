param(
    [int]$IntervalSeconds = 300
)

$LogDir = Join-Path $PSScriptRoot 'monitor_logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir 'feed-monitor.log'

$urls = @(
    'https://cm-fy.github.io/amo-add-ons-rss/amo_latest_extensions.xml',
    'https://cm-fy.github.io/amo-add-ons-rss/public/amo_latest_extensions.xml'
)

function Get-HeadInfo($uri) {
    try {
        $resp = Invoke-WebRequest -Uri $uri -Method Head -UseBasicParsing -TimeoutSec 15
        return @{ Status = $resp.StatusCode; Headers = $resp.Headers }
    } catch {
        return @{ Error = $_.Exception.Message }
    }
}

function Get-ContentHash($uri) {
    try {
        $b = Invoke-RestMethod -Uri $uri -Method Get -UseBasicParsing -TimeoutSec 30 -ErrorAction Stop
        if ($null -eq $b) { return $null }
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($b.ToString())
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $hash = $sha.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hash)).Replace('-', '').ToLower()
    } catch {
        return $null
    }
}

while ($true) {
    $t = (Get-Date).ToString('o')
    Add-Content -Path $LogFile -Value "=== $t ==="
    foreach ($u in $urls) {
        Add-Content -Path $LogFile -Value "--- $u ---"
        $h = Get-HeadInfo $u
        if ($h.ContainsKey('Error')) {
            Add-Content -Path $LogFile -Value "HEAD ERROR: $($h.Error)"
        } else {
            Add-Content -Path $LogFile -Value "Status: $($h.Status)"
            if ($h.Headers.ETag) { Add-Content -Path $LogFile -Value "ETag: $($h.Headers.ETag)" }
            if ($h.Headers.'Last-Modified') { Add-Content -Path $LogFile -Value "Last-Modified: $($h.Headers.'Last-Modified')" }
        }
        $hash = Get-ContentHash $u
        if ($hash) { Add-Content -Path $LogFile -Value "SHA256: $hash" } else { Add-Content -Path $LogFile -Value "SHA256: (fetch failed)" }
    }
    Start-Sleep -Seconds $IntervalSeconds
}
