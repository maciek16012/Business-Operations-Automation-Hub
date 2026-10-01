Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$DemoProject = 'boah-portfolio-demo'
$DemoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$DemoRuntime = [IO.Path]::GetFullPath((Join-Path $DemoRoot '.runtime-demo'))
if ($DemoRuntime -ne (Join-Path $DemoRoot '.runtime-demo')) { throw 'Unexpected demo runtime path.' }
function Assert-DemoPath([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        if ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Refusing linked demo path: $Path"
        }
    }
}
Assert-DemoPath $DemoRuntime
function Assert-DemoIdentity {
    Assert-DemoPath (Join-Path $DemoRuntime 'identity.json')
    Assert-DemoPath (Join-Path $DemoRuntime 'demo.env')
    $identity = Get-Content -LiteralPath (Join-Path $DemoRuntime 'identity.json') -Raw | ConvertFrom-Json
    if ($identity.project -ne $DemoProject -or $identity.kind -ne 'BOAH_M8_SYNTHETIC_DEMO') {
        throw 'Not an owned M8 demo runtime. No changes made.'
    }
}
function Get-DemoArgs {
    @('--project-name', $DemoProject, '--env-file', (Join-Path $DemoRuntime 'demo.env'), '-f', (Join-Path $DemoRoot 'docker-compose.demo.yml'))
}
function Invoke-Demo {
    $DockerArguments = @($args)
    & docker compose @(Get-DemoArgs) @DockerArguments
    if ($LASTEXITCODE -ne 0) { throw "Demo Docker operation failed ($($DockerArguments[0])). Inspect docker compose logs; credentials were retained." }
}
function New-DemoRandom([int]$Size=32) {
    $bytes = New-Object byte[] $Size
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}
