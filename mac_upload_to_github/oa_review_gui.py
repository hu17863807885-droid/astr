from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageTk

try:
    from tkinter import Button, Canvas, Entry, Frame, Label, Menu, Scale, Scrollbar, Tk, messagebox
except ImportError:  # pragma: no cover - Python 2 compatibility for the source app.
    from Tkinter import Button, Canvas, Entry, Frame, Label, Menu, Scale, Scrollbar, Tk
    import tkMessageBox as messagebox


DISPLAY_FIELDS = (
    ("id", "ID"),
    ("ra", "RA"),
    ("dec", "Dec"),
    ("redshift", "Redshift"),
    ("rms", "RMS"),
    ("catalogue", "Catalogue"),
)

METADATA_ALIASES = {
    "id": ("id", "patch_id", "table_id"),
    "ra": ("ra",),
    "dec": ("dec", "declination"),
    "redshift": ("redshift", "z", "sysz"),
    "rms": ("rms",),
    "catalogue": ("catalogue", "catalog", "quality", "class"),
}

FLAG_COLUMNS = (
    "ring",
    "interesting",
    "recenter",
    "incomplete_labeling",
    "over_annotation",
    "under_annotation",
    "accurate_annotation",
)

CSV_FIELDNAMES = [
    "index",
    "table_id",
    "id",
    "ra",
    "dec",
    "redshift",
    "rms",
    "catalogue",
    "comment",
    "has_image_comment",
    "visuScore",
    "ring",
    "interesting",
    "recenter",
    "incomplete_labeling",
    "over_annotation",
    "under_annotation",
    "accurate_annotation",
    "image_file",
]


@dataclass
class Candidate:
    index: int
    patch_id: str
    object_id: str
    image_path: Path
    metadata: dict[str, str]


def _field_names(table: Any) -> list[str]:
    return list(getattr(table, "names", None) or table.columns.names)


def _field(table: Any, row: Any, names: dict[str, str], requested: str, fallback_index: int | None = None) -> Any:
    key = requested.lower()
    if key in names:
        return row[names[key]]
    if fallback_index is not None:
        return row[fallback_index]
    return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    return str(value).strip()


def _patch_id_from_object_id(object_id: str) -> str:
    name = Path(object_id).name
    stem = Path(name).stem
    if stem.endswith("_triplet"):
        stem = stem[: -len("_triplet")]
    return stem


def _metadata_from_values(values: dict[str, Any], patch_id: str) -> dict[str, str]:
    lowered = {key.lower(): value for key, value in values.items() if key}
    metadata: dict[str, str] = {}
    for output_key, aliases in METADATA_ALIASES.items():
        for alias in aliases:
            value = _as_text(lowered.get(alias))
            if value:
                metadata[output_key] = value
                break
        else:
            metadata[output_key] = ""

    if not metadata["id"]:
        metadata["id"] = patch_id
    return metadata


def _load_fits_candidates(catalog_path: Path, plot_dir: Path) -> list[Candidate]:
    from astropy.io import fits

    with fits.open(catalog_path) as hdul:
        table = hdul[1].data
        names = {name.lower(): name for name in _field_names(table)}
        candidates: list[Candidate] = []

        for row_index, row in enumerate(table, start=1):
            object_id = _as_text(_field(table, row, names, "object_id", 1))
            if not object_id:
                continue

            patch_id = _as_text(_field(table, row, names, "patch_id"))
            if not patch_id:
                patch_id = _patch_id_from_object_id(object_id)

            image_path = plot_dir / object_id
            if not image_path.is_file():
                folder_id = _as_text(_field(table, row, names, "folder_id"))
                if folder_id:
                    candidate_path = catalog_path.parent / folder_id / object_id
                    if candidate_path.is_file():
                        image_path = candidate_path

            if image_path.is_file():
                values = {name: _as_text(row[name]) for name in _field_names(table)}
                candidates.append(Candidate(row_index, patch_id, object_id, image_path, _metadata_from_values(values, patch_id)))

    return candidates


def _load_csv_candidates(catalog_path: Path, plot_dir: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    with catalog_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=1):
            object_id = _as_text(row.get("object_id"))
            if not object_id:
                continue
            patch_id = _as_text(row.get("patch_id")) or _patch_id_from_object_id(object_id)

            image_path = plot_dir / object_id
            folder_id = _as_text(row.get("folder_id"))
            if not image_path.is_file() and folder_id:
                candidate_path = catalog_path.parent / folder_id / object_id
                if candidate_path.is_file():
                    image_path = candidate_path

            if image_path.is_file():
                candidates.append(Candidate(row_index, patch_id, object_id, image_path, _metadata_from_values(row, patch_id)))
    return candidates


