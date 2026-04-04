@echo off
REM ============================================================
REM  ARCG_CC — 起動スクリプト（コンソールあり・デバッグ用）
REM  このファイルを curve_fitter/ フォルダと同じ場所に置いて
REM  ダブルクリックするか、コマンドプロンプトから実行してください。
REM ============================================================

REM スクリプト自身があるフォルダに移動
cd /d "%~dp0"

REM Python が見つかるか確認
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python が見つかりません。
    echo Python 3.10 以上をインストールし、PATH に追加してください。
    pause
    exit /b 1
)

REM 必要パッケージの簡易チェック（初回のみ）
python -c "import PyQt6, matplotlib, numpy, scipy, ezdxf, pandas, yaml" >nul 2>&1
if errorlevel 1 (
    echo [INFO] 必要なパッケージをインストールします...
    pip install -r curve_fitter\requirements.txt
    pip install pyyaml
    if errorlevel 1 (
        echo [ERROR] パッケージのインストールに失敗しました。
        pause
        exit /b 1
    )
)

REM アプリ起動
python curve_fitter\main.py %*
if errorlevel 1 (
    echo [ERROR] アプリケーションがエラーで終了しました。
    pause
)
