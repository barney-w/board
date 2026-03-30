"""Render a customised board-pass card for a developer."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from xml.sax.saxutils import escape


def _format_date(iso: str) -> str:
    """Format an ISO-8601 timestamp as ``29 Mar 2026``."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f"{dt.day} {dt.strftime('%b')} {dt.year}"


def _time_remaining(valid_until: str) -> tuple[str, bool]:
    """Return a human-readable duration and whether the pass has expired."""
    dt = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
    days = (dt - datetime.now(UTC)).days
    if days < 0:
        return "EXPIRED", True
    if days == 0:
        return "today", False
    if days == 1:
        return "1 day", False
    if days < 60:
        return f"{days} days", False
    months = days // 30
    if months < 12:
        return f"{months} months", False
    years = days // 365
    remainder = (days % 365) // 30
    if remainder and years < 3:
        return f"{years}y {remainder}m", False
    return f"{years} year{'s' if years != 1 else ''}", False


def render_board_pass_svg(
    *,
    developer_name: str,
    environment: str,
    region: str,
    region_short: str,
    vm_name: str,
    auth_method: str,
    issued_at: str,
    valid_until: str,
) -> str:
    """Return a complete SVG string for the board pass card."""
    initials = escape(developer_name[:2].upper())
    name = escape(developer_name)
    env = escape(environment)
    reg = escape(region)
    zone = escape(region_short.upper())
    vm_display = escape(f"devvm-{developer_name}")
    vm_full = escape(vm_name)
    auth = escape(auth_method)
    issued = escape(_format_date(issued_at))
    expires = escape(_format_date(valid_until))
    remaining, expired = _time_remaining(valid_until)
    remaining_esc = escape(remaining)

    stamp_colour = "#ef4444" if expired else "#22c55e"
    stamp_text = "REVOKED" if expired else "AUTHORISED"
    badge_colour = "#ef4444" if expired else "#22c55e"

    return f"""\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 420" width="680" height="420">
  <defs>
    <style>
      text {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
      .sans {{ font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; }}
    </style>

    <linearGradient id="card-bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1a1f2e"/>
      <stop offset="100%" stop-color="#151926"/>
    </linearGradient>
    <linearGradient id="header-bg" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#0284c7"/>
      <stop offset="100%" stop-color="#0ea5e9"/>
    </linearGradient>
    <linearGradient id="shimmer-grad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="white" stop-opacity="0"/>
      <stop offset="50%" stop-color="white" stop-opacity="0.06"/>
      <stop offset="100%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <pattern id="security-grid" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
      <line x1="0" y1="0" x2="20" y2="0" stroke="white" stroke-opacity="0.04" stroke-width="0.5"/>
      <line x1="0" y1="0" x2="0" y2="20" stroke="white" stroke-opacity="0.04" stroke-width="0.5"/>
    </pattern>
    <clipPath id="card-clip">
      <rect width="680" height="420" rx="12"/>
    </clipPath>
  </defs>

  <!-- Card frame -->
  <rect width="680" height="420" rx="12" fill="url(#card-bg)" stroke="#2a3040" stroke-width="1"/>

  <g clip-path="url(#card-clip)">

    <!-- Holographic shimmer -->
    <rect x="0" y="0" width="680" height="420" fill="url(#shimmer-grad)"/>

    <!-- Header strip -->
    <rect x="0" y="0" width="680" height="56" fill="url(#header-bg)"/>
    <rect x="0" y="0" width="680" height="56" fill="url(#security-grid)"/>

    <!-- Shield icon -->
    <g transform="translate(24, 14)">
      <path d="M14,2 L3,7 L3,13 C3,19.5 7.8,25.6 14,27 C20.2,25.6 25,19.5 25,13 L25,7 Z"
            fill="none" stroke="white" stroke-width="1.5" opacity="0.9"/>
      <path d="M11,14 L13.5,16.5 L18,11" stroke="white" stroke-width="1.8"
            fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>
    </g>

    <text x="52" y="28" font-size="13" font-weight="700" fill="white" letter-spacing="0.18em"
          class="sans">B O A R D &#160; P A S S</text>
    <text x="52" y="44" font-size="10" fill="rgba(255,255,255,0.7)" letter-spacing="0.08em"
          class="sans">ACCESS CREDENTIAL</text>

    <!-- Identity section -->
    <rect x="28" y="72" width="42" height="42" rx="8" fill="#0ea5e9" opacity="0.15"/>
    <text x="49" y="100" text-anchor="middle" font-size="16" font-weight="700"
          fill="#38bdf8" class="sans">{initials}</text>

    <text x="84" y="91" font-size="16" font-weight="600" fill="#e2e8f0"
          class="sans">{name}</text>
    <text x="84" y="108" font-size="11" fill="#64748b"
          class="sans">{env} environment &#183; {reg}</text>

    <!-- Stamp -->
    <g transform="translate(540, 80)">
      <rect x="-52" y="-13" width="104" height="26" rx="4"
            fill="none" stroke="{stamp_colour}" stroke-width="2" opacity="0.8"/>
      <text x="0" y="4" text-anchor="middle" font-size="11" font-weight="700"
            fill="{stamp_colour}" letter-spacing="0.1em" class="sans">{stamp_text}</text>
    </g>

    <!-- Field grid — Row 1: VM / ZONE -->
    <text x="28" y="148" font-size="9" fill="#64748b" letter-spacing="0.08em" class="sans">VM</text>
    <text x="28" y="164" font-size="15" font-weight="600" fill="#e2e8f0">{vm_display}</text>

    <text x="560" y="148" font-size="9" fill="#64748b" letter-spacing="0.08em" class="sans">ZONE</text>
    <rect x="560" y="152" width="44" height="20" rx="4" fill="#0ea5e9" opacity="0.12"/>
    <text x="582" y="167" text-anchor="middle" font-size="13" font-weight="700" fill="#38bdf8">{zone}</text>

    <!-- Row 2: AUTH METHOD / ISSUED / EXPIRES -->
    <text x="28" y="200" font-size="9" fill="#64748b" letter-spacing="0.08em" class="sans">AUTH METHOD</text>
    <text x="28" y="216" font-size="13" fill="#e2e8f0">{auth}</text>

    <text x="220" y="200" font-size="9" fill="#64748b" letter-spacing="0.08em" class="sans">ISSUED</text>
    <text x="220" y="216" font-size="13" fill="#e2e8f0">{issued}</text>

    <text x="400" y="200" font-size="9" fill="#64748b" letter-spacing="0.08em" class="sans">EXPIRES</text>
    <text x="400" y="216" font-size="13" fill="#e2e8f0">{expires}</text>

    <rect x="530" y="202" width="58" height="18" rx="9" fill="{badge_colour}" opacity="0.12"/>
    <text x="559" y="215" text-anchor="middle" font-size="10" font-weight="600"
          fill="{badge_colour}" class="sans">{remaining_esc}</text>

    <!-- Row 3: CLEARANCE -->
    <text x="28" y="252" font-size="9" fill="#64748b" letter-spacing="0.08em" class="sans">CLEARANCE</text>

    <rect x="28" y="260" width="120" height="24" rx="12" fill="#1e293b"/>
    <circle cx="44" cy="272" r="3.5" fill="#22c55e"/>
    <text x="54" y="277" font-size="11" fill="#94a3b8" class="sans">SSH Terminal</text>

    <rect x="160" y="260" width="120" height="24" rx="12" fill="#1e293b"/>
    <circle cx="176" cy="272" r="3.5" fill="#22c55e"/>
    <text x="186" y="277" font-size="11" fill="#94a3b8" class="sans">code-server</text>

    <!-- Perforation -->
    <circle cx="0" cy="306" r="8" fill="#0f1219"/>
    <circle cx="680" cy="306" r="8" fill="#0f1219"/>
    <line x1="16" y1="306" x2="664" y2="306"
          stroke="#2a3040" stroke-width="1" stroke-dasharray="6,4"/>

    <!-- Stub section -->
    <g transform="translate(28, 322)" opacity="0.7">
      <rect x="0" y="0" width="2" height="24" fill="#0ea5e9"/>
      <rect x="4" y="0" width="1" height="24" fill="#0ea5e9"/>
      <rect x="7" y="0" width="3" height="24" fill="#0ea5e9"/>
      <rect x="12" y="0" width="1" height="24" fill="#0ea5e9"/>
      <rect x="15" y="0" width="2" height="24" fill="#0ea5e9"/>
      <rect x="19" y="0" width="3" height="24" fill="#0ea5e9"/>
      <rect x="24" y="0" width="1" height="24" fill="#0ea5e9"/>
      <rect x="27" y="0" width="2" height="24" fill="#0ea5e9"/>
      <rect x="31" y="0" width="1" height="24" fill="#0ea5e9"/>
      <rect x="34" y="0" width="3" height="24" fill="#0ea5e9"/>
      <rect x="39" y="0" width="2" height="24" fill="#0ea5e9"/>
      <rect x="43" y="0" width="1" height="24" fill="#0ea5e9"/>
      <rect x="46" y="0" width="2" height="24" fill="#0ea5e9"/>
      <rect x="50" y="0" width="3" height="24" fill="#0ea5e9"/>
      <rect x="55" y="0" width="1" height="24" fill="#0ea5e9"/>
      <rect x="58" y="0" width="2" height="24" fill="#0ea5e9"/>
      <rect x="62" y="0" width="1" height="24" fill="#0ea5e9"/>
      <rect x="65" y="0" width="3" height="24" fill="#0ea5e9"/>
      <rect x="70" y="0" width="2" height="24" fill="#0ea5e9"/>
      <rect x="74" y="0" width="1" height="24" fill="#0ea5e9"/>
      <rect x="77" y="0" width="2" height="24" fill="#0ea5e9"/>
      <rect x="81" y="0" width="3" height="24" fill="#0ea5e9"/>
      <rect x="86" y="0" width="1" height="24" fill="#0ea5e9"/>
      <rect x="89" y="0" width="2" height="24" fill="#0ea5e9"/>
      <rect x="93" y="0" width="1" height="24" fill="#0ea5e9"/>
      <rect x="96" y="0" width="3" height="24" fill="#0ea5e9"/>
      <rect x="101" y="0" width="2" height="24" fill="#0ea5e9"/>
    </g>

    <text x="28" y="360" font-size="10" fill="#475569">{vm_full}</text>

    <!-- Stub identity -->
    <text x="540" y="336" font-size="13" font-weight="600" fill="#94a3b8"
          class="sans" text-anchor="end">{name}</text>
    <text x="540" y="354" font-size="10" fill="#475569"
          class="sans" text-anchor="end">{reg} &#183; {env}</text>

    <rect x="560" y="322" width="44" height="20" rx="4" fill="#0ea5e9" opacity="0.12"/>
    <text x="582" y="337" text-anchor="middle" font-size="13" font-weight="700" fill="#38bdf8">{zone}</text>

    <text x="540" y="376" font-size="10" fill="#475569"
          class="sans" text-anchor="end">Expires: {expires}</text>

    <!-- Action buttons -->
    <rect x="200" y="384" width="140" height="32" rx="6" fill="#0ea5e9"/>
    <text x="270" y="405" text-anchor="middle" font-size="12" font-weight="600"
          fill="white" class="sans">Connect Now</text>

    <rect x="352" y="384" width="140" height="32" rx="6"
          fill="none" stroke="#334155" stroke-width="1"/>
    <text x="422" y="405" text-anchor="middle" font-size="12" font-weight="500"
          fill="#94a3b8" class="sans">Delete Pass File</text>

  </g>
</svg>
"""


def render_board_pass_png(
    **kwargs: str,
) -> bytes:
    """Render the board-pass SVG and convert to PNG (2x for retina).

    Requires ``rsvg-convert`` on PATH (from librsvg).
    All keyword arguments are forwarded to :func:`render_board_pass_svg`.
    """
    svg = render_board_pass_svg(**kwargs)
    result = subprocess.run(
        ["rsvg-convert", "-w", "1360", "-h", "840"],
        input=svg.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return result.stdout
