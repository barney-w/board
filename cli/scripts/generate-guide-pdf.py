#!/usr/bin/env python3
"""Generate the Board Quick Start PDF guide.

Usage: python3 generate-guide-pdf.py [output_path]
Default output: scripts/templates/Board Quick Start.pdf

Requires: pip install fpdf2
"""

import sys
from pathlib import Path

from fpdf import FPDF, XPos, YPos


class BoardGuide(FPDF):
    BLUE = (14, 165, 233)  # #0ea5e9
    DARK_BLUE = (2, 132, 199)  # #0284c7
    DARK = (30, 30, 30)
    GREY = (100, 100, 100)
    LIGHT_BG = (248, 250, 252)  # #f8fafc
    WHITE = (255, 255, 255)

    def header(self):
        pass

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*self.GREY)
        self.cell(0, 8, "Board Quick Start Guide", align="L")
        self.cell(0, 8, f"Page {self.page_no()}", align="R")

    def draw_header_bar(self):
        self.set_fill_color(*self.BLUE)
        self.rect(0, 0, 210, 36, "F")
        self.set_xy(20, 8)
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(*self.WHITE)
        self.cell(0, 9, "Board", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(20)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(220, 240, 255)
        self.cell(0, 6, "Quick Start Guide")

    def _rounded_rect(self, x, y, w, h, r):
        """Draw a filled rounded rectangle using overlapping rects + corner circles."""
        self.rect(x + r, y, w - 2 * r, h, "F")
        self.rect(x, y + r, w, h - 2 * r, "F")
        for cx, cy in [
            (x + r, y + r),
            (x + w - r, y + r),
            (x + r, y + h - r),
            (x + w - r, y + h - r),
        ]:
            self.circle(cx, cy, r, "F")

    def draw_step(self, num, title, body, y):
        card_x, card_w, pad = 20, 170, 6
        text_x = card_x + pad + 22
        body_w = card_w - (text_x - card_x) - pad

        # Measure body height by counting how many lines fpdf will wrap to
        self.set_font("Helvetica", "", 9)
        char_w = self.get_string_width("x")
        chars_per_line = int(body_w / char_w)
        import textwrap

        lines = textwrap.wrap(body, width=chars_per_line)
        body_h = len(lines) * 4.5
        card_h = body_h + 16

        # Card background
        self.set_fill_color(*self.LIGHT_BG)
        self.set_draw_color(*self.LIGHT_BG)
        self._rounded_rect(card_x, y, card_w, card_h, 3)

        # Number circle
        cx, cy = card_x + pad + 8, y + card_h / 2
        self.set_fill_color(*self.BLUE)
        self.circle(cx, cy, 8, "F")
        self.set_xy(cx - 8, cy - 4)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*self.WHITE)
        self.cell(16, 8, str(num), align="C")

        # Title
        self.set_xy(text_x, y + 4)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*self.DARK)
        self.cell(0, 5, title)

        # Body
        self.set_xy(text_x, y + 10)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*self.GREY)
        self.multi_cell(body_w, 4.5, body)

        return y + card_h + 4

    def draw_section_title(self, title, y):
        self.set_xy(20, y)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*self.DARK_BLUE)
        self.cell(0, 7, title)
        return y + 9

    def draw_command_row(self, cmd, desc, y, shade):
        if shade:
            self.set_fill_color(*self.LIGHT_BG)
            self.rect(20, y, 170, 7, "F")
        self.set_xy(22, y + 0.5)
        self.set_font("Courier", "B", 7.5)
        self.set_text_color(*self.DARK)
        self.cell(66, 6, cmd)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*self.GREY)
        self.cell(0, 6, desc)
        return y + 7


def build_pdf(output_path):
    pdf = BoardGuide(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # -- Header banner --
    pdf.draw_header_bar()

    # -- Intro --
    y = 44
    pdf.set_xy(20, y)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*BoardGuide.GREY)
    pdf.multi_cell(
        170,
        5,
        "Your admin created a cloud dev environment for you. Follow these steps to get connected.",
    )
    y = pdf.get_y() + 6

    # -- Steps --
    y = pdf.draw_section_title("Get Connected", y)

    y = pdf.draw_step(
        1,
        "Run Setup",
        'Unzip this folder and double-click "Setup Board" '
        "(macOS/Linux: .command, Windows: .cmd). "
        "This installs the VS Code extension and opens your board pass.",
        y,
    )
    y = pdf.draw_step(
        2,
        "Enter Your Passphrase",
        "VS Code will ask for the passphrase your admin shared with you. "
        "This decrypts your connection credentials.",
        y,
    )
    y = pdf.draw_step(
        3,
        "Click Connect",
        "The Board Pass card appears. Click Connect Now and you're coding on your cloud VM.",
        y,
    )
    y += 2

    # -- After Connecting --
    y = pdf.draw_section_title("After Connecting", y)
    pdf.set_xy(20, y)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*BoardGuide.GREY)
    pdf.multi_cell(
        170,
        4.5,
        "On first connect you'll be prompted to run first-time setup "
        "(Git identity + SSH keys). Your VM has a sample project at "
        "~/projects/hello-board -- try docker compose up and visit "
        "http://localhost:8000.",
    )
    y = pdf.get_y() + 6

    # -- Commands table --
    y = pdf.draw_section_title("Commands", y)
    commands = [
        ("Board: Import Pass", "Decrypt and install a .board-pass file"),
        ("Board: Connect", "Open a remote VS Code window on your VM"),
        ("Board: Start / Stop", "Start or deallocate the VM"),
        ("Board: Run First-Time Setup", "Configure Git + SSH keys on the VM"),
        ("Board: Open code-server", "Open code-server in your browser"),
    ]
    for i, (cmd, desc) in enumerate(commands):
        y = pdf.draw_command_row(cmd, desc, y, shade=(i % 2 == 0))

    y += 8

    # -- Footer note --
    pdf.set_xy(20, y)
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_text_color(*BoardGuide.GREY)
    pdf.cell(0, 5, "Don't have a board pass? Ask your admin -- they'll create one for you.")

    pdf.output(output_path)


if __name__ == "__main__":
    default = str(Path(__file__).resolve().parent / "templates" / "Board Quick Start.pdf")
    out = sys.argv[1] if len(sys.argv) > 1 else default
    build_pdf(out)
    print(f"Generated: {out}")
