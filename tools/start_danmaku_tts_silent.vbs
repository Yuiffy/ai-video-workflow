Option Explicit

Dim fso, shell, scriptDir, repoRoot, configPath, configText
Dim match, found, runtime, pythonw, launcher, action, command

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
repoRoot = fso.GetParentFolderName(scriptDir)
configPath = fso.BuildPath(repoRoot, "config.json")
launcher = fso.BuildPath(scriptDir, "danmaku_tts_launcher.py")

If Not fso.FileExists(configPath) Then
    WScript.Quit 2
End If
If Not fso.FileExists(launcher) Then
    WScript.Quit 3
End If

configText = fso.OpenTextFile(configPath, 1, False, -2).ReadAll
Set match = New RegExp
match.Pattern = """runtime_python""\s*:\s*""([^""]+)"""
match.Global = False
If Not match.Test(configText) Then
    WScript.Quit 4
End If

Set found = match.Execute(configText)
runtime = Replace(found.Item(0).SubMatches.Item(0), "/", "\")
pythonw = fso.BuildPath(fso.GetParentFolderName(runtime), "pythonw.exe")
If Not fso.FileExists(pythonw) Then
    pythonw = runtime
End If
If Not fso.FileExists(pythonw) Then
    WScript.Quit 5
End If

action = "start"
If WScript.Arguments.Named.Exists("restart") Then action = "restart"
If WScript.Arguments.Named.Exists("stop") Then action = "stop"
If WScript.Arguments.Named.Exists("warm") Then action = "warm"
If WScript.Arguments.Named.Exists("status") Then action = "status"

command = """" & pythonw & """ """ & launcher & """ --action " & action
shell.Run command, 0, False
