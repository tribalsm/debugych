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
 Copy-Item apps/desktop/target/release/debugych-desktop.exe apps/desktop/target/release/Debugych.exe -Force
 $taskOriginalPath=$env:Path;$env:Path="$env:USERPROFILE/.cargo/bin;$env:Path"
 Push-Location apps/desktop
 try{ & npm exec -- tauri bundle --bundles nsis --config tauri.release.conf.json --no-sign --no-binary-patching; if($LASTEXITCODE -ne 0){throw 'Installer build failed'} }finally{Pop-Location;$env:Path=$taskOriginalPath}
 Copy-Item -LiteralPath 'apps/desktop/target/release/bundle/nsis/Дебагыч_1.2.0_x64-setup.exe' -Destination 'outputs/Debugych-Desktop-1.2.0-Setup.exe' -Force
 & python scripts/package-desktop-sources.py;if($LASTEXITCODE -ne 0){throw 'Source archive failed'}
}finally{Pop-Location}
