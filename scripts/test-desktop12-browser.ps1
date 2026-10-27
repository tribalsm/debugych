$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$linux=(& wsl -u root -- wslpath -a $root.Replace('\','/')).Trim()
# Uses the cached trusted runtime built by test-desktop-pet-browser.ps1.
& wsl -u root -- docker run --rm --network none --shm-size 256m --entrypoint node -v "${linux}/tests/desktop12:/work/pet/tests/desktop12:ro" -v "${linux}/apps/desktop/shell:/work/pet/web/desktop-shell:ro" debugych-desktop11-browser:local node_modules/@playwright/test/cli.js test -c tests/desktop12/playwright.config.cjs
if($LASTEXITCODE -ne 0){throw 'Desktop 1.2 shell contract tests failed'}
