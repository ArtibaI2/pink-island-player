Set WshShell = CreateObject("WScript.Shell")
dir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = dir
WshShell.Run "cmd /c start """" pythonw """ & dir & "\player_host.py""", 0, False
Set WshShell = Nothing
