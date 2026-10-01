[CmdletBinding()]
param([switch]$SkipSeed, [switch]$WithEmail)
. (Join-Path $PSScriptRoot 'common.ps1')
& docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop with Linux containers first.' }
if (!(Test-Path -LiteralPath (Join-Path $DemoRuntime 'identity.json'))) {
    if (Test-Path -LiteralPath (Join-Path $DemoRuntime 'demo.env')) { throw 'Unowned existing demo.env; refusing overwrite.' }
    New-Item -ItemType Directory -Force -Path $DemoRuntime | Out-Null
    foreach ($folder in @('incoming','archive','protocols','n8n')) { New-Item -ItemType Directory -Force -Path (Join-Path $DemoRuntime $folder) | Out-Null }
    if ($env:OS -eq 'Windows_NT') {
        $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        & icacls $DemoRuntime /inheritance:r /grant:r "*$($sid):(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not protect demo runtime ACL.' }
    }
    $keyBytes=New-Object byte[] 32; $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($keyBytes) } finally { $rng.Dispose() }
    $values=[ordered]@{
        POSTGRES_PASSWORD=(New-DemoRandom); BOAH_MASTER_KEY=[Convert]::ToBase64String($keyBytes)
        BOAH_INITIAL_ADMIN_EMAIL='admin@example.com'; BOAH_INITIAL_ADMIN_PASSWORD=(New-DemoRandom)
        BOAH_SERVICE_TOKEN=(New-DemoRandom 48); M7_MAIL_PASSWORD=(New-DemoRandom)
        M7_WEBHOOK_HMAC=(New-DemoRandom); M8_VIEWER_PASSWORD=(New-DemoRandom)
        M8_REVIEWER_PASSWORD=(New-DemoRandom); M8_OPERATOR_PASSWORD=(New-DemoRandom)
    }
    [IO.File]::WriteAllLines((Join-Path $DemoRuntime 'demo.env'), @($values.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }), [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $DemoRuntime 'identity.json'), '{"project":"boah-portfolio-demo","kind":"BOAH_M8_SYNTHETIC_DEMO"}', [Text.UTF8Encoding]::new($false))
}
Assert-DemoIdentity
Push-Location $DemoRoot
try {
    Invoke-Demo config --quiet
    Invoke-Demo build backend frontend tesseract paddle clamav
    Invoke-Demo up -d --no-build --wait --wait-timeout 1200
    Invoke-Demo exec -T backend python /demo-tools/seed_demo.py prepare-n8n
    # Temporary credential copies are readable only by the n8n runtime account.
    Invoke-Demo cp (Join-Path $DemoRuntime 'n8n/credential.json') n8n:/tmp/boah-demo-credential.json
    Invoke-Demo cp (Join-Path $DemoRuntime 'n8n/workflow.json') n8n:/tmp/boah-demo-workflow.json
    Invoke-Demo exec -T -u root n8n sh -c 'chown node:node /tmp/boah-demo-credential.json /tmp/boah-demo-workflow.json && chmod 600 /tmp/boah-demo-credential.json /tmp/boah-demo-workflow.json'
    try {
        Invoke-Demo exec -T n8n n8n import:credentials --input=/tmp/boah-demo-credential.json
        Invoke-Demo exec -T n8n n8n import:workflow --input=/tmp/boah-demo-workflow.json
        Invoke-Demo exec -T n8n n8n publish:workflow --id=boahReviewM5
    } finally {
        Invoke-Demo exec -T -u root n8n rm -f /tmp/boah-demo-credential.json /tmp/boah-demo-workflow.json
    }
    Invoke-Demo restart n8n
    Invoke-Demo up -d --no-build --wait --wait-timeout 180
    if (!$SkipSeed) { Invoke-Demo exec -T backend python /demo-tools/seed_demo.py seed }
    if ($WithEmail) { Invoke-Demo exec -T backend python /demo-tools/seed_demo.py email }
    Write-Host 'Demo ready: http://localhost:3080'
    Write-Host "Generated local login details: $(Join-Path $DemoRuntime 'login.txt')"
    Write-Host 'HTTP and test-only plaintext IMAP are local demo settings. Do not expose this profile publicly.'
} finally { Pop-Location }
