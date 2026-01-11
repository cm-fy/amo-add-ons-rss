<#
backup_repo.ps1

Creates a self-contained offline backup for a GitHub repo including:
- mirror clone + working copy + bundle
- workflow definitions
- Actions runs (logs + artifacts)
- GitHub Pages site mirror
- repo metadata, Pages builds, environments, and secret NAMES

Prereqs: git, GitHub CLI (gh), jq (optional), wget (optional)
Usage: .\backup_repo.ps1 <OWNER/REPO> [OutDir]
Example: .\backup_repo.ps1 cm-fy/amo-add-ons-rss C:\backups\amo-backup
#>

param(
    [string]$Repo,
    [string]$OutDir
)

function Fail($msg) { Write-Error $msg; exit 1 }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git is required but not found on PATH' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Fail 'GitHub CLI (gh) is required but not found on PATH' }

if ([string]::IsNullOrEmpty($OutDir)) {
    $safe = $Repo -replace '[\\/:]','_' -replace '\s','_'
    $OutDir = Join-Path (Get-Location) "backup_${safe}_$(Get-Date -Format 'yyyy-MM-dd_HHmmss')"
}

if ([string]::IsNullOrEmpty($Repo)) {
    # Try to auto-detect from git remote origin
    try {
        $remoteUrl = (git config --get remote.origin.url) -as [string]
    } catch {
        $remoteUrl = $null
    }
    if ([string]::IsNullOrEmpty($remoteUrl)) {
        # fallback: try gh to detect repo from current directory (requires gh auth)
        try {
            $ghRepo = & gh repo view --json nameWithOwner --jq .nameWithOwner 2>$null
            if ($ghRepo) { $remoteUrl = $ghRepo }
        } catch {
            # ignore
        }
    }
    if ([string]::IsNullOrEmpty($remoteUrl)) {
        Fail 'No repo parameter provided and no git remote.origin.url found. Provide OWNER/REPO explicitly.'
    }

    # Parse git@github.com:owner/repo.git or https://github.com/owner/repo.git
    if ($remoteUrl -match 'git@[^:]+:([^/]+)/([^/]+?)(?:\.git)?$') {
        $Repo = "$($matches[1])/$($matches[2])"
    } elseif ($remoteUrl -match 'https?://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$') {
        $Repo = "$($matches[1])/$($matches[2])"
    } else {
        # last resort: strip .git and hostname if present
        $tmp = $remoteUrl -replace '\.git$',''
        if ($tmp -match '/([^/]+/[^/]+)$') { $Repo = $matches[1] }
    }
}

Write-Output "Backing up $Repo → $OutDir"
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

Set-Location $OutDir

## 1) Full repo copies
Write-Output '[1/9] Cloning repository (mirror)'
git clone --mirror "https://github.com/$Repo.git" "$OutDir\repo.git"
Write-Output '[1/9] Cloning repository (working copy)'
git clone "https://github.com/$Repo.git" "$OutDir\repo-working"
Write-Output '[1/9] Creating bundle of all refs'
git --git-dir="$OutDir\repo.git" bundle create "$OutDir\repo.bundle" --all

## 2) Workflow files
Write-Output '[2/9] Copying workflow definitions'
if (Test-Path "$OutDir\repo-working\.github\workflows") {
    Copy-Item -Path "$OutDir\repo-working\.github\workflows" -Destination "$OutDir\workflows" -Recurse -Force
}

## 3) Actions runs, logs and artifacts
Write-Output '[3/9] Downloading Actions runs (logs + artifacts) — requires gh auth'
New-Item -ItemType Directory -Path "$OutDir\actions\runs" -Force | Out-Null
try {
    $runIds = gh run list --repo $Repo --limit 1000 --json id --jq '.[].id' 2>$null
} catch {
    Write-Warning "Failed to list runs via gh: $_"
    $runIds = @()
}
foreach ($id in $runIds -split "`n") {
    $id = $id.Trim()
    if ([string]::IsNullOrEmpty($id)) { continue }
    Write-Output " - downloading run $id"
    $dest = "$OutDir\actions\runs\$id"
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    & gh run download $id --repo $Repo --dir $dest --logs 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Warning "Failed download for run $id" }
}