def load_candidates(catalog_path: Path, plot_dir: Path) -> list[Candidate]:
    if catalog_path.suffix.lower() in {".fits", ".fit", ".fts"}:
        return _load_fits_candidates(catalog_path, plot_dir)
    return _load_csv_candidates(catalog_path, plot_dir)


class ReviewApp:
    def __init__(
        self,
        candidates: list[Candidate],
        classifier: str,
        start_index: int,
        win_height: int,
        output_dir: Path,
        resume: bool = True,
    ):
        if not candidates:
            raise ValueError("No displayable images were found for the catalog.")
        if start_index < 1 or start_index > len(candidates):
            raise ValueError(f"Start index must be between 1 and {len(candidates)}.")

        self.candidates = candidates
        self.classifier = classifier or "None"
        self.start_index = start_index
        self.counter = start_index - 1
        self.win_height = win_height
        self.output_dir = output_dir
        self.records_by_index: dict[int, dict[str, Any]] = {}
        self.current_flags = {name: 0 for name in FLAG_COLUMNS}
        self.flag_buttons: dict[str, Button] = {}
        self.current_image: Image.Image | None = None
        self.drawing_overlay: Image.Image | None = None
        self.current_candidate: Candidate | None = None
        self.resize_after_id: str | None = None
        self.comment_after_id: str | None = None
        self.drawing_after_id: str | None = None
        self.geometry_initialized = False
        self.zoom_scale = 1.0
        self.rendered_width = 0
        self.rendered_height = 0
        self.image_origin_x = 0.0
        self.image_origin_y = 0.0
        self.h_scroll_visible = False
        self.v_scroll_visible = False
        self.draw_mode: str | None = None
        self.draw_buttons: dict[str, Button] = {}
        self.last_draw_point: tuple[int, int] | None = None
        self.brush_width = 10
        self.eraser_width = 28
        self.comment_dir = self.output_dir / "comment"
        if resume:
            self._load_resume_records()

        self.root = Tk()
        self.root.title("OA review")
        self.root.configure(bg="#eeeeee")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        self.info_label = Label(self.root, anchor="center", justify="center", bg="#f7f7f7", padx=8, pady=4)
        self.info_label.grid(row=0, column=0, sticky="ew")
        self.nav_frame = Frame(self.root, bg="#eeeeee")
        self.nav_frame.grid(row=1, column=0, sticky="ew", pady=(7, 0))
        self.nav_frame.columnconfigure(0, weight=1)
        self.nav_frame.columnconfigure(1, weight=1)
        self._build_navigation()

        self.image_frame = Frame(self.root, bg="#eeeeee")
        self.image_frame.grid(row=2, column=0, sticky="nsew", padx=14, pady=(8, 8))
        self.image_frame.rowconfigure(0, weight=1)
        self.image_frame.columnconfigure(0, weight=1)
        self.canvas = Canvas(self.image_frame, highlightthickness=0, bg="#eeeeee")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.x_scrollbar = Scrollbar(self.image_frame, orient="horizontal", command=self.canvas.xview)
        self.y_scrollbar = Scrollbar(self.image_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.x_scrollbar.set, yscrollcommand=self.y_scrollbar.set)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)
        self.canvas.bind("<ButtonPress-1>", self._start_drawing)
        self.canvas.bind("<B1-Motion>", self._continue_drawing)
        self.canvas.bind("<ButtonRelease-1>", self._end_drawing)
        self.controls_frame = Frame(self.root, bg="#eeeeee")
        self.controls_frame.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.photo = None

        self._build_buttons()
        self._build_menu()
        self._show_current()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_navigation(self) -> None:
        left_frame = Frame(self.nav_frame, bg="#eeeeee")
        left_frame.grid(row=0, column=0, sticky="e", padx=(0, 14))
        right_frame = Frame(self.nav_frame, bg="#eeeeee")
        right_frame.grid(row=0, column=1, sticky="w", padx=(14, 0))

        Label(left_frame, text="Go to", bg="#eeeeee").pack(side="left", padx=(0, 5))
        self.page_entry = Entry(left_frame, width=7, justify="center")
        self.page_entry.pack(side="left", padx=(0, 5))
        self.page_entry.bind("<Return>", self.go_to_page)
        Button(left_frame, text="Page", command=self.go_to_page).pack(side="left")

        Label(right_frame, text="comment", bg="#eeeeee").pack(side="left", padx=(0, 5))
        self.comment_entry = Entry(right_frame, width=54)
        self.comment_entry.pack(side="left")
        self.comment_entry.bind("<KeyRelease>", self._on_comment_changed)
        self.comment_entry.bind("<FocusOut>", self._on_comment_focus_out)
        self.comment_entry.bind("<Return>", self._on_comment_focus_out)

    def _build_buttons(self) -> None:
        score_frame = Frame(self.controls_frame, bg="#eeeeee")
        score_frame.pack(side="top", anchor="center", pady=(0, 5))
        flag_frame = Frame(self.controls_frame, bg="#eeeeee")
        flag_frame.pack(side="top", anchor="center", pady=(0, 5))
        drawing_frame = Frame(self.controls_frame, bg="#eeeeee")
        drawing_frame.pack(side="top", anchor="center")

        Button(score_frame, text="not a lens(0)", command=lambda: self.classify(0), bg="#f5ebe7").pack(
            side="left", padx=8, pady=3
        )
        Button(score_frame, text="maybe not a lens(1)", command=lambda: self.classify(1), bg="#f3e2d6").pack(
            side="left", padx=8, pady=3
        )
        Button(score_frame, text="maybe a lens(2)", command=lambda: self.classify(2), bg="#debcb2").pack(
            side="left", padx=8, pady=3
        )
        Button(score_frame, text="sure lens(3)", command=lambda: self.classify(3), bg="#d5a294").pack(
            side="left", padx=8, pady=3
        )
        Button(score_frame, text="correct previous", command=self.correct_previous).pack(side="left", padx=8, pady=3)

        for label, key in (
            ("arc/ring", "ring"),
            ("other interesting obj.", "interesting"),
            ("target not in the centre", "recenter"),
            ("Incomplete labeling", "incomplete_labeling"),
            ("over-annotation", "over_annotation"),
            ("under-annotation", "under_annotation"),
            ("Accurate annotation", "accurate_annotation"),
        ):
            button = Button(flag_frame, text=label, command=lambda flag_key=key: self.set_flag(flag_key))
            button.pack(side="left", padx=8, pady=3)
            self.flag_buttons[key] = button

        for label, mode in (("brush", "brush"), ("eraser", "eraser")):
            button = Button(drawing_frame, text=label, command=lambda draw_mode=mode: self.set_draw_mode(draw_mode))
            button.pack(side="left", padx=8, pady=3)
            self.draw_buttons[mode] = button
        Label(drawing_frame, text="brush size", bg="#eeeeee").pack(side="left", padx=(12, 4), pady=3)
        self.brush_size_scale = Scale(
            drawing_frame,
            from_=2,
            to=40,
            orient="horizontal",
            length=120,
            showvalue=True,
            command=self.set_brush_width,
            bg="#eeeeee",
            highlightthickness=0,
        )
        self.brush_size_scale.set(self.brush_width)
        self.brush_size_scale.pack(side="left", padx=(0, 8), pady=0)
        Button(drawing_frame, text="clear drawing", command=self.clear_drawing).pack(side="left", padx=8, pady=3)

    def _build_menu(self) -> None:
        menubar = Menu(self.root)
        save_menu = Menu(menubar, tearoff=0)
        save_menu.add_command(label="Save CSV", command=self.save_csv)
        save_menu.add_separator()
        menubar.add_cascade(label="Save", menu=save_menu)
        self.root.config(menu=menubar)

    def _fit_image(self, image: Image.Image, max_width: int, max_height: int) -> tuple[Image.Image, int, int]:
        max_width = max(max_width, 120)
        max_height = max(max_height, 120)
        ratio = image.width / float(image.height)

        target_width = max_width
        target_height = int(round(target_width / ratio))
        if target_height > max_height:
            target_height = max_height
            target_width = int(round(target_height * ratio))

        resized = image.resize((target_width, target_height), Image.LANCZOS)
        return resized, target_width, target_height

    def _initial_image_size(self, image: Image.Image) -> tuple[int, int]:
        screen_width = max(self.root.winfo_screenwidth(), 800)
        screen_height = max(self.root.winfo_screenheight(), 600)
        max_width = max(min(screen_width - 160, int(self.win_height * image.width / float(image.height))), 400)
        max_height = max(min(self.win_height, screen_height - 220), 250)
        _resized, width, height = self._fit_image(image, max_width, max_height)
        return width, height

    def _show_current(self) -> None:
        candidate = self.candidates[self.counter]
        with Image.open(candidate.image_path) as image:
            self.current_image = image.convert("RGB").copy()
        self.current_candidate = candidate
        self._load_drawing_overlay()
        self.zoom_scale = 1.0

        initial_width, initial_height = self._initial_image_size(self.current_image)
        if not self.geometry_initialized:
            self.canvas.config(width=initial_width, height=initial_height)
            self.root.geometry(f"{initial_width + 28}x{initial_height + 196}")
            self.root.minsize(920, 560)
            self.geometry_initialized = True

        self._load_current_record_state()
        self.info_label.config(text=self._info_text(candidate), wraplength=max(initial_width, 600))
        self.root.title(f"OA review - {candidate.patch_id} ({self.counter + 1}/{len(self.candidates)})")
        self._refresh_flag_buttons()
        self._render_current_image()
        self.root.update_idletasks()

    def _on_canvas_configure(self, _event: object) -> None:
        if self.current_image is None:
            return
        if self.resize_after_id is not None:
            self.root.after_cancel(self.resize_after_id)
        self.resize_after_id = self.root.after(60, self._render_current_image)

    def _render_current_image(self) -> None:
        self.resize_after_id = None
        if self.current_image is None:
            return

        canvas_width = max(self.canvas.winfo_width(), 120)
        canvas_height = max(self.canvas.winfo_height(), 120)
        display_image = self._display_image()
        fit_image, fit_width, fit_height = self._fit_image(display_image, canvas_width - 16, canvas_height - 16)
        width = max(1, int(round(fit_width * self.zoom_scale)))
        height = max(1, int(round(fit_height * self.zoom_scale)))
        if width == fit_width and height == fit_height:
            resized = fit_image
        else:
            resized = display_image.resize((width, height), Image.LANCZOS)

        self.rendered_width = width
        self.rendered_height = height
        self.info_label.config(wraplength=max(canvas_width, 600))
        self.photo = ImageTk.PhotoImage(resized)
        self.canvas.delete("all")
        self.image_origin_x = 0 if width > canvas_width else (canvas_width - width) / 2
        self.image_origin_y = 0 if height > canvas_height else (canvas_height - height) / 2
        scroll_width = max(width, canvas_width)
        scroll_height = max(height, canvas_height)
        self.canvas.config(scrollregion=(0, 0, scroll_width, scroll_height))
        self.canvas.create_image(self.image_origin_x, self.image_origin_y, image=self.photo, anchor="nw")
        self._update_scrollbars(width > canvas_width, height > canvas_height)

    def _display_image(self) -> Image.Image:
        if self.current_image is None:
            raise ValueError("No current image is loaded.")
        if self.drawing_overlay is None or not self._overlay_has_marks(self.drawing_overlay):
            return self.current_image
        base = self.current_image.convert("RGBA")
        return Image.alpha_composite(base, self.drawing_overlay).convert("RGB")

    def _update_scrollbars(self, show_horizontal: bool, show_vertical: bool) -> None:
        if show_horizontal and not self.h_scroll_visible:
            self.x_scrollbar.grid(row=1, column=0, sticky="ew")
            self.h_scroll_visible = True
        elif not show_horizontal and self.h_scroll_visible:
            self.x_scrollbar.grid_remove()
            self.h_scroll_visible = False
            self.canvas.xview_moveto(0)

        if show_vertical and not self.v_scroll_visible:
            self.y_scrollbar.grid(row=0, column=1, sticky="ns")
            self.v_scroll_visible = True
        elif not show_vertical and self.v_scroll_visible:
            self.y_scrollbar.grid_remove()
            self.v_scroll_visible = False
            self.canvas.yview_moveto(0)

    def _on_ctrl_mousewheel(self, event: Any) -> str:
        factor = 1.15 if event.delta > 0 else 1 / 1.15
        self._zoom_at(event.x, event.y, factor)
        return "break"

    def _zoom_at(self, canvas_x: int, canvas_y: int, factor: float) -> None:
        if self.current_image is None:
            return

        old_width = max(self.rendered_width, 1)
        old_height = max(self.rendered_height, 1)
        old_canvas_x = self.canvas.canvasx(canvas_x)
        old_canvas_y = self.canvas.canvasy(canvas_y)
        rel_x = (old_canvas_x - self.image_origin_x) / old_width
        rel_y = (old_canvas_y - self.image_origin_y) / old_height
        rel_x = min(max(rel_x, 0.0), 1.0)
        rel_y = min(max(rel_y, 0.0), 1.0)

        self.zoom_scale = min(6.0, max(0.5, self.zoom_scale * factor))
        self._render_current_image()
        self.root.update_idletasks()

        canvas_width = max(self.canvas.winfo_width(), 120)
        canvas_height = max(self.canvas.winfo_height(), 120)
        scroll_width = max(self.rendered_width, canvas_width)
        scroll_height = max(self.rendered_height, canvas_height)
        if self.rendered_width > canvas_width:
            target_left = rel_x * self.rendered_width - canvas_x
            self.canvas.xview_moveto(min(max(target_left / scroll_width, 0.0), 1.0))
        if self.rendered_height > canvas_height:
            target_top = rel_y * self.rendered_height - canvas_y
            self.canvas.yview_moveto(min(max(target_top / scroll_height, 0.0), 1.0))

    def set_draw_mode(self, mode: str) -> None:
        self.draw_mode = None if self.draw_mode == mode else mode
        self.last_draw_point = None
        self._refresh_draw_buttons()

    def _refresh_draw_buttons(self) -> None:
        for mode, button in self.draw_buttons.items():
            if self.draw_mode == mode:
                button.config(relief="sunken", bg="#dcefd6")
            else:
                button.config(relief="raised", bg="SystemButtonFace")
        self.canvas.config(cursor="crosshair" if self.draw_mode else "")

    def set_brush_width(self, value: str) -> None:
        try:
            self.brush_width = max(1, int(float(value)))
        except ValueError:
            self.brush_width = 10

    def clear_drawing(self) -> None:
        if self.current_image is None:
            return
        self.drawing_overlay = Image.new("RGBA", self.current_image.size, (0, 0, 0, 0))
        self._save_current_drawing()
        self._save_current_state_to_record()
        self.autosave()
        self._render_current_image()

    def _safe_patch_id(self, patch_id: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", patch_id)

    def _annotation_paths(self, page_index: int) -> tuple[Path, Path]:
        candidate = self.candidates[page_index - 1]
        safe_id = self._safe_patch_id(candidate.patch_id)
        return (
            self.comment_dir / f"{page_index:04d}_{safe_id}_annotation.png",
            self.comment_dir / f"{page_index:04d}_{safe_id}_preview.png",
        )

    def _load_drawing_overlay(self) -> None:
        if self.current_image is None:
            self.drawing_overlay = None
            return
        overlay_path, _preview_path = self._annotation_paths(self.counter + 1)
        if overlay_path.is_file():
            try:
                overlay = Image.open(overlay_path).convert("RGBA")
                if overlay.size != self.current_image.size:
                    overlay = overlay.resize(self.current_image.size, Image.NEAREST)
                self.drawing_overlay = overlay.copy()
                return
            except OSError:
                pass
        self.drawing_overlay = Image.new("RGBA", self.current_image.size, (0, 0, 0, 0))

    def _overlay_has_marks(self, overlay: Image.Image | None) -> bool:
        if overlay is None:
            return False
        return overlay.getchannel("A").getbbox() is not None

    def _page_has_image_comment(self, page_index: int) -> bool:
        if page_index == self.counter + 1 and self._overlay_has_marks(self.drawing_overlay):
            return True
        overlay_path, _preview_path = self._annotation_paths(page_index)
        if not overlay_path.is_file():
            return False
        try:
            with Image.open(overlay_path) as overlay:
                return overlay.convert("RGBA").getchannel("A").getbbox() is not None
        except OSError:
            return False

    def _save_current_drawing(self) -> None:
        if self.current_image is None or self.drawing_overlay is None:
            return
        overlay_path, preview_path = self._annotation_paths(self.counter + 1)
        has_marks = self._overlay_has_marks(self.drawing_overlay)

        if has_marks:
            self.comment_dir.mkdir(parents=True, exist_ok=True)
            self.drawing_overlay.save(overlay_path)
            preview = Image.alpha_composite(self.current_image.convert("RGBA"), self.drawing_overlay).convert("RGB")
            preview.save(preview_path)
        else:
            for path in (overlay_path, preview_path):
                if path.is_file():
                    path.unlink()

    def _canvas_to_image_point(self, canvas_x: int, canvas_y: int) -> tuple[int, int] | None:
        if self.current_image is None or self.rendered_width <= 0 or self.rendered_height <= 0:
            return None
        x = self.canvas.canvasx(canvas_x) - self.image_origin_x
        y = self.canvas.canvasy(canvas_y) - self.image_origin_y
        if x < 0 or y < 0 or x > self.rendered_width or y > self.rendered_height:
            return None
        image_x = int(round(x / self.rendered_width * (self.current_image.width - 1)))
        image_y = int(round(y / self.rendered_height * (self.current_image.height - 1)))
        return (
            min(max(image_x, 0), self.current_image.width - 1),
            min(max(image_y, 0), self.current_image.height - 1),
        )

    def _start_drawing(self, event: Any) -> str | None:
        if not self.draw_mode:
            return None
        point = self._canvas_to_image_point(event.x, event.y)
        if point is None:
            return "break"
        self.last_draw_point = point
        self._draw_segment(point, point)
        self._render_current_image()
        return "break"

    def _continue_drawing(self, event: Any) -> str | None:
        if not self.draw_mode:
            return None
        point = self._canvas_to_image_point(event.x, event.y)
        if point is None:
            return "break"
        if self.last_draw_point is None:
            self.last_draw_point = point
        self._draw_segment(self.last_draw_point, point)
        self.last_draw_point = point
        self._render_current_image()
        return "break"

    def _end_drawing(self, _event: Any) -> str | None:
        if not self.draw_mode:
            return None
        self.last_draw_point = None
        self._save_current_drawing()
        self._save_current_state_to_record()
        self.autosave()
        return "break"

    def _draw_segment(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        if self.drawing_overlay is None or self.current_image is None or self.draw_mode is None:
            return
        if self.draw_mode == "brush":
            draw = ImageDraw.Draw(self.drawing_overlay, "RGBA")
            draw.line([start, end], fill=(0, 255, 0, 220), width=self.brush_width, joint="curve")
            radius = max(self.brush_width // 2, 1)
            draw.ellipse((end[0] - radius, end[1] - radius, end[0] + radius, end[1] + radius), fill=(0, 255, 0, 220))
        elif self.draw_mode == "eraser":
            alpha = self.drawing_overlay.getchannel("A")
            draw = ImageDraw.Draw(alpha)
            draw.line([start, end], fill=0, width=self.eraser_width, joint="curve")
            radius = max(self.eraser_width // 2, 1)
            draw.ellipse((end[0] - radius, end[1] - radius, end[0] + radius, end[1] + radius), fill=0)
            self.drawing_overlay.putalpha(alpha)

    def _info_text(self, candidate: Candidate) -> str:
        parts = []
        for key, label in DISPLAY_FIELDS:
            value = candidate.metadata.get(key, "")
            if value:
                parts.append(f"{label}: {value}")
        return "    ".join(parts) if parts else f"ID: {candidate.patch_id}"

    def _refresh_flag_buttons(self) -> None:
        for key, button in self.flag_buttons.items():
            if self.current_flags[key]:
                button.config(relief="sunken", bg="#dcefd6")
            else:
                button.config(relief="raised", bg="SystemButtonFace")

    def set_flag(self, key: str) -> None:
        self.current_flags[key] = 0 if self.current_flags[key] else 1
        self._refresh_flag_buttons()
        self._save_current_drawing()
        self._save_current_state_to_record()
        self.autosave()

    def _record_has_score(self, record: dict[str, Any] | None) -> bool:
        return bool(_as_text(record.get("visuScore") if record else ""))

    def _base_record(self, page_index: int) -> dict[str, Any]:
        candidate = self.candidates[page_index - 1]
        return {
            "index": page_index,
            "table_id": candidate.patch_id,
            "id": candidate.metadata.get("id", candidate.patch_id),
            "ra": candidate.metadata.get("ra", ""),
            "dec": candidate.metadata.get("dec", ""),
            "redshift": candidate.metadata.get("redshift", ""),
            "rms": candidate.metadata.get("rms", ""),
            "catalogue": candidate.metadata.get("catalogue", ""),
            "comment": "",
            "has_image_comment": "0",
            "visuScore": "",
            "image_file": candidate.object_id,
            **{name: 0 for name in FLAG_COLUMNS},
        }

    def _save_current_state_to_record(self, create: bool = False) -> None:
        if not hasattr(self, "comment_entry"):
            return

        page_index = self.counter + 1
        record = dict(self.records_by_index.get(page_index, self._base_record(page_index)))
        existing_has_score = self._record_has_score(record)
        record.update(self.current_flags)
        record["comment"] = self.comment_entry.get().strip()
        record["has_image_comment"] = "1" if self._page_has_image_comment(page_index) else "0"

        has_flags = any(int(record.get(name, 0) or 0) for name in FLAG_COLUMNS)
        has_comment = bool(record["comment"])
        has_image_comment = record["has_image_comment"] == "1"
        if existing_has_score or has_flags or has_comment or has_image_comment or create:
            self.records_by_index[page_index] = record
        else:
            self.records_by_index.pop(page_index, None)

    def _load_current_record_state(self) -> None:
        page_index = self.counter + 1
        record = self.records_by_index.get(page_index)
        if record:
            self.current_flags = {name: int(record.get(name, 0) or 0) for name in FLAG_COLUMNS}
            comment = _as_text(record.get("comment"))
        else:
            self.current_flags = {name: 0 for name in FLAG_COLUMNS}
            comment = ""

        self.comment_entry.delete(0, "end")
        if comment:
            self.comment_entry.insert(0, comment)
        self.page_entry.delete(0, "end")
        self.page_entry.insert(0, str(page_index))

    def _on_comment_changed(self, _event: object | None = None) -> None:
        if self.comment_after_id is not None:
            self.root.after_cancel(self.comment_after_id)
        self.comment_after_id = self.root.after(500, self._save_comment_autosave)

    def _on_comment_focus_out(self, _event: object | None = None) -> str | None:
        self._save_comment_autosave()
        return "break" if _event is not None and getattr(_event, "keysym", "") == "Return" else None

    def _save_comment_autosave(self) -> None:
        self.comment_after_id = None
        self._save_current_state_to_record()
        self.autosave()

    def go_to_page(self, _event: object | None = None) -> None:
        raw_page = self.page_entry.get().strip()
        try:
            page = int(raw_page)
        except ValueError:
            messagebox.showinfo("Go to Page", f"Invalid page: {raw_page}")
            return

        if page < 1 or page > len(self.candidates):
            messagebox.showinfo("Go to Page", f"Page must be between 1 and {len(self.candidates)}.")
            return

        self._save_current_drawing()
        self._save_current_state_to_record()
        self.autosave()
        self.counter = page - 1
        self._show_current()

    def classify(self, score: int) -> None:
        self._save_current_drawing()
        page_index = self.counter + 1
        record = dict(self.records_by_index.get(page_index, self._base_record(page_index)))
        record.update(self.current_flags)
        record["comment"] = self.comment_entry.get().strip()
        record["has_image_comment"] = "1" if self._page_has_image_comment(page_index) else "0"
        record["visuScore"] = score
        self.records_by_index[page_index] = record
        self.autosave()

        if self.counter + 1 >= len(self.candidates):
            self.save_csv(final=True)
            messagebox.showinfo("Done", "No more images to analyse.")
            self.root.quit()
            return

        self.counter += 1
        self._show_current()

    def correct_previous(self) -> None:
        self._save_current_drawing()
        self._save_current_state_to_record()
        scored_indexes = sorted(index for index, record in self.records_by_index.items() if self._record_has_score(record))
        if not scored_indexes:
            messagebox.showinfo("Error", "The list is empty")
            return

        current_page = self.counter + 1
        target_candidates = [index for index in scored_indexes if index <= current_page]
        if not self._record_has_score(self.records_by_index.get(current_page)):
            target_candidates = [index for index in scored_indexes if index < current_page]
        target_index = target_candidates[-1] if target_candidates else scored_indexes[-1]

        previous = self.records_by_index.pop(target_index)
        self.counter = target_index - 1
        self.autosave()
        self._show_current()
        self.current_flags = {name: int(previous.get(name, 0) or 0) for name in FLAG_COLUMNS}
        self.comment_entry.delete(0, "end")
        comment = _as_text(previous.get("comment"))
        if comment:
            self.comment_entry.insert(0, comment)
        self._refresh_flag_buttons()

    def _safe_classifier(self) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", self.classifier)

    def _output_path(self) -> Path:
        end_index = max(self.records_by_index) if self.records_by_index else self.counter + 1
        return self.output_dir / f"classif_{self._safe_classifier()}_id{self.start_index}to{end_index}.csv"

    def _autosave_path(self) -> Path:
        return self.output_dir / f"classif_{self._safe_classifier()}_autosave.csv"

    def _load_resume_records(self) -> None:
        autosave_path = self._autosave_path()
        if not autosave_path.is_file():
            return

        loaded: dict[int, dict[str, Any]] = {}
        with autosave_path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    index = int(row.get("index", ""))
                except ValueError:
                    continue

                if index < 1 or index > len(self.candidates):
                    continue

                candidate = self.candidates[index - 1]
                table_id = _as_text(row.get("table_id"))
                image_file = _as_text(row.get("image_file"))
                if table_id and table_id != candidate.patch_id:
                    continue
                if image_file and image_file != candidate.object_id:
                    continue

                record = self._base_record(index)
                record.update({field: row.get(field, "") for field in CSV_FIELDNAMES})
                loaded[index] = record

        if loaded:
            self.records_by_index = loaded
            self.counter = self._first_unreviewed_index(self.start_index - 1)

    def _first_unreviewed_index(self, start: int) -> int:
        for index in range(max(start, 0), len(self.candidates)):
            if not self._record_has_score(self.records_by_index.get(index + 1)):
                return index
        return len(self.candidates) - 1

    def _write_csv(self, output_path: Path) -> None:
        with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            for index in sorted(self.records_by_index):
                record = dict(self.records_by_index[index])
                record["has_image_comment"] = "1" if self._page_has_image_comment(index) else "0"
                writer.writerow({field: record.get(field, "") for field in CSV_FIELDNAMES})

    def autosave(self) -> None:
        self._write_csv(self._autosave_path())

    def save_csv(self, final: bool = False) -> None:
        self._save_current_drawing()
        self._save_current_state_to_record()
        if not self.records_by_index:
            if not final:
                messagebox.showinfo("Error", "The list is empty")
            return

        output_path = self._output_path()
        self._write_csv(output_path)
        if not final:
            messagebox.showinfo("Saved", str(output_path))

    def run(self) -> None:
        self.root.mainloop()

    def _on_close(self) -> None:
        if self.comment_after_id is not None:
            self.root.after_cancel(self.comment_after_id)
            self.comment_after_id = None
        self._save_current_drawing()
        self._save_current_state_to_record()
        if self.records_by_index:
            self.autosave()
        self.root.destroy()


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    explicit_start = any(arg == "-s" or (arg.startswith("-s") and len(arg) > 2) for arg in argv)

    parser = argparse.ArgumentParser(description="Program for classifying OA annotation triplets")
    parser.add_argument("-path_cat", default="./vis_table.csv", type=str, help="path of input catalog of candidates")
    parser.add_argument("-id", default="None", type=str, help="your name to write in output file")
    parser.add_argument("-s", default=1, type=int, help="index of first source to classify in catalog")
    parser.add_argument("-win", default=500, type=int, help="maximum height of display window")
    parser.add_argument("--no_resume", action="store_true", help="ignore autosave and start from -s")
    parser.add_argument(
        "-plot_dir",
        default="./annotation_check_triplets",
        type=str,
        help="directory containing the PNG images listed by the catalog",
    )
    args = parser.parse_args(argv)

    catalog_path = Path(args.path_cat).resolve()
    if not catalog_path.is_file() and args.path_cat == "./vis_table.csv":
        fits_path = (Path.cwd() / "vis_table.fits").resolve()
        if fits_path.is_file():
            catalog_path = fits_path
    plot_dir = Path(args.plot_dir).resolve()
    if not plot_dir.is_dir() and (catalog_path.parent / "vis_plot").is_dir():
        plot_dir = catalog_path.parent / "vis_plot"

    candidates = load_candidates(catalog_path, plot_dir)
    print(f"Catalog length is {len(candidates)}")
    print(f"Loaded {len(candidates)} images from {plot_dir}")

    app = ReviewApp(candidates, args.id, args.s, args.win, catalog_path.parent, resume=(not explicit_start and not args.no_resume))
    app.run()


if __name__ == "__main__":
    main(sys.argv[1:])
