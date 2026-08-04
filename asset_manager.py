from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPixmap


def discover_files(folder: Path, supported_extensions: set[str]) -> list[Path]:
    """Return supported files in a customization slot, alphabetically."""
    try:
        return sorted(
            (
                path
                for path in folder.iterdir()
                if path.is_file() and path.suffix.lower() in supported_extensions
            ),
            key=lambda path: path.name.casefold(),
        )
    except OSError:
        return []


def discover_first_file(folder: Path, supported_extensions: set[str]) -> Path | None:
    candidates = discover_files(folder, supported_extensions)
    return candidates[0] if candidates else None


def load_scaled_pixmap(path: Path | None, size: int) -> QPixmap:
    """Decode and scale an image once instead of during every repaint."""
    if path is None:
        return QPixmap()
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(
        QSize(size, size),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def load_scaled_pixmaps(
    folder: Path,
    supported_extensions: set[str],
    size: int,
) -> tuple[list[Path], list[QPixmap]]:
    paths = discover_files(folder, supported_extensions)
    valid_paths: list[Path] = []
    pixmaps: list[QPixmap] = []
    for path in paths:
        pixmap = load_scaled_pixmap(path, size)
        if pixmap.isNull():
            continue
        valid_paths.append(path)
        pixmaps.append(pixmap)
    return valid_paths, pixmaps


def is_edible_item(image_path: Path) -> tuple[bool, str]:
    """Conservatively identify obvious food or RAM images."""
    try:
        if not image_path.is_file():
            return False, ""
        stem = image_path.stem.casefold()

        ram_keywords = (
            "ram", "ddr", "dimm", "sodimm", "vram", "memory stick", "memory_stick",
        )
        if any(keyword in stem for keyword in ram_keywords):
            return True, "Nom nom nom! Delicious RAM! 💾 [^w^]"

        food_keywords = (
            "orange", "apple", "banana", "fruit", "pizza", "burger", "snack",
            "food", "cake", "cookie", "bread", "cheese", "meat", "candy",
            "sushi", "taco", "donut", "berry", "citrus", "peach", "mango",
            "strawberry", "grape", "melon", "watermelon",
        )
        if any(keyword in stem for keyword in food_keywords):
            clean_name = image_path.stem.replace("_", " ")
            return True, f"Nom nom nom! Delicious {clean_name}! 😋 [^w^]"

        image = QImage(str(image_path))
        if image.isNull() or image.width() < 20 or image.height() < 20:
            return False, ""

        # Only roughly food-shaped images are eligible for palette guessing.
        aspect = image.width() / image.height()
        if not 0.60 <= aspect <= 1.70:
            return False, ""

        orange = red = yellow = samples = 0
        x_step = max(1, image.width() // 24)
        y_step = max(1, image.height() // 24)
        for x in range(0, image.width(), x_step):
            for y in range(0, image.height(), y_step):
                color = QColor(image.pixel(x, y))
                red_value, green_value, blue_value = (
                    color.red(), color.green(), color.blue()
                )
                samples += 1
                if (
                    red_value > 160
                    and green_value > 75
                    and blue_value < 115
                    and red_value > green_value > blue_value
                ):
                    orange += 1
                elif red_value > 170 and green_value < 80 and blue_value < 80:
                    red += 1
                elif red_value > 185 and green_value > 155 and blue_value < 105:
                    yellow += 1

        if samples:
            if orange / samples > 0.32:
                return True, "Nom nom nom! Delicious juicy orange! 🍊 [^w^]"
            if red / samples > 0.32:
                return True, "Nom nom nom! Delicious red fruit! 🍎 [^w^]"
            if yellow / samples > 0.32:
                return True, "Nom nom nom! Delicious snack! 🍌 [^w^]"
    except (OSError, ValueError):
        pass
    return False, ""


def count_spoken_words(message: str) -> int:
    """Count alphabetic words while ignoring bracketed visor expressions."""
    without_expressions = re.sub(r"\[[^\]\r\n]{1,24}\]", " ", message)
    return len(
        re.findall(
            r"(?<!\w)[^\W\d_]+(?:['\u2019][^\W\d_]+)*(?!\w)",
            without_expressions,
            flags=re.UNICODE,
        )
    )

