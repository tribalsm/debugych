$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$context=Join-Path $root 'outputs/desktop11/pet-browser-context'
$pet=Join-Path $context 'pet'
New-Item -ItemType Directory -Force -Path $pet | Out-Null
foreach($name in @('web','tests/browser','evidence/v31')){
 $destination=Join-Path $pet $name
 New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
 & python -c 'import shutil,sys;shutil.copytree(sys.argv[1],sys.argv[2],dirs_exist_ok=True)' (Join-Path $root "apps/pet/$name") $destination
 if($LASTEXITCODE -ne 0){throw 'Cannot prepare browser context'}
}
Copy-Item -LiteralPath (Join-Path $root 'scripts/test-pet-browser.mjs') -Destination (Join-Path $pet 'run-browser.mjs')
Copy-Item -LiteralPath (Join-Path $root 'infra/desktop11-browser.Dockerfile') -Destination (Join-Path $context 'Dockerfile')
# Uses an existing trusted Playwright runtime; never changes other containers.
$linux=(& wsl -u root -- wslpath -a $context.Replace('\','/')).Trim()
& wsl -u root -- docker build --network none -t debugych-desktop11-browser:local $linux
if($LASTEXITCODE -ne 0){throw 'Browser image failed; requires cached debugych-integration-playwright:local'}
& wsl -u root -- docker run --rm --network none --shm-size 256m debugych-desktop11-browser:local
if($LASTEXITCODE -ne 0){throw 'Pet browser tests failed'}
