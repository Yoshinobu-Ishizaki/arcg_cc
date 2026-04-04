#Requires -Version 5.1
<#
.SYNOPSIS
    ARCG_CC インストーラ
.DESCRIPTION
    Python の確認・インストール、必要ライブラリのインストール、
    アプリファイルの配置、デスクトップショートカット作成を行います。
.NOTES
    実行方法:
        右クリック → "PowerShell で実行"
        または:
        powershell -ExecutionPolicy Bypass -File Install_ARCG_CC.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ============================================================
#  設定
# ============================================================
$AppName        = "ARCG_CC"
$AppVersion     = "1.0"
$AppDescription = "Arc & Curve G1 Continuous Curve Fitter"
$MinPythonMajor = 3
$MinPythonMinor = 10
$PythonInstallUrl = "https://www.python.org/downloads/"

$Packages = @(
    "PyQt6>=6.6",
    "matplotlib>=3.8",
    "numpy>=1.26",
    "scipy>=1.12",
    "ezdxf>=1.3",
    "pandas>=2.1",
    "pyyaml"
)

# インストーラ自身があるフォルダ = アプリのルートとみなす
$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$AppSourceDir = Join-Path $InstallerDir "curve_fitter"
$IcoPath      = Join-Path $InstallerDir "icons\arcg_cc.ico"
$LauncherVbs  = Join-Path $InstallerDir "windows\ARCG_CC.vbs"

# ============================================================
#  GUI ヘルパー（WinForms）
# ============================================================
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Show-Progress {
    param([string]$Title, [string]$Message, [int]$Percent)
    # 進捗はコンソールに出力（GUIプログレスバーは別スレッドが必要なため）
    $bar = "#" * [int]($Percent / 5)
    $sp  = " " * (20 - $bar.Length)
    Write-Host "`r  [$bar$sp] $Percent%  $Message" -NoNewline
}

function Show-MsgBox {
    param(
        [string]$Message,
        [string]$Title   = $AppName,
        [string]$Buttons = "OK",          # OK / OKCancel / YesNo / YesNoCancel
        [string]$Icon    = "Information"  # Information / Warning / Error / Question
    )
    $b = [System.Windows.Forms.MessageBoxButtons]::$Buttons
    $i = [System.Windows.Forms.MessageBoxIcon]::$Icon
    return [System.Windows.Forms.MessageBox]::Show($Message, $Title, $b, $i)
}

