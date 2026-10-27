$ErrorActionPreference='Stop'
$exe=Join-Path $PSScriptRoot 'Debugych.exe'
if(!(Test-Path -LiteralPath $exe)){throw 'Распакуйте полный пакет: Debugych.exe должен находиться рядом со скриптом.'}
$link=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Дебагыч Desktop 1.1.lnk'
$shell=New-Object -ComObject WScript.Shell
if(Test-Path -LiteralPath $link){
 $existing=$shell.CreateShortcut($link)
 if($existing.TargetPath -ne $exe){throw "Ярлык уже указывает на другую папку. Удалите или переименуйте его самостоятельно: $link"}
}
$shortcut=$shell.CreateShortcut($link)
$shortcut.TargetPath=$exe
$shortcut.WorkingDirectory=$PSScriptRoot
$shortcut.IconLocation="$exe,0"
$shortcut.Save()
Write-Output $link
