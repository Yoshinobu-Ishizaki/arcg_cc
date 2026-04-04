; ============================================================
;  ARCG_CC Inno Setup スクリプト
;  Windows マシンで Inno Setup をインストール後、
;  このファイルを右クリック → "Compile" で .exe インストーラが生成されます。
;
;  Inno Setup: https://jrsoftware.org/isinfo.php
; ============================================================

#define AppName      "ARCG_CC"
#define AppVersion   "1.0"
#define AppDesc      "Arc & Curve G1 Continuous Curve Fitter"
#define AppPublisher "Your Organization"
#define AppExeName   "ARCG_CC.vbs"
#define AppIcon      "icons\arcg_cc.ico"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisherURL=https://example.com
AppSupportURL=https://example.com
AppUpdatesURL=https://example.com
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=.\installer_output
OutputBaseFilename=Install_ARCG_CC_{#AppVersion}
SetupIconFile={#AppIcon}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardResizable=no
; 管理者権限（インストール先が ProgramFiles のため）
PrivilegesRequired=admin
; 32/64 ビット両対応
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon";    Description: "デスクトップにショートカットを作成する"; GroupDescription: "追加タスク:"; Flags: checked
Name: "startmenuicon";  Description: "スタートメニューに登録する";             GroupDescription: "追加タスク:"; Flags: checked
Name: "installpkgs";    Description: "Python パッケージをインストール / 更新する (PyQt6, matplotlib 等)"; GroupDescription: "追加タスク:"; Flags: checked

[Files]
; アプリ本体
Source: "curve_fitter\*"; DestDir: "{app}\curve_fitter"; Flags: ignoreversion recursesubdirs createallsubdirs
; アイコン
Source: "icons\arcg_cc.ico"; DestDir: "{app}"; Flags: ignoreversion
; 起動スクリプト
Source: "windows\ARCG_CC.vbs";          DestDir: "{app}"; Flags: ignoreversion
Source: "windows\ARCG_CC_debug.bat";    DestDir: "{app}"; Flags: ignoreversion
Source: "windows\ARCG_CC.ps1";          DestDir: "{app}"; Flags: ignoreversion

[Icons]
; デスクトップ
Name: "{autodesktop}\{#AppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\ARCG_CC.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\arcg_cc.ico"; Comment: "{#AppDesc}"; Tasks: desktopicon
; スタートメニュー
Name: "{group}\{#AppName}";       Filename: "{sys}\wscript.exe"; Parameters: """{app}\ARCG_CC.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\arcg_cc.ico"; Comment: "{#AppDesc}"; Tasks: startmenuicon
Name: "{group}\アンインストール";  Filename: "{uninstallexe}"

[Run]
; Python パッケージインストール（タスクが選択された場合のみ）
Filename: "{cmd}"; Parameters: "/c python -m pip install --upgrade PyQt6>=6.6 matplotlib>=3.8 numpy>=1.26 scipy>=1.12 ezdxf>=1.3 pandas>=2.1 pyyaml"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; Tasks: installpkgs; StatusMsg: "Python パッケージをインストールしています..."
; インストール後に起動するか確認
Filename: "{sys}\wscript.exe"; Parameters: """{app}\ARCG_CC.vbs"""; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent; Description: "ARCG_CC を今すぐ起動する"

[UninstallRun]
; アンインストール時はショートカットも削除（Inno Setup が自動処理）

[Code]
// Python がインストールされているか確認するカスタムページ
var
  PythonFound: Boolean;
  PythonPath:  String;

function FindPython(): Boolean;
var
  TestPaths: TArrayOfString;
  i: Integer;
  ExitCode: Integer;
  PyVer: String;
begin
  Result := False;

  // PATH から python.exe を探す
  if RegQueryStringValue(HKEY_CURRENT_USER,
      'SOFTWARE\Python\PythonCore', 'InstallPath', PythonPath) then begin
    PythonPath := AddBackslash(PythonPath) + 'python.exe';
    if FileExists(PythonPath) then begin
      Result := True;
      Exit;
    end;
  end;

  // 一般的なパスを探索
  SetArrayLength(TestPaths, 4);
  TestPaths[0] := ExpandConstant('{pf}\Python312\python.exe');
  TestPaths[1] := ExpandConstant('{pf}\Python311\python.exe');
  TestPaths[2] := ExpandConstant('{pf}\Python310\python.exe');
  TestPaths[3] := GetEnv('LOCALAPPDATA') + '\Programs\Python\Python312\python.exe';

  for i := 0 to GetArrayLength(TestPaths)-1 do begin
    if FileExists(TestPaths[i]) then begin
      PythonPath := TestPaths[i];
      Result := True;
      Exit;
    end;
  end;
end;

procedure InitializeWizard();
begin
  PythonFound := FindPython();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpWelcome then begin
    if not PythonFound then begin
      if MsgBox('Python 3.10 以上が見つかりませんでした。' + #13#10 +
                'Python なしでもファイルはコピーされますが、' + #13#10 +
                'アプリを起動するには Python のインストールが必要です。' + #13#10 + #13#10 +
                'インストールを続けますか？',
                mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
    end;
  end;
end;
