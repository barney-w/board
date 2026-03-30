"""Assemble the board starter-kit zip."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path  # noqa: TC003 — used at runtime in function signatures

def _patch_vsix(vsix_path: Path, png_content: bytes) -> bytes:
    """Return a patched VSIX (bytes) with the board-pass PNG replaced.

    Replaces ``extension/resources/board-pass-card.png`` with the
    personalised card image.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(vsix_path, "r") as src, zipfile.ZipFile(
        buf, "w", zipfile.ZIP_DEFLATED
    ) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "extension/resources/board-pass-card.png":
                data = png_content
            dst.writestr(item, data)

    return buf.getvalue()


def build_zip(
    board_pass_path: Path,
    vsix_path: Path,
    output_dir: Path,
    name: str,
    templates_dir: Path | None = None,
    board_pass_png: bytes | None = None,
) -> Path:
    """Create ``{name}-board.zip`` in *output_dir*.

    The zip contains:
    - ``{name}.board-pass``
    - ``board.vsix``
    - ``Setup Board.command``  (macOS launcher, from *templates_dir*)
    - ``Setup Board.cmd``      (Windows launcher, from *templates_dir*)
    - ``Board Quick Start.pdf`` (optional, from *templates_dir*)

    If *board_pass_png* is provided the VSIX is patched to replace the
    default board-pass card image with a personalised one.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{name}-board.zip"
    prefix = f"{name}-board"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(board_pass_path, f"{prefix}/{name}.board-pass")

        if board_pass_png:
            vsix_bytes = _patch_vsix(vsix_path, board_pass_png)
            zf.writestr(f"{prefix}/board.vsix", vsix_bytes)
        else:
            zf.write(vsix_path, f"{prefix}/board.vsix")

        if templates_dir is not None:
            for filename in ("Setup Board.command", "Setup Board.cmd"):
                src = templates_dir / filename
                if src.exists():
                    zf.write(src, f"{prefix}/{filename}")

            pdf = templates_dir / "Board Quick Start.pdf"
            if pdf.exists():
                zf.write(pdf, f"{prefix}/Board Quick Start.pdf")

    return zip_path
