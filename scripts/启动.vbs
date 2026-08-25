Option Explicit

Dim shell, fso, scriptDir, rootDir, logDir, batchPath, launcherLog, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
rootDir = fso.GetParentFolderName(scriptDir)
logDir = fso.BuildPath(rootDir, "logs")
batchPath = fso.BuildPath(scriptDir, fso.GetBaseName(WScript.ScriptFullName) & ".bat")
launcherLog = fso.BuildPath(logDir, "launcher.log")

If Not fso.FolderExists(logDir) Then fso.CreateFolder(logDir)

command = "cmd.exe /d /c " & Chr(34) & Chr(34) & batchPath & Chr(34) & " > " & Chr(34) & launcherLog & Chr(34) & " 2>&1" & Chr(34)

' Window style 0 runs the normal launcher completely hidden.
shell.Run command, 0, False
