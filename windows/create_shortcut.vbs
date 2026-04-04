' ============================================================
'  ARCG_CC — デスクトップショートカット作成スクリプト
'
'  このスクリプトを実行すると、デスクトップに
'  アイコン付きの ARCG_CC ショートカットが作成されます。
'
'  使い方:
'    このファイルをダブルクリック → デスクトップにショートカット作成
' ============================================================

Option Explicit

Dim oShell, oFSO, oLink
Dim sDir, sVbs, sIco, sLnk, sDesc

Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")

' このスクリプトがある場所（= ARCG_CC.vbs と arcg_cc.ico がある場所）
sDir = oFSO.GetParentFolderName(WScript.ScriptFullName)
sVbs = sDir & "\ARCG_CC.vbs"
sIco = sDir & "\arcg_cc.ico"

' ---- 存在チェック ----
If Not oFSO.FileExists(sVbs) Then
    MsgBox "ARCG_CC.vbs が見つかりません:" & vbCrLf & sVbs, _
           vbCritical, "ショートカット作成エラー"
    WScript.Quit 1
End If

If Not oFSO.FileExists(sIco) Then
    MsgBox "arcg_cc.ico が見つかりません:" & vbCrLf & sIco & _
           vbCrLf & vbCrLf & "アイコンなしでショートカットを作成します。", _
           vbExclamation, "アイコン未検出"
    sIco = ""
End If

' ---- デスクトップにショートカットを作成 ----
sLnk = oShell.SpecialFolders("Desktop") & "\ARCG_CC.lnk"

Set oLink = oShell.CreateShortcut(sLnk)

' ターゲット: wscript.exe で .vbs を実行（コンソールなし起動）
oLink.TargetPath       = "wscript.exe"
oLink.Arguments        = """" & sVbs & """"
oLink.WorkingDirectory = sDir
oLink.Description      = "ARCG_CC — G1連続セグメント近似ツール"
oLink.WindowStyle      = 1   ' 通常ウィンドウ

If sIco <> "" Then
    oLink.IconLocation = sIco & ",0"
End If

oLink.Save

Set oLink  = Nothing
Set oShell = Nothing
Set oFSO   = Nothing

MsgBox "デスクトップに ARCG_CC ショートカットを作成しました。" & vbCrLf & _
       sLnk, vbInformation, "ARCG_CC セットアップ完了"
