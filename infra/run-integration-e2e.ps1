# Only the debugych-integration preview and its disposable trusted UI harness.
$ErrorActionPreference = 'Stop'
$integrationRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$linuxRoot = (& wsl -u root -e wslpath -a -u $integrationRoot).Trim()
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$runId = [guid]::NewGuid().ToString('N').Substring(0,12)
$contextPath = Join-Path $integrationRoot ('outputs/integration/e2e-image-'+$runId)
$linuxContext = (& wsl -u root -e wslpath -a -u $contextPath).Trim()
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
New-Item -ItemType Directory -Force $contextPath | Out-Null
# Copies are bounded to our lockfile-installed libraries; no user credentials.
foreach ($pair in @(@('axe-core','axe-core'),@('@axe-core/playwright','axe-playwright'),@('lucide-react','lucide-react'))) {
  $destination = Join-Path $contextPath $pair[1]
  if (-not (Test-Path $destination)) {
    Copy-Item -LiteralPath (Join-Path $integrationRoot ('apps/web/node_modules/'+$pair[0])) -Destination $destination -Recurse
  }
}
& wsl -u root --cd $linuxRoot -e docker build -f infra/integration-e2e.Dockerfile -t debugych-integration-e2e:local $linuxContext
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$qaName = 'debugych-integration-e2e-' + $runId
$qaVolume = $qaName + '-outputs'
$qaArguments = @('run','--name',$qaName,'--network','debugych-integration_backend',
  '--user','10000:10000','--cap-drop','ALL','--security-opt','no-new-privileges:true',
  '--read-only','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=256m,mode=1777',
  '--memory','1g','--cpus','1','--pids-limit','256',
  '--mount',"type=bind,source=$linuxRoot/tests,target=/work/tests,readonly",
  '--mount',"type=bind,source=$linuxRoot/evaluation,target=/work/evaluation,readonly",
  '--mount',"type=bind,source=$linuxRoot/demo,target=/work/demo,readonly",
  '--mount',"type=bind,source=$linuxRoot/apps/web/playwright.config.ts,target=/work/apps/web/playwright.config.ts,readonly",
  '--mount',"type=bind,source=$linuxRoot/apps/web/src,target=/work/apps/web/src,readonly",
  '--mount',"type=volume,source=$qaVolume,target=/work/outputs",
  '-e','PLAYWRIGHT_BASE_URL=http://web:8080','-e','COMPOSE_CONTRACT_TEST=1',
  '-e','PLAYWRIGHT_BROWSERS_PATH=/opt/browsers','-e','HOME=/tmp',
  '-e','PLAYWRIGHT_JSON_OUTPUT_NAME=../../outputs/integration/browser-linux-results.json',
  '-e','PLAYWRIGHT_HTML_REPORT=../../outputs/integration/browser-linux-report',
  '-e','PLAYWRIGHT_HTML_OPEN=never',
  'debugych-integration-e2e:local','test','--config','/work/apps/web/playwright.config.ts',
  '--output','../../outputs/integration/browser-linux-artifacts','--reporter=list,json,html')
& wsl -u root -e docker @qaArguments
$testExit = $LASTEXITCODE
# Export only after execution. Node copyfile/trace operations stay on Linux FS.
& wsl -u root -e docker cp "${qaName}:/work/outputs/." "$linuxRoot/outputs/"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& wsl -u root -e docker rm $qaName
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Keep the uniquely named volume as additional local evidence, never prune.
exit $testExit
