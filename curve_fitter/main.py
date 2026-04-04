"""
エントリポイント

Usage:
    python main.py
    python -m curve_fitter  (パッケージとして配置した場合)
"""
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from curve_fitter.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("曲線フィッター")

    # High-DPI 対応（PyQt6 はデフォルト有効だが明示）
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
