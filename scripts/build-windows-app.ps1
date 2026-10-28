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
 $desktopConfig=Get-Content apps/desktop/tauri.conf.json -Raw -Encoding UTF8 | ConvertFrom-Json
 $targetRoot=if($env:CARGO_TARGET_DIR){$env:CARGO_TARGET_DIR}else{Join-Path $root 'apps/desktop/target'}
 Copy-Item (Join-Path $targetRoot 'release/debugych-desktop.exe') (Join-Path $targetRoot 'release/Debugych.exe') -Force
 $taskOriginalPath=$env:Path;$env:Path="$env:USERPROFILE/.cargo/bin;$env:Path"
 Push-Location apps/desktop
 try{ & npm exec -- tauri bundle --bundles nsis --config tauri.release.conf.json --no-sign --no-binary-patching; if($LASTEXITCODE -ne 0){throw 'Installer build failed'} }finally{Pop-Location;$env:Path=$taskOriginalPath}
 Copy-Item -LiteralPath (Join-Path $targetRoot ('release/bundle/nsis/'+$desktopConfig.productName+'_'+$desktopConfig.version+'_x64-setup.exe')) -Destination (Join-Path $root ('outputs/Debugych-Desktop-'+$desktopConfig.version+'-Setup.exe')) -Force
 & python scripts/package-desktop-sources.py;if($LASTEXITCODE -ne 0){throw 'Source archive failed'}
}finally{Pop-Location}
