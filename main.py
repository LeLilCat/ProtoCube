from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication 

from pet_window import ProtoCube


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ProtoCube Prototype")
    app.setQuitOnLastWindowClosed(True)

    pet = ProtoCube()
    app.aboutToQuit.connect(pet.shutdown)
    pet.show()
    pet.raise_()
    QTimer.singleShot(0, pet.force_window_visible)
    QTimer.singleShot(250, pet.force_window_visible)
    # Register only after Windows finishes creating and showing the HWND.
    QTimer.singleShot(500, pet.register_global_hotkey)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
