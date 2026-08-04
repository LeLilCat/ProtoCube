"""Crash-reporting entry point for the console-free ProtoCube launcher."""

from __future__ import annotations

import datetime as dt
import sys
import traceback
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
CRASH_LOG = PROJECT_DIR / "protocube_startup.log"


def write_crash_log(exception: BaseException | None = None) -> None:
    timestamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    if exception is None:
        details = traceback.format_exc()
    else:
        details = "".join(
            traceback.format_exception(type(exception), exception, exception.__traceback__)
        )
    report = (
        f"ProtoCube startup failure at {timestamp}\n"
        f"Python: {sys.executable}\n\n"
        f"{details}"
    )
    CRASH_LOG.write_text(report, encoding="utf-8")


def report_unhandled_exception(
    exception_type: type[BaseException],
    exception: BaseException,
    exception_traceback,
) -> None:
    del exception_type, exception_traceback
    write_crash_log(exception)
    if sys.__excepthook__ is not None:
        sys.__excepthook__(type(exception), exception, exception.__traceback__)


def main() -> int:
    sys.excepthook = report_unhandled_exception
    try:
        from main import main as run_protocube

        return run_protocube()
    except BaseException as error:
        write_crash_log()
        # A console launch should still expose the original traceback.
        if sys.stderr is not None:
            traceback.print_exception(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