## 4) Pages site mirror
Write-Output '[4/9] Determining Pages URL'
$pageUrl = $null
try { $pageUrl = gh api repos/$Repo/pages --jq .html_url 2>$null } catch { }
if ([string]::IsNullOrEmpty($pageUrl) -or $pageUrl -eq 'null') {
    $owner = $Repo.Split('/')[0]
    $name = $Repo.Split('/')[1]
    $pageUrl = "https://$owner.github.io/$name/"
}
Write-Output "Pages URL: $pageUrl"
New-Item -ItemType Directory -Path "$OutDir\pages" -Force | Out-Null

if (Get-Command wget -ErrorAction SilentlyContinue) {
    Write-Output '[4/9] Using wget to mirror site (retries: 3, wait-retry: 9s)'
    # Use wget's built-in retry logic; don't swallow output so network issues are visible.
    $wgetArgs = @(
        '--mirror',
        '--convert-links',
        '--adjust-extension',
        '--page-requisites',
        '--no-parent',
        '--span-hosts',
        '--tries=3',
        '--waitretry=9',
        '--timeout=15',
        '-P', "$OutDir\pages",
        $pageUrl
    )
    & wget @wgetArgs
    $exit = $LASTEXITCODE
    if ($exit -ne 0) {
        Write-Warning "wget exited with code $exit; falling back to a single-page fetch of the site root. See wget output for details."
        try {
            Invoke-WebRequest -Uri $pageUrl -OutFile "$OutDir\pages\index.html" -UseBasicParsing -ErrorAction Stop
        } catch { Write-Warning ("Fallback failed to fetch {0}: {1}" -f $pageUrl, $_.Exception.Message) }
    }
} else {
    Write-Output '[4/9] wget not found — saving root index and common assets via Invoke-WebRequest'
    try {
        Invoke-WebRequest -Uri $pageUrl -OutFile "$OutDir\pages\index.html" -UseBasicParsing -ErrorAction Stop
    } catch { Write-Warning ("Failed to fetch {0}: {1}" -f $pageUrl, $_.Exception.Message) }
}

## 5) Pages builds metadata
Write-Output '[5/9] Exporting Pages build metadata'
& gh api repos/$Repo/pages/builds --paginate > "$OutDir\pages-builds.json" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warning 'Pages builds API failed' }

## 6) Repo metadata, settings, actions permissions, environments
Write-Output '[6/9] Exporting repo metadata and settings'
& gh api repos/$Repo > "$OutDir\repo-settings.json" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warning 'repo settings export failed' }
& gh api repos/$Repo/actions/permissions > "$OutDir\actions-permissions.json" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warning 'actions permissions export failed' }
& gh api repos/$Repo/environments --paginate > "$OutDir\environments.json" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warning 'environments export failed' }

Write-Output '[6/9] Listing action secret NAMES (values not exportable)'
& gh api repos/$Repo/actions/secrets --jq '.secrets[].name' > "$OutDir\actions-secret-names.txt" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warning 'list secrets failed' }

New-Item -ItemType Directory -Path "$OutDir\environments" -Force | Out-Null
try {
    $envs = (Get-Content "$OutDir\environments.json" -ErrorAction SilentlyContinue | Out-String) -join ""
    $envNames = @()
    if ($envs) { $envNames = (ConvertFrom-Json $envs).environments | ForEach-Object { $_.name } }
    foreach ($e in $envNames) {
        & gh api repos/$Repo/environments/$e/secrets --jq '.secrets[].name' > "$OutDir\environments\$e-secrets.txt" 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Warning "failed to list secrets for env $e" }
    }
} catch { }

## 7) Copy important working files
Write-Output '[7/9] Copying important repo files from working clone'
Copy-Item -Path "$OutDir\repo-working\*" -Destination "$OutDir\repo-files" -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item -Path "$OutDir\repo-working\.github" -Destination "$OutDir\.github" -Recurse -Force -ErrorAction SilentlyContinue

## 8) Save GH workflow run list for quick reference
try { gh run list --repo $Repo --limit 1000 --json databaseRecordUrl,name,createdAt,status > "$OutDir\actions-run-list.json" 2>$null } catch { }

## 9) Package into zip
Write-Output '[8/9] Creating final ZIP archive'
$archive = "$OutDir.zip"
if (Test-Path $archive) { Remove-Item $archive -Force }
Compress-Archive -Path "$OutDir\*" -DestinationPath $archive -Force

Write-Output "Backup complete: $archive"
Write-Output "Note: secret values are NOT exportable. Recreate them manually in the target repo."