function Show-InstallDialog {
    <#
      インストール設定ダイアログを表示し、ユーザーの選択を返す。
      戻り値: [PSCustomObject] @{
          Proceed          = $true/$false
          InstallDir       = "C:\..."
          CreateShortcut   = $true/$false
          AddToStartMenu   = $true/$false
      }
    #>

    $form = New-Object System.Windows.Forms.Form
    $form.Text          = "$AppName $AppVersion セットアップ"
    $form.Size          = New-Object System.Drawing.Size(520, 440)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox   = $false
    $form.MinimizeBox   = $false

    # ---- アイコン ----
    if (Test-Path $IcoPath) {
        $form.Icon = New-Object System.Drawing.Icon($IcoPath)
    }

    # ---- タイトルバナー ----
    $banner = New-Object System.Windows.Forms.Panel
    $banner.Size      = New-Object System.Drawing.Size(520, 70)
    $banner.Location  = New-Object System.Drawing.Point(0, 0)
    $banner.BackColor = [System.Drawing.Color]::FromArgb(18, 36, 72)
    $form.Controls.Add($banner)

    $lblTitle = New-Object System.Windows.Forms.Label
    $lblTitle.Text      = "  $AppName $AppVersion"
    $lblTitle.Font      = New-Object System.Drawing.Font("Segoe UI", 18, [System.Drawing.FontStyle]::Bold)
    $lblTitle.ForeColor = [System.Drawing.Color]::White
    $lblTitle.Size      = New-Object System.Drawing.Size(340, 40)
    $lblTitle.Location  = New-Object System.Drawing.Point(10, 15)
    $banner.Controls.Add($lblTitle)

    $lblSub = New-Object System.Windows.Forms.Label
    $lblSub.Text      = "  $AppDescription"
    $lblSub.Font      = New-Object System.Drawing.Font("Segoe UI", 9)
    $lblSub.ForeColor = [System.Drawing.Color]::FromArgb(180, 210, 255)
    $lblSub.Size      = New-Object System.Drawing.Size(480, 20)
    $lblSub.Location  = New-Object System.Drawing.Point(10, 48)
    $banner.Controls.Add($lblSub)

    $y = 90

    # ---- インストール先 ----
    $lblDir = New-Object System.Windows.Forms.Label
    $lblDir.Text     = "インストール先フォルダ:"
    $lblDir.Location = New-Object System.Drawing.Point(20, $y)
    $lblDir.Size     = New-Object System.Drawing.Size(200, 20)
    $form.Controls.Add($lblDir)

    $y += 24
    $defaultInstDir = Join-Path ([Environment]::GetFolderPath("ProgramFiles")) $AppName
    $txtDir = New-Object System.Windows.Forms.TextBox
    $txtDir.Text     = $defaultInstDir
    $txtDir.Location = New-Object System.Drawing.Point(20, $y)
    $txtDir.Size     = New-Object System.Drawing.Size(380, 24)
    $form.Controls.Add($txtDir)

    $btnBrowse = New-Object System.Windows.Forms.Button
    $btnBrowse.Text     = "参照..."
    $btnBrowse.Location = New-Object System.Drawing.Point(410, ($y - 1))
    $btnBrowse.Size     = New-Object System.Drawing.Size(70, 26)
    $btnBrowse.Add_Click({
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description         = "インストール先フォルダを選択してください"
        $dlg.SelectedPath        = $txtDir.Text
        $dlg.ShowNewFolderButton = $true
        if ($dlg.ShowDialog() -eq "OK") {
            $txtDir.Text = $dlg.SelectedPath
        }
    })
    $form.Controls.Add($btnBrowse)

    $y += 40

    # ---- インストール内容（チェックリスト） ----
    $lblOpts = New-Object System.Windows.Forms.Label
    $lblOpts.Text     = "インストールオプション:"
    $lblOpts.Location = New-Object System.Drawing.Point(20, $y)
    $lblOpts.Size     = New-Object System.Drawing.Size(200, 20)
    $form.Controls.Add($lblOpts)

    $y += 26
    $chkPkgs = New-Object System.Windows.Forms.CheckBox
    $chkPkgs.Text     = "Python パッケージをインストール / 更新する  (PyQt6, matplotlib, numpy, scipy, ezdxf, pandas, pyyaml)"
    $chkPkgs.Location = New-Object System.Drawing.Point(30, $y)
    $chkPkgs.Size     = New-Object System.Drawing.Size(460, 36)
    $chkPkgs.Checked  = $true
    $chkPkgs.AutoSize = $false
    $form.Controls.Add($chkPkgs)

    $y += 44
    $chkShortcut = New-Object System.Windows.Forms.CheckBox
    $chkShortcut.Text     = "デスクトップにショートカットを作成する"
    $chkShortcut.Location = New-Object System.Drawing.Point(30, $y)
    $chkShortcut.Size     = New-Object System.Drawing.Size(400, 24)
    $chkShortcut.Checked  = $true
    $form.Controls.Add($chkShortcut)

    $y += 30
    $chkStartMenu = New-Object System.Windows.Forms.CheckBox
    $chkStartMenu.Text     = "スタートメニューに登録する"
    $chkStartMenu.Location = New-Object System.Drawing.Point(30, $y)
    $chkStartMenu.Size     = New-Object System.Drawing.Size(400, 24)
    $chkStartMenu.Checked  = $true
    $form.Controls.Add($chkStartMenu)

    $y += 40

    # ---- 区切り線 ----
    $sep = New-Object System.Windows.Forms.Label
    $sep.BorderStyle = "Fixed3D"
    $sep.Location    = New-Object System.Drawing.Point(10, $y)
    $sep.Size        = New-Object System.Drawing.Size(480, 2)
    $form.Controls.Add($sep)

    $y += 14

    # ---- ボタン ----
    $btnInstall = New-Object System.Windows.Forms.Button
    $btnInstall.Text          = "インストール"
    $btnInstall.Location      = New-Object System.Drawing.Point(300, $y)
    $btnInstall.Size          = New-Object System.Drawing.Size(100, 32)
    $btnInstall.DialogResult  = [System.Windows.Forms.DialogResult]::OK
    $btnInstall.BackColor     = [System.Drawing.Color]::FromArgb(18, 36, 72)
    $btnInstall.ForeColor     = [System.Drawing.Color]::White
    $btnInstall.FlatStyle     = "Flat"
    $form.Controls.Add($btnInstall)
    $form.AcceptButton = $btnInstall

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Text         = "キャンセル"
    $btnCancel.Location     = New-Object System.Drawing.Point(410, $y)
    $btnCancel.Size         = New-Object System.Drawing.Size(80, 32)
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.Controls.Add($btnCancel)
    $form.CancelButton = $btnCancel

    $result = $form.ShowDialog()

    return [PSCustomObject]@{
        Proceed        = ($result -eq [System.Windows.Forms.DialogResult]::OK)
        InstallDir     = $txtDir.Text
        InstallPkgs    = $chkPkgs.Checked
        CreateShortcut = $chkShortcut.Checked
        AddToStartMenu = $chkStartMenu.Checked
    }
}

