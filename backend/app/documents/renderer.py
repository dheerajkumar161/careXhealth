"""Document presentation: agent Markdown + structured data → Jinja2 HTML template → PDF (xhtml2pdf).

Agents produce content; formatting lives only here and in backend/templates/.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from app.core.config import BACKEND_DIR
from app.core.util import fmt_date_time, now, parse_dt

TEMPLATES = {
    "PATIENT_INSTRUCTIONS": "patient_plan.html",
    "REFERRAL_PACKAGE": "referral_package.html",
    "NURSE_HANDOFF": "nurse_handoff.html",
    "CLINICAL_SUMMARY": "recovery_summary.html",
}
DEFAULT_TEMPLATE = "clinical_summary.html"

# xhtml2pdf's built-in fonts lack most symbols; register a Unicode TTF when one is available.
FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
]
# Emoji pictographs have no glyphs in document fonts
EMOJI = re.compile("[\U0001f300-\U0001faff\U00002600-\U000026ff\U00002700-\U000027bf\U0001f000-\U0001f2ff\ufe0f]")

_env = Environment(loader=FileSystemLoader(BACKEND_DIR / "templates"), autoescape=select_autoescape(["html"]))


def _font() -> str | None:
    return next((p.as_posix() for p in FONT_CANDIDATES if p.exists()), None)


SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")  # e.g. SpO₂ — common document fonts lack these glyphs


def markdown_to_html(text: str) -> Markup:
    return Markup(md.markdown(EMOJI.sub("", text).translate(SUBSCRIPTS), extensions=["tables", "sane_lists"]))  # noqa: S704 (markdown output of our own documents)


def render_html(document: dict[str, Any], patient: dict[str, Any]) -> str:
    template = _env.get_template(TEMPLATES.get(document["type"], DEFAULT_TEMPLATE))
    created = parse_dt(document["createdAt"]) or now()
    return template.render(
        doc=document,
        patient=patient,
        body=markdown_to_html(document["content"]),
        data=document.get("data") if isinstance(document.get("data"), dict) else {},
        created=fmt_date_time(created),
        generated=fmt_date_time(now()),
        font_path=_font(),
    )


def render_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa
    from xhtml2pdf.config.resources import ResourceAccessPolicy

    # Documents contain user-entered text: no network fetches; local reads only for templates and the font.
    font = _font()
    policy = ResourceAccessPolicy(allow_remote=False, base_dir=BACKEND_DIR / "templates", extra_roots=[Path(font).parent] if font else [])
    out = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=out, encoding="utf-8", resource_policy=policy)
    if result.err:
        raise RuntimeError("PDF rendering failed")
    return out.getvalue()
