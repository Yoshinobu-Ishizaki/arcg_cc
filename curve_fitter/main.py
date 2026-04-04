"""
エントリポイント

Usage:
    python main.py
    python -m curve_fitter  (パッケージとして配置した場合)
"""
import sys
import os
# Ensure the project root is on sys.path so `curve_fitter` is importable
# whether this file is run directly or via `uv run python main.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from curve_fitter.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("曲線フィッター")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
