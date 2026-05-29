from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from app.core.config_loader import load_config
from app.core.logger import setup_logging
from app.ui.main_window import MainWindow


def main() -> int:
    config_path = Path(__file__).resolve().parent / "config" / "default.yaml"
    config = load_config(str(config_path))
    logger = setup_logging(config)

    app = QApplication(sys.argv)
    window = MainWindow(config=config, logger=logger)
    window.show()

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
