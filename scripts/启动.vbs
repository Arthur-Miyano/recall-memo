Option Explicit

Dim shell, fso, scriptDir, rootDir, logDir, batchPath, launcherLog, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
rootDir = fso.GetParentFolderName(scriptDir)
logDir = fso.BuildPath(rootDir, "logs")
' 始终调用 ASCII 名称的入口，避开 Windows 命令解释器的代码页问题。
batchPath = fso.BuildPath(scriptDir, "launch.bat")

If Not fso.FolderExists(logDir) Then fso.CreateFolder(logDir)
launcherLog = fso.BuildPath(logDir, "launcher.log")

' Do not wait here: the batch script starts a background server of its own.
shell.CurrentDirectory = scriptDir
command = "cmd.exe /d /c " & Chr(34) & Chr(34) & batchPath & Chr(34) & " > " & Chr(34) & launcherLog & Chr(34) & " 2>&1" & Chr(34)
shell.Run command, 0, False