# ============================================================
#  Python の確認
# ============================================================
function Get-PythonPath {
    # python / py ランチャーを探す
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $p = Get-Command $cmd -ErrorAction Stop
            $ver = & $p.Source --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -gt $MinPythonMajor -or
                    ($major -eq $MinPythonMajor -and $minor -ge $MinPythonMinor)) {
                    return $p.Source
                }
            }
        } catch {}
    }
    return $null
}

# ============================================================
#  メイン処理
# ============================================================

# --- 1. インストール設定ダイアログ ---
$cfg = Show-InstallDialog

if (-not $cfg.Proceed) {
    Write-Host "インストールをキャンセルしました。"
    exit 0
}

$InstallDir = $cfg.InstallDir

# コンソールウィンドウを表示
$host.UI.RawUI.WindowTitle = "ARCG_CC セットアップ"
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ARCG_CC $AppVersion インストール開始"       -ForegroundColor Cyan
Write-Host "  インストール先: $InstallDir"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# --- 2. Python チェック ---
Write-Host "[1/5] Python を確認しています..." -ForegroundColor Yellow
$pythonExe = Get-PythonPath

if (-not $pythonExe) {
    $ans = Show-MsgBox -Buttons "YesNo" -Icon "Warning" -Title "Python が見つかりません" -Message @"
Python $MinPythonMajor.$MinPythonMinor 以上が見つかりませんでした。

Python 公式サイトからインストールしてください:
$PythonInstallUrl

インストール時に「Add Python to PATH」にチェックを入れてください。

ブラウザで公式サイトを開きますか？
"@
    if ($ans -eq "Yes") {
        Start-Process $PythonInstallUrl
    }
    Write-Host "Python が見つからないためインストールを中断しました。" -ForegroundColor Red
    pause
    exit 1
}

$verStr = & $pythonExe --version 2>&1
Write-Host "  OK: $verStr ($pythonExe)" -ForegroundColor Green

# --- 3. アプリファイルのコピー ---
Write-Host ""
Write-Host "[2/5] アプリをコピーしています..." -ForegroundColor Yellow

