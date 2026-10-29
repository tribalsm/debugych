param([string]$Exe=(Join-Path $env:LOCALAPPDATA 'Дебагыч/Debugych.exe'))
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$output=Join-Path $root 'outputs/desktop12'
$Exe=(Resolve-Path -LiteralPath $Exe).Path
$results=@()
foreach($mode in @('remote','local')){
 $profile=Join-Path $output "native-profiles/$mode"
 New-Item -ItemType Directory -Force -Path $profile | Out-Null
 $api=if($mode -eq 'remote'){'https://debugych-release.invalid'}else{'http://127.0.0.1:8000'}
 @{mode=$mode;api_url=$api;backend_root='';pet_visible=$true;project_id=''} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $profile 'connection.json') -Encoding utf8
 # Windows PowerShell UTF8 adds BOM; serde_json expects ordinary UTF8.
 $config=Join-Path $profile 'connection.json'
 [IO.File]::WriteAllText($config,[IO.File]::ReadAllText($config),(New-Object Text.UTF8Encoding($false)))
 $start=New-Object Diagnostics.ProcessStartInfo
 $start.FileName=$Exe;$start.WorkingDirectory=$env:TEMP;$start.UseShellExecute=$false
 $start.EnvironmentVariables['DEBUGYCH_DESKTOP_PROFILE']=$profile
 $start.EnvironmentVariables['PATH']="$env:SystemRoot/System32;$env:SystemRoot"
 foreach($key in @('NODE_PATH','NODE_OPTIONS','PYTHONPATH','LLM_API_KEY')){$start.EnvironmentVariables.Remove($key)}
 $app=New-Object Diagnostics.Process;$app.StartInfo=$start
 if(-not $app.Start()){throw 'Could not launch installed test client'}
 $children=@{};$ready=$false
 try{
  for($attempt=0;$attempt -lt 24;$attempt++){
   if($app.HasExited){throw "Installed client exited during $mode smoke test"}
   foreach($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($app.Id)")){$children[$child.ProcessId]=$child.Name}
   $portFile=Join-Path $profile 'frontend-port.txt'
   if($mode -eq 'local' -and (Test-Path -LiteralPath $portFile)){
    $port=[IO.File]::ReadAllText($portFile).Trim()
    try{$page=Invoke-WebRequest "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 1;$ready=$page.StatusCode -eq 200}catch{}
   }
   Start-Sleep -Milliseconds 250
  }
  $serviceChildren=@($children.Values | Where-Object {$_ -in @('wsl.exe','docker.exe','powershell.exe','node.exe')})
  if($mode -eq 'remote' -and $serviceChildren.Count){throw 'Remote mode spawned a local service'}
  if($mode -eq 'local' -and -not $ready){throw 'Bundled frontend did not become ready without development tools in PATH'}
  $runtime=Get-Content -LiteralPath (Join-Path (Split-Path $Exe -Parent) 'native-runtime.json') -Raw | ConvertFrom-Json
  if($runtime.configDirectory -ne $profile){throw 'Wrong test profile'}
  $results+=@{mode=$mode;appPid=$app.Id;clientStayedAlive=$true;frontendReady=$ready;serviceChildren=$serviceChildren;profileMatches=$true;noDevelopmentToolsInChildPath=$true;sourceWorkingDirectory=$false;uiInteraction='NOT TESTED: Windows Computer Use helper unavailable';cleanup='Forced cleanup of this exact owned smoke-test process, not a graceful-exit check'}
 }finally{
  # Only the exact Process object created above. Never stop by name or stop shared services.
  if(-not $app.HasExited){$app.Kill();$app.WaitForExit()}
  for($cleanupAttempt=0;$cleanupAttempt -lt 50;$cleanupAttempt++){
   $remaining=@($children.Keys | Where-Object {Get-Process -Id $_ -ErrorAction SilentlyContinue});if(-not $remaining.Count){break};Start-Sleep -Milliseconds 100
  }
  if($remaining.Count){throw "Owned child cleanup incomplete: $($remaining -join ',')"}
  $app.Dispose()
 }
}
$results | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output 'installed-modes-smoke.json') -Encoding utf8
Write-Output 'PASS: installed Local/Remote process smoke; bundled runtime without Node/Python in PATH; no local services in Remote. Native interaction and clean VM are separate checks.'
