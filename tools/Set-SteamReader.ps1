param(
    [Parameter(Mandatory=$true)][string]$SteamDirectory,
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [Parameter(Mandatory=$true)][ValidateSet('Install','Restore')][string]$Action
)
$ErrorActionPreference='Stop'
$originalHash='e8656a70d57eb5cfa5e20a4c96c45f7f72325a3a109135e919d033f233fa3fb7'
$candidateHash='55a6d7993ad945fa26ee30b046d553e3c1d7c7b8f97c064e491158af1aad30df'
if (@(Get-Process -Name steam,steamwebhelper,gameoverlayui -ErrorAction SilentlyContinue).Count) {
    throw 'Exit Steam and Steam games fully before replacing the reader.'
}
$steamRoot=(Resolve-Path -LiteralPath $SteamDirectory).Path
$buildRoot=(Resolve-Path -LiteralPath $BuildDirectory).Path
$target=Join-Path $steamRoot 'SDL3.dll'
$original=Join-Path $buildRoot 'original\SDL3.dll'
if ((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash -ine $originalHash) {throw 'Original backup hash mismatch.'}
$current=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
if ($Action -eq 'Restore') {
    if ($current -ieq $originalHash) {'Original reader is already installed.';return}
    if ($current -ine $candidateHash) {throw 'Unknown installed DLL; a Steam update may have replaced it. No replacement performed.'}
    $source=$original;$expected=$originalHash
} else {
    if ($current -ine $originalHash) {throw 'Installed DLL does not match the supported original. No replacement performed.'}
    $source=Join-Path $buildRoot 'candidate\SDL3.dll';$expected=$candidateHash
    $baseline=Get-Content -LiteralPath (Join-Path $buildRoot 'original-result.json') -Raw | ConvertFrom-Json
    $test=Get-Content -LiteralPath (Join-Path $buildRoot 'candidate-result.json') -Raw | ConvertFrom-Json
    if (-not $baseline.passed -or -not $test.passed -or $test.exhaustive_fine_cases -ne 262144 -or $test.fixture_rows -ne 45252 -or $test.fallback_cases -ne 4096 -or $test.other_pid_fallback_cases -ne 256 -or $test.stock_replay_sha256 -ne $baseline.stock_replay_sha256) {
        throw 'Parser replay validation is incomplete.'
    }
}
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ine $expected) {throw 'Source reader hash mismatch.'}
$staging=Join-Path $steamRoot ('SDL3.ultimate2-'+[Guid]::NewGuid().ToString('N')+'.tmp')
try {
    Copy-Item -LiteralPath $source -Destination $staging
    if ((Get-FileHash -LiteralPath $staging -Algorithm SHA256).Hash -ine $expected) {throw 'Staged reader hash mismatch; installed file retained.'}
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ine $current) {throw 'Target changed during preparation; installed file retained.'}
    [IO.File]::Replace($staging,$target,[NullString]::Value)
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ine $expected) {throw 'Installed reader verification failed; inspect before starting Steam.'}
} finally {
    if (Test-Path -LiteralPath $staging) {Remove-Item -LiteralPath $staging}
}
"$Action complete; installed SHA-256: $expected"
