$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try{
 & npm --prefix apps/pet run build;if($LASTEXITCODE -ne 0){throw "Pet build failed"}
 & python scripts/prepare-desktop.py;if($LASTEXITCODE -ne 0){throw "Pet embedding failed"}
 & npm --prefix apps/web run build;if($LASTEXITCODE -ne 0){throw 'Frontend build failed'}
 $cargo=Join-Path $env:USERPROFILE '.cargo/bin/cargo.exe'
 & $cargo test --locked --manifest-path apps/desktop/Cargo.toml;if($LASTEXITCODE -ne 0){throw 'Native tests failed'}
 & $cargo build --locked --release --manifest-path apps/desktop/Cargo.toml;if($LASTEXITCODE -ne 0){throw 'Native build failed'}
 & python scripts/package-windows-app.py;if($LASTEXITCODE -ne 0){throw 'Packaging failed'}
}finally{Pop-Location}
