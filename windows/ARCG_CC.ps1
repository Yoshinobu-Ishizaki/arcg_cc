# ============================================================
#  ARCG_CC — PowerShell 起動スクリプト兼ショートカット作成ツール
#
#  使い方:
#    1. 起動するだけ:
#       右クリック → "PowerShell で実行"
#
#    2. デスクトップにショートカットを作成:
#       PowerShell -ExecutionPolicy Bypass -File ARCG_CC.ps1 -CreateShortcut
# ============================================================

param(
    [switch]$CreateShortcut   # このスイッチを付けるとショートカット作成モード
)

# スクリプト自身のフォルダ
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$MainScript = Join-Path $ScriptDir "curve_fitter\main.py"
$IcoPath    = Join-Path $ScriptDir "arcg_cc.ico"

# ---- ショートカット作成モード ----
if ($CreateShortcut) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $LnkPath = Join-Path $Desktop "ARCG_CC.lnk"

    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($LnkPath)

    # pythonw で起動（コンソールなし）
    $PythonW = (Get-Command pythonw -ErrorAction SilentlyContinue)?.Source
    if (-not $PythonW) {
        $PythonW = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    }

    $Shortcut.TargetPath       = $PythonW
    $Shortcut.Arguments        = "`"$MainScript`""
    $Shortcut.WorkingDirectory = $ScriptDir
    $Shortcut.Description      = "ARCG_CC - G1連続セグメント近似ツール"
    $Shortcut.WindowStyle      = 7   # 最小化状態で起動（コンソールを隠す）

    if (Test-Path $IcoPath) {
        $Shortcut.IconLocation = "$IcoPath,0"
    }
    $Shortcut.Save()

    Write-Host "ショートカットを作成しました: $LnkPath" -ForegroundColor Green
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($WshShell) | Out-Null
    exit 0
}

# ---- 通常起動モード ----
Set-Location $ScriptDir

# Python チェック
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    [System.Windows.Forms.MessageBox]::Show(
        "Python が見つかりません。`nPython 3.10 以上をインストールしてください。",
        "ARCG_CC 起動エラー",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

# main.py 存在チェック
if (-not (Test-Path $MainScript)) {
    Write-Error "起動スクリプトが見つかりません: $MainScript"
    exit 1
}

# 起動（コンソールウィンドウを非表示にして pythonw で実行）
$PythonW = (Get-Command pythonw -ErrorAction SilentlyContinue)?.Source
if ($PythonW) {
    Start-Process -FilePath $PythonW -ArgumentList "`"$MainScript`"" `
        -WorkingDirectory $ScriptDir -WindowStyle Hidden
} else {
    # pythonw がない場合は python で起動
    Start-Process -FilePath $Python.Source -ArgumentList "`"$MainScript`"" `
        -WorkingDirectory $ScriptDir -WindowStyle Minimized
}
