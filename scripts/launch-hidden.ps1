$batch = Join-Path $PSScriptRoot 'launch.bat'
$log = Join-Path (Split-Path $PSScriptRoot -Parent) 'logs\launcher.log'
$arguments = '/d /c ""{0}" > "{1}" 2>&1"' -f $batch, $log
Start-Process -FilePath $env:ComSpec -ArgumentList $arguments -WindowStyle Hidden