try {
    # インストール先フォルダを作成
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }

    # curve_fitter フォルダをコピー
    $destApp = Join-Path $InstallDir "curve_fitter"
    if (Test-Path $destApp) {
        Remove-Item $destApp -Recurse -Force
    }
    Copy-Item -Path $AppSourceDir -Destination $destApp -Recurse -Force

    # アイコンをコピー
    $destIco = Join-Path $InstallDir "arcg_cc.ico"
    if (Test-Path $IcoPath) {
        Copy-Item -Path $IcoPath -Destination $destIco -Force
    }

    # 起動スクリプト（VBS）をコピー
    $destVbs = Join-Path $InstallDir "ARCG_CC.vbs"
    if (Test-Path $LauncherVbs) {
        Copy-Item -Path $LauncherVbs -Destination $destVbs -Force
    } else {
        # VBS が見つからない場合は生成
        $vbsContent = @'
Dim oShell, oFSO, sDir, sPython, sScript, sCmd
Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")
sDir = oFSO.GetParentFolderName(WScript.ScriptFullName)
oShell.CurrentDirectory = sDir
sPython = "pythonw"
sScript = sDir & "\curve_fitter\main.py"
If Not oFSO.FileExists(sScript) Then
    MsgBox "main.py が見つかりません: " & sScript, 16, "ARCG_CC"
    WScript.Quit 1
End If
sCmd = sPython & " """ & sScript & """"
oShell.Run sCmd, 0, False
'@
        Set-Content -Path $destVbs -Value $vbsContent -Encoding UTF8
    }

    Write-Host "  OK: $InstallDir" -ForegroundColor Green
} catch {
    Show-MsgBox -Icon "Error" -Message "ファイルのコピーに失敗しました:`n$($_.Exception.Message)"
    exit 1
}

# --- 4. パッケージインストール ---
if ($cfg.InstallPkgs) {
    Write-Host ""
    Write-Host "[3/5] Python パッケージをインストールしています..." -ForegroundColor Yellow
    Write-Host "  (初回は数分かかることがあります)"

    $pip = $pythonExe -replace "python(w?)\.exe$", "Scripts\pip.exe"
    if (-not (Test-Path $pip)) {
        $pip = "pip"
    }

    $total = $Packages.Count
    $i     = 0
    foreach ($pkg in $Packages) {
        $i++
        $pct = [int](($i / $total) * 100)
        Show-Progress -Title "パッケージインストール" -Message $pkg -Percent $pct
        try {
            & $pythonExe -m pip install --upgrade $pkg --quiet 2>&1 | Out-Null
        } catch {
            Write-Host ""
            Write-Host "  警告: $pkg のインストールに失敗しました: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    Write-Host ""
    Write-Host "  OK: 全パッケージのインストール完了" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[3/5] パッケージインストール: スキップ" -ForegroundColor DarkGray
}

# --- 5. デスクトップショートカット ---
Write-Host ""
Write-Host "[4/5] ショートカットを作成しています..." -ForegroundColor Yellow

$destVbs  = Join-Path $InstallDir "ARCG_CC.vbs"
$destIco  = Join-Path $InstallDir "arcg_cc.ico"
$wshShell = New-Object -ComObject WScript.Shell

function New-Shortcut {
    param([string]$LnkPath, [string]$TargetVbs, [string]$IcoFile, [string]$Desc)
    $lnk = $wshShell.CreateShortcut($LnkPath)
    $lnk.TargetPath       = "wscript.exe"
    $lnk.Arguments        = "`"$TargetVbs`""
    $lnk.WorkingDirectory = $InstallDir
    $lnk.Description      = $Desc
    $lnk.WindowStyle      = 1
    if (Test-Path $IcoFile) { $lnk.IconLocation = "$IcoFile,0" }
    $lnk.Save()
}

if ($cfg.CreateShortcut) {
    $desktop = $wshShell.SpecialFolders("Desktop")
    $lnkPath = Join-Path $desktop "ARCG_CC.lnk"
    New-Shortcut -LnkPath $lnkPath -TargetVbs $destVbs -IcoFile $destIco `
                 -Desc $AppDescription
    Write-Host "  OK: デスクトップ ← $lnkPath" -ForegroundColor Green
}

if ($cfg.AddToStartMenu) {
    $startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) $AppName
    if (-not (Test-Path $startMenu)) {
        New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
    }
    $lnkPath = Join-Path $startMenu "ARCG_CC.lnk"
    New-Shortcut -LnkPath $lnkPath -TargetVbs $destVbs -IcoFile $destIco `
                 -Desc $AppDescription
    Write-Host "  OK: スタートメニュー ← $lnkPath" -ForegroundColor Green
}

[System.Runtime.InteropServices.Marshal]::ReleaseComObject($wshShell) | Out-Null

# --- 6. アンインストーラ生成 ---
Write-Host ""
Write-Host "[5/5] アンインストーラを生成しています..." -ForegroundColor Yellow

$uninstScript = @"
# ARCG_CC アンインストーラ
`$InstallDir = "$InstallDir"
`$AppName    = "$AppName"
Add-Type -AssemblyName System.Windows.Forms
`$ans = [System.Windows.Forms.MessageBox]::Show(
    "`$AppName をアンインストールしますか?`n`n`$InstallDir",
    "`$AppName アンインストール",
    [System.Windows.Forms.MessageBoxButtons]::YesNo,
    [System.Windows.Forms.MessageBoxIcon]::Question
)
if (`$ans -ne "Yes") { exit 0 }

# デスクトップ・スタートメニューのショートカットを削除
`$wsh = New-Object -ComObject WScript.Shell
foreach (`$loc in @(`$wsh.SpecialFolders("Desktop"),
                    (Join-Path ([Environment]::GetFolderPath("Programs")) "`$AppName"))) {
    `$lnk = Join-Path `$loc "ARCG_CC.lnk"
    if (Test-Path `$lnk) { Remove-Item `$lnk -Force }
}
# インストールフォルダを削除
if (Test-Path `$InstallDir) { Remove-Item `$InstallDir -Recurse -Force }
[System.Windows.Forms.MessageBox]::Show("アンインストールが完了しました。", "`$AppName")
"@
$uninstPath = Join-Path $InstallDir "Uninstall_ARCG_CC.ps1"
Set-Content -Path $uninstPath -Value $uninstScript -Encoding UTF8
Write-Host "  OK: $uninstPath" -ForegroundColor Green

# ============================================================
#  完了
# ============================================================
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ARCG_CC のインストールが完了しました！"    -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

$msg = "ARCG_CC $AppVersion のインストールが完了しました。`n`nインストール先: $InstallDir"
if ($cfg.CreateShortcut) { $msg += "`n`nデスクトップのショートカットからすぐに起動できます。" }
$msg += "`n`n今すぐ起動しますか？"

$ans = Show-MsgBox -Buttons "YesNo" -Icon "Information" -Message $msg -Title "インストール完了"
if ($ans -eq "Yes") {
    $destVbs = Join-Path $InstallDir "ARCG_CC.vbs"
    if (Test-Path $destVbs) {
        Start-Process "wscript.exe" -ArgumentList "`"$destVbs`""
    }
}
