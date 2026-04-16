"""Entry point for the integrated Study Lens demo."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from launcher import Launcher


def main():
    app = QApplication(sys.argv)
    window = Launcher()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
