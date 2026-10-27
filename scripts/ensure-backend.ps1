param([string]$BackendRoot=$env:DEBUGYCH_BACKEND_ROOT,[string]$DataDir=$env:DEBUGYCH_DATA_DIR,[string]$LogFile=$env:DEBUGYCH_BOOT_LOG)
$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
function Invoke-Docker([Parameter(ValueFromRemainingArguments=$true)][string[]]$DockerArgs){
 if($script:nativeDocker){$output=& docker @DockerArgs 2>&1}else{$output=& wsl.exe -d Ubuntu -u root -- docker @DockerArgs 2>&1}
 if($LASTEXITCODE -ne 0){$output | Out-File -LiteralPath $LogFile -Append;throw 'Docker command failed. See the local startup log.'}
 return ($output -join "`n")
}
try{
 $h=$null;try{$h=Invoke-RestMethod http://127.0.0.1:8000/api/health -TimeoutSec 3}catch{}
 if($h.status -eq 'ok' -and $h.sandbox_available -eq $true -and $h.execution -eq 'gvisor-python'){exit 0}
 $script:nativeDocker=!!(Get-Command docker -ErrorAction SilentlyContinue)
 if(-not $script:nativeDocker){if(-not(Get-Command wsl.exe -ErrorAction SilentlyContinue)){throw 'Local mode requires WSL2 Ubuntu, Linux Docker and gVisor. Or configure an HTTPS backend.'}; & wsl.exe -d Ubuntu -u root -- systemctl start docker 2>&1 | Out-File -LiteralPath $LogFile -Append}
 $os=Invoke-Docker -DockerArgs @('info','--format','{{.OSType}}');$runtimes=(Invoke-Docker -DockerArgs @('info','--format','{{json .Runtimes}}')) | ConvertFrom-Json
 if($os.Trim() -ne 'linux' -or -not $runtimes.runsc){throw 'Linux Docker with registered gVisor/runsc is required. Unsafe runner fallback is disabled.'}
 # Reuse the exact existing stack owning local API port 8000, preserving volumes and secrets.
 $owner=$null
 $ids=(Invoke-Docker -DockerArgs @('ps','-a','--filter','label=com.docker.compose.service=api','--format','{{.ID}}')) -split "`n"
 foreach($id in $ids){if(-not $id.Trim()){continue};$item=((Invoke-Docker -DockerArgs @('inspect',$id.Trim())) | ConvertFrom-Json)[0];$bindings=$item.HostConfig.PortBindings.'8000/tcp';if($bindings | Where-Object {$_.HostPort -eq '8000' -and $_.HostIp -in @('127.0.0.1','')}){if($owner){throw 'Multiple backends own port 8000. Resolve the conflict in connection settings.'};$owner=$item.Config.Labels.'com.docker.compose.project'}}
 if($owner){
  foreach($services in @(@('postgres','redis'),@('runner','supervisor'),@('api'),@('worker'))){
   $names=@();foreach($service in $services){$found=Invoke-Docker -DockerArgs @('ps','-a','--filter',"label=com.docker.compose.project=$owner",'--filter',"label=com.docker.compose.service=$service",'--format','{{.ID}}');$names+=@($found -split "`n" | Where-Object {$_})}
   if($names.Count){Invoke-Docker -DockerArgs (@('start')+$names) | Out-File -LiteralPath $LogFile -Append}
   foreach($name in $names){for($i=0;$i -lt 45;$i++){$item=((Invoke-Docker -DockerArgs @('inspect',$name)) | ConvertFrom-Json)[0];if(-not $item.State.Health -or $item.State.Health.Status -eq 'healthy'){break};if($i -eq 44){throw 'A backend service did not become healthy. See the local startup log.'};Start-Sleep -Seconds 2}}
  }
 }else{
  $BackendRoot=(Resolve-Path -LiteralPath $BackendRoot).Path
  $envPath=Join-Path $DataDir 'backend.env';if(-not(Test-Path -LiteralPath $envPath)){Copy-Item -LiteralPath (Join-Path $BackendRoot '.env.example') -Destination $envPath}
  $composePath=Join-Path $BackendRoot 'docker-compose.yml'
  if(-not $script:nativeDocker){$composePath=(& wsl.exe -d Ubuntu -- wslpath -a $composePath).Trim();$envPath=(& wsl.exe -d Ubuntu -- wslpath -a $envPath).Trim()}
  Invoke-Docker -DockerArgs @('compose','-p','debugych-windows','--env-file',$envPath,'-f',$composePath,'up','-d','--no-recreate','--build','api','worker','runner','supervisor','postgres','redis') | Out-File -LiteralPath $LogFile -Append
 }
 exit 0
}catch{ $_.Exception.Message | Set-Content -LiteralPath (Join-Path $DataDir 'startup-error.txt');exit 1 }
