[CmdletBinding()]
param([switch]$ConfirmDemoReset)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-DemoIdentity
Write-Warning "PERMANENTLY deletes only $DemoProject demo containers, five dedicated volumes and $DemoRuntime. Production and M7 resources are excluded."
if (!$ConfirmDemoReset) {
    if ((Read-Host "Type $DemoProject to confirm") -cne $DemoProject) { throw 'Reset cancelled.' }
}
$allowed=@('demo_db','demo_storage','demo_n8n','demo_paddle_models','demo_clam_signatures') | ForEach-Object { "$($DemoProject)_$_" }
$volumes=@(& docker volume ls --filter "label=com.docker.compose.project=$DemoProject" --format '{{.Name}}')
if ($LASTEXITCODE -ne 0) { throw 'Docker volume inventory failed.' }
foreach ($volume in $volumes) {
    if ($volume -notin $allowed) { throw "Unexpected volume under demo project: $volume. Reset refused." }
    $owner=& docker volume inspect --format '{{index .Labels "com.docker.compose.project"}}' $volume
    if ($LASTEXITCODE -ne 0 -or $owner -ne $DemoProject) { throw 'Volume ownership check failed.' }
}
$containers=@(& docker ps -a --filter "label=com.docker.compose.project=$DemoProject" --format '{{.Names}}')
if ($LASTEXITCODE -ne 0) { throw 'Docker container inventory failed.' }
foreach ($container in $containers) {
    if (!$container.StartsWith("$DemoProject-")) { throw 'Unexpected container name. Reset refused.' }
}
Push-Location $DemoRoot
try { Invoke-Demo down --volumes } finally { Pop-Location }
Assert-DemoPath $DemoRuntime
$resolved=(Resolve-Path -LiteralPath $DemoRuntime).Path
if ($resolved -ne (Join-Path $DemoRoot '.runtime-demo')) { throw 'Cleanup target outside demo runtime. Refused.' }
Remove-Item -LiteralPath $resolved -Recurse -Force
Write-Host 'Dedicated demo reset complete. Run start_demo.ps1 to regenerate fresh random credentials.'
