# ARCG_CC Windows 起動ファイル

## フォルダ構成

```
（任意のフォルダ）/
├── arcg_cc.ico          ← アイコン
├── ARCG_CC.vbs          ← ダブルクリック起動（実用版・コンソールなし）★推奨
├── ARCG_CC.bat          ← バッチ起動（デバッグ用・コンソールあり）
├── ARCG_CC.ps1          ← PowerShell 起動 + ショートカット作成
├── create_shortcut.vbs  ← デスクトップショートカット作成スクリプト
└── curve_fitter/        ← アプリ本体（main.py が入っているフォルダ）
    ├── main.py
    ├── requirements.txt
    ├── core/
    └── ui/
```

---

## セットアップ手順

### 1. 必要パッケージのインストール

```cmd
pip install -r curve_fitter\requirements.txt
pip install pyyaml
```

### 2. 起動方法（3 通り）

#### A. VBScript（推奨 — コンソールなし）
`ARCG_CC.vbs` をダブルクリック

#### B. バッチファイル（デバッグ用 — コンソールあり）
`ARCG_CC_debug.bat` をダブルクリック  
エラーが出た場合はコンソールにメッセージが表示されます。

#### C. PowerShell
```powershell
# 実行ポリシーを一時的に緩めて起動
powershell -ExecutionPolicy Bypass -File ARCG_CC.ps1
```

---

## デスクトップにアイコン付きショートカットを作成する

### 方法 A（VBScript）
`create_shortcut.vbs` をダブルクリック  
→ デスクトップに `ARCG_CC.lnk` が作成されます。

### 方法 B（PowerShell）
```powershell
powershell -ExecutionPolicy Bypass -File ARCG_CC.ps1 -CreateShortcut
```

---

## 動作要件

| 項目 | 要件 |
|------|------|
| OS | Windows 10 / 11 |
| Python | 3.10 以上（PATH に追加済みであること） |
| 主要パッケージ | PyQt6, matplotlib, numpy, scipy, ezdxf, pandas, pyyaml |

---

## トラブルシューティング

**「Python が見つかりません」**  
→ Python 公式サイトからインストールし、インストーラの「Add Python to PATH」にチェックを入れてください。

**「ModuleNotFoundError」**  
→ `ARCG_CC_debug.bat` で起動してエラー内容を確認し、不足パッケージを `pip install` してください。

**「このアプリを実行すると…」とセキュリティダイアログが出る**  
→ `.vbs` / `.ps1` は署名なしのため Windows Defender SmartScreen の警告が出ることがあります。「詳細情報」→「実行」で起動できます。
