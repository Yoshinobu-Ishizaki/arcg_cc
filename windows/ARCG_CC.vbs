' ============================================================
'  ARCG_CC — 起動スクリプト（コンソールなし・実用版）
'  このファイルを curve_fitter/ フォルダと同じ場所に置いて
'  ダブルクリックで起動できます。
' ============================================================

Option Explicit

Dim oShell, oFSO, sDir, sPython, sScript, sCmd

Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")

' スクリプト自身のフォルダを作業ディレクトリにする
sDir = oFSO.GetParentFolderName(WScript.ScriptFullName)
oShell.CurrentDirectory = sDir

' pythonw.exe（コンソールなし）を優先、なければ python.exe を使う
sPython = "pythonw"
On Error Resume Next
oShell.Run "pythonw --version", 0, True
If Err.Number <> 0 Then
    sPython = "python"
End If
On Error GoTo 0

' main.py のパス
sScript = sDir & "\curve_fitter\main.py"

If Not oFSO.FileExists(sScript) Then
    MsgBox "起動スクリプトが見つかりません:" & vbCrLf & sScript & _
           vbCrLf & vbCrLf & "curve_fitter フォルダと同じ場所にこのファイルを置いてください。", _
           vbCritical, "ARCG_CC 起動エラー"
    WScript.Quit 1
End If

' 起動コマンド（0 = 非表示ウィンドウ, False = 非同期）
sCmd = sPython & " """ & sScript & """"
oShell.Run sCmd, 0, False

Set oShell = Nothing
Set oFSO   = Nothing
