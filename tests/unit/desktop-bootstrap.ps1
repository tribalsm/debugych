# Fixture-only contract test: no real Docker, WSL, HTTP, or AI requests.
$ErrorActionPreference='Stop'
$script:starts=@();$script:projectQueries=@();$script:existing=$true;$script:runsc=$true;$script:compose=$null
function global:Invoke-RestMethod { throw 'Fixture offline' }
function global:docker {
 $DockerArgs=@($args)
 $global:LASTEXITCODE=0
 switch($DockerArgs[0]){
  'info' {if($DockerArgs[-1] -eq '{{.OSType}}'){'linux'}elseif($script:runsc){'{"runsc":{}}'}else{'{}'}}
  'ps' {if(-not $script:existing){return};if($DockerArgs -contains 'label=com.docker.compose.project=fixture'){$script:projectQueries+='fixture';($DockerArgs | Where-Object {$_ -like 'label=com.docker.compose.service=*'}).Split('=')[-1]}else{'api'}}
  'inspect' {'[{"HostConfig":{"PortBindings":{"8000/tcp":[{"HostIp":"127.0.0.1","HostPort":"8000"}]}},"Config":{"Labels":{"com.docker.compose.project":"fixture"}},"State":{"Health":{"Status":"healthy"}}}]'}
  'start' {$script:starts+=($DockerArgs[1..($DockerArgs.Count-1)] -join ',');'fixture started'}
  'compose' {$script:compose=$DockerArgs;'fixture compose started'}
  default {throw ('Unexpected fixture command: '+($DockerArgs -join '|'))}
 }
}
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$dir=Join-Path $root 'outputs/web-integration/bootstrap-fixture'
$source=Get-Content -Raw -LiteralPath (Join-Path $root 'scripts/ensure-backend.ps1')
$source=$source.Replace('exit 0','return').Replace('exit 1',"throw 'Bootstrap fixture failed'")
& ([scriptblock]::Create($source)) -BackendRoot $root -DataDir $dir -LogFile (Join-Path $dir 'fixture.log')
if(($script:starts -join '|') -ne 'postgres,redis|runner,supervisor|api|worker'){throw ('Incorrect startup order: '+($script:starts -join '|'))}
if($script:projectQueries.Count -ne 6){throw 'Every service must be scoped to the discovered owner project'}
'PASS: exact owner discovery, service order, existing-volume reuse; no real containers touched'
$script:existing=$false
& ([scriptblock]::Create($source)) -BackendRoot $root -DataDir $dir -LogFile (Join-Path $dir 'fixture.log')
if($script:compose -notcontains '--no-recreate' -or $script:compose -notcontains 'debugych-windows'){throw 'Fresh stack must use its own project without recreating existing containers'}
if(-not(Select-String -LiteralPath (Join-Path $dir 'backend.env') -Pattern '^LLM_API_KEY=$')){throw 'New environment must not contain a key'}
'PASS: new configured stack uses existing Compose and blank-key environment'
$script:runsc=$false;$script:compose=$null;$rejected=$false
try{& ([scriptblock]::Create($source)) -BackendRoot $root -DataDir $dir -LogFile (Join-Path $dir 'fixture.log')}catch{$rejected=$true}
if(-not $rejected -or $script:compose){throw 'Missing runsc must fail closed before starting Compose'}
'PASS: missing gVisor rejects startup; no unsafe runner fallback'
