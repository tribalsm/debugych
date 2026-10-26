param([switch]$ReuseBackend,[switch]$Build,[int]$Port=8798,[string]$EnvFile,[string]$ComposeProject='debugych',[string]$WslDistro='Ubuntu')
$ErrorActionPreference='Stop'
$appRoot=Split-Path $PSScriptRoot -Parent
if(-not(Get-Command node -ErrorAction SilentlyContinue)){throw 'Install Node.js 22 or newer, or use the existing Docker Compose web service.'}
if($Port -lt 1024 -or $Port -gt 65535){throw 'Choose a port from 1024 to 65535.'}
if(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue){throw "Port $Port is already in use. Existing processes will not be stopped."}
$keepWsl=$null
try{
 $healthy=$false;try{$h=Invoke-RestMethod http://127.0.0.1:8000/api/health -TimeoutSec 4;$healthy=$h.status -eq 'ok' -and $h.execution -in @('gvisor-python','trusted-demo-only')}catch{}
 if(-not $healthy){
  if($ReuseBackend){throw 'The existing backend is not available at http://127.0.0.1:8000. No containers were changed.'}
  if(-not $EnvFile){$EnvFile=Join-Path $appRoot '.env'}
  if(-not(Test-Path -LiteralPath $EnvFile)){Copy-Item -LiteralPath (Join-Path $appRoot '.env.example') -Destination $EnvFile;Write-Host 'Created local .env without an API key. Add a key there if needed, never in the browser.'}
  $composeArgs=@('compose','-p',$ComposeProject,'--env-file',$EnvFile,'-f',(Join-Path $appRoot 'docker-compose.yml'),'up','-d','--build')
  if(Get-Command docker -ErrorAction SilentlyContinue){
   $runtimes=& docker info --format '{{json .Runtimes}}';if($LASTEXITCODE -ne 0 -or $runtimes -notmatch 'runsc'){throw 'A Linux Docker Engine with registered runsc is required. See docs/debugych-web-integration.md.'}
   & docker @composeArgs
  }else{
   $keepWsl=Start-Process -FilePath wsl -ArgumentList @('-d',$WslDistro,'-u','root','--','sleep','infinity') -WindowStyle Hidden -PassThru
   $runtimes=& wsl -d $WslDistro -u root -- docker info --format '{{json .Runtimes}}';if($LASTEXITCODE -ne 0 -or $runtimes -notmatch 'runsc'){throw 'WSL Docker requires registered runsc. Setup is documented; this launcher does not restart Docker or install gVisor.'}
   $linuxRoot=(& wsl -d $WslDistro -- wslpath -a $appRoot).Trim();$linuxEnv=(& wsl -d $WslDistro -- wslpath -a (Resolve-Path -LiteralPath $EnvFile).Path).Trim()
   & wsl -d $WslDistro -u root -- docker compose -p $ComposeProject --env-file $linuxEnv -f "$linuxRoot/docker-compose.yml" up -d --build
  }
  if($LASTEXITCODE -ne 0){throw 'Compose startup failed. Existing unrelated stacks were not stopped.'}
  for($i=0;$i -lt 60;$i++){try{$h=Invoke-RestMethod http://127.0.0.1:8000/api/health -TimeoutSec 3;if($h.status -eq 'ok'){$healthy=$true;break}}catch{};Start-Sleep -Seconds 2}
  if(-not $healthy){throw 'Backend did not become healthy. Inspect this Compose project logs.'}
 }
 if(-not $keepWsl -and -not(Get-Command docker -ErrorAction SilentlyContinue) -and (Get-Command wsl -ErrorAction SilentlyContinue)){
  $keepWsl=Start-Process -FilePath wsl -ArgumentList @('-d',$WslDistro,'-u','root','--','sleep','infinity') -WindowStyle Hidden -PassThru
 }
 if($Build -or -not(Test-Path -LiteralPath (Join-Path $appRoot 'apps/web/dist/index.html'))){
  Push-Location (Join-Path $appRoot 'apps/web');try{if(-not(Test-Path node_modules)){& npm ci;if($LASTEXITCODE -ne 0){throw 'npm ci failed'}};& npm run build;if($LASTEXITCODE -ne 0){throw 'Frontend build failed'}}finally{Pop-Location}
 }
 $env:DEBUGYCH_WEB_PORT=[string]$Port;$env:DEBUGYCH_API_URL='http://127.0.0.1:8000'
 Write-Host "Opening production frontend at http://127.0.0.1:$Port/ . Press Ctrl+C to stop only this frontend."
 & node (Join-Path $PSScriptRoot 'serve-web.mjs')
}finally{if($keepWsl -and -not $keepWsl.HasExited){Stop-Process -Id $keepWsl.Id -ErrorAction SilentlyContinue}}
