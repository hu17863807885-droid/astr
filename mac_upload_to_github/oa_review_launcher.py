from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from oa_review_gui import main as review_main


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def has_default_dataset(path: Path) -> bool:
    return (path / "vis_table.csv").is_file() and (path / "annotation_check_triplets").is_dir()


def default_data_dir(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if has_default_dataset(candidate):
            return candidate
    return start


def show_error(title: str, message: str) -> None:
    try:
        from tkinter import Tk, messagebox

        root = Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        print(f"{title}: {message}", file=sys.stderr)


def main() -> int:
    base_dir = default_data_dir(app_dir())
    os.chdir(base_dir)

    if len(sys.argv) > 1:
        args = sys.argv[1:]
    else:
        catalog = base_dir / "vis_table.csv"
        triplets = base_dir / "annotation_check_triplets"
        if not catalog.is_file() or not triplets.is_dir():
            show_error(
                "OA Review",
                "vis_table.csv or annotation_check_triplets was not found.\n\n"
                "Put OA_Review.exe or OA_Review.app inside a cluster directory, for example:\n"
                r"Windows: E:\Astronaut_OA\Abell370" "\n"
                "macOS: /Users/you/Astronaut_OA/Abell370",
            )
            return 1
        args = ["-path_cat", str(catalog), "-plot_dir", str(triplets), "-id", "reviewer", "-win", "500"]

    try:
        review_main(args)
    except Exception as exc:
        log_path = base_dir / "oa_review_error.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        show_error("OA Review", f"{exc}\n\nDetailed error was written to:\n{log_path}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
