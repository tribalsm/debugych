# Use a native Docker CLI when installed; otherwise the verified Ubuntu WSL engine.
# Call from repository root: .\scripts\compose.ps1 up --build
$ErrorActionPreference = 'Stop'
if (Get-Command docker -ErrorAction SilentlyContinue) {
    & docker compose @args
} else {
    & wsl -d Ubuntu -u root -- docker compose @args
}
exit $LASTEXITCODE
