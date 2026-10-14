"""Exports: branded PDF reports plus CSV/JSON. Reports never contain keys, prompts or diagnostics.

Every PDF states what it is (AI assessments vs. TMDB facts), the spoiler level, the generation time
and TMDB attribution. Spoiler notes are included only when the caller opts in AND the analysis was
generated with a spoiler level that allows them.
"""
from __future__ import annotations

import csv
import io
import json
import os
import time
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from .. import scoring
from ..config import APP_VERSION, DIMENSIONS
from ..errors import AppError, ErrorCategory
from ..services import Analysis
from ..spoilers import LABELS as SPOILER_LABELS
from .awards import LABEL as AWARDS_LABEL, AwardResult
from .serialize import analysis_to_dict, meta_snapshot

GOLD, INK, MUTED, RULE = "#B7791F", "#14161C", "#5B6472", "#D9DEE6"
TMDB_NOTE = "This product uses the TMDB API but is not endorsed or certified by TMDB."
DISCLAIMER = ("Scores and commentary are CineCritic AI assessments: subjective opinions, not objective measurements, "
              "and not IMDb, TMDB or audience ratings. AI can make mistakes.")


class ExportError(AppError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCategory.INTERNAL, "The PDF could not be generated. Try again, or download the JSON "
                         "version instead." + (f" ({detail})" if detail else ""))


# --------------------------------------------------------------------------- fonts
_FONT = None


def _find_font() -> tuple[str, str] | None:
    candidates = [("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
    try:
        import matplotlib
        base = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
        candidates.append((os.path.join(base, "DejaVuSans.ttf"), os.path.join(base, "DejaVuSans-Bold.ttf")))
    except Exception:
        pass
    return next(((r, b) for r, b in candidates if os.path.exists(r) and os.path.exists(b)), None)


def _fonts() -> tuple[str, str, bool]:
    """(regular, bold, unicode_ok). Falls back to Helvetica with Latin-1 sanitising."""
    global _FONT
    if _FONT is None:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        found = _find_font()
        if found:
            pdfmetrics.registerFont(TTFont("CC-Sans", found[0]))
            pdfmetrics.registerFont(TTFont("CC-Sans-Bold", found[1]))
            _FONT = ("CC-Sans", "CC-Sans-Bold", True)
        else:
            _FONT = ("Helvetica", "Helvetica-Bold", False)
    return _FONT


def _t(text, unicode_ok: bool | None = None) -> str:
    """Escape for ReportLab markup; transliterate to Latin-1 when no Unicode font is available."""
    s = str(text if text is not None else "")
    s = s.replace("’", "'").replace("“", '"').replace("”", '"') if not (unicode_ok or _fonts()[2]) else s
    if not (unicode_ok if unicode_ok is not None else _fonts()[2]):
        s = s.encode("latin-1", "replace").decode("latin-1")
    return escape(s)


# --------------------------------------------------------------------------- document skeleton
def _build(title: str, subtitle: str, story_fn, footer_note: str = "") -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

        regular, bold, uni = _fonts()
        styles = {
            "h1": ParagraphStyle("h1", fontName=bold, fontSize=20, leading=25, textColor=colors.HexColor(INK), spaceAfter=2),
            "sub": ParagraphStyle("sub", fontName=regular, fontSize=10, leading=14, textColor=colors.HexColor(MUTED), spaceAfter=10),
            "h2": ParagraphStyle("h2", fontName=bold, fontSize=12.5, leading=16, textColor=colors.HexColor(GOLD), spaceBefore=12, spaceAfter=5, keepWithNext=1),
            "body": ParagraphStyle("body", fontName=regular, fontSize=9.6, leading=14, textColor=colors.HexColor(INK), alignment=TA_LEFT, spaceAfter=4),
            "small": ParagraphStyle("small", fontName=regular, fontSize=8, leading=11, textColor=colors.HexColor(MUTED), spaceAfter=3),
            "cell": ParagraphStyle("cell", fontName=regular, fontSize=8.8, leading=12, textColor=colors.HexColor(INK)),
            "cellb": ParagraphStyle("cellb", fontName=bold, fontSize=8.8, leading=12, textColor=colors.HexColor(INK)),
            "warn": ParagraphStyle("warn", fontName=bold, fontSize=9, leading=13, textColor=colors.HexColor("#9B1C1C"), spaceAfter=3),
        }
        buf = io.BytesIO()
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=24 * mm,
                              bottomMargin=20 * mm, title=title, author="CineCritic", subject=subtitle)

        def decorate(canvas, d):
            canvas.saveState()
            w, h = A4
            canvas.setFillColor(colors.HexColor("#0B0C10"))
            canvas.rect(0, h - 15 * mm, w, 15 * mm, stroke=0, fill=1)
            canvas.setFillColor(colors.HexColor("#E5A93C"))
            canvas.setFont(bold, 11)
            canvas.drawString(18 * mm, h - 9.5 * mm, "CINECRITIC")
            canvas.setFillColor(colors.HexColor("#CBD5E1"))
            canvas.setFont(regular, 8)
            canvas.drawRightString(w - 18 * mm, h - 9.5 * mm, _plain(title, uni)[:70])
            canvas.setStrokeColor(colors.HexColor(RULE))
            canvas.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
            canvas.setFillColor(colors.HexColor(MUTED))
            canvas.setFont(regular, 7.5)
            canvas.drawString(18 * mm, 9.5 * mm, f"Generated {generated} · CineCritic {APP_VERSION}" + (f" · {footer_note}" if footer_note else ""))
            canvas.drawRightString(w - 18 * mm, 9.5 * mm, f"Page {d.page}")
            canvas.restoreState()

        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
        doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=decorate)])
        story = [_para(title, styles["h1"]), _para(subtitle, styles["sub"])]
        story += story_fn(styles, doc.width)
        doc.build(story)
        return buf.getvalue()
    except AppError:
        raise
    except Exception as exc:
        raise ExportError(type(exc).__name__) from exc


def _plain(text: str, uni: bool) -> str:
    return str(text) if uni else str(text).encode("latin-1", "replace").decode("latin-1")


def _para(text, style):
    from reportlab.platypus import Paragraph
    return Paragraph(_t(text), style)


def _rich(markup: str, style):
    """Paragraph from markup the caller has already escaped with _t()."""
    from reportlab.platypus import Paragraph
    return Paragraph(markup, style)


def _table(rows, widths, styles, header=True, zebra=True):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    data = [[_rich(_t(c), styles["cellb" if (header and i == 0) else "cell"]) if not hasattr(c, "wrap") else c
             for c in row] for i, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3EBDD")))
    if zebra:
        style += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FAFAF7")) for i in range(2, len(rows), 2)]
    t.setStyle(TableStyle(style))
    return t


def _fmt_ts(ts: float | None) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "n/a"


# --------------------------------------------------------------------------- critique report
def critique_pdf(a: Analysis, *, scale: int = 10, weights: dict | None = None, include_spoilers: bool = False,
                 user_rating: float | None = None) -> bytes:
    c, m = a.critique, a.meta
    scores = scoring.dimension_scores(c)
    weighted, used, missing = scoring.weighted_overall(scores, weights)
    show_spoilers = bool(include_spoilers and a.spoiler_level != "none" and c.spoiler_notes)

    def story(S, width):
        from reportlab.platypus import Spacer
        out = []
        facts = [["Field", "Value (TMDB-verified when TMDB data is present)"]]
        src = "TMDB" if m else "AI-supplied, unverified"
        for k, v in (("Year", (m.year if m else c.year)), ("Runtime", (m.runtime if m else c.runtime)),
                     ("Genres", ", ".join(m.genres) if m else c.genre), ("Director", (m.director if m else c.director)),
                     ("Cinematographer", (m.cinematographer if m else c.cinematographer)),
                     ("Composer", (m.composer if m else c.composer)),
                     ("Cast", ", ".join(n for n, _ in m.cast) if m else "")):
            facts.append([k, v or "Not available"])
        facts.append(["Source of facts", src])
        if m and m.rating is not None:
            facts.append(["TMDB audience rating (external)", f"{m.rating:.1f}/10 from {m.votes:,} votes"])
        if user_rating is not None:
            facts.append(["Your rating (personal)", f"{user_rating:.1f}/10"])
        out += [_para("Film facts", S["h2"]), _table(facts, [width * .32, width * .68], S)]

        out += [_para("CineCritic verdict (AI assessment)", S["h2"]),
                _para(f"{c.verdict_label}  ·  Overall {scoring.fmt(c.overall_score if scoring.valid_score(c.overall_score) is not None else None, scale)}"
                      f"/{scale} ({scoring.band(c.overall_score)})", S["cellb"]),
                _para(c.pull_quote, S["body"]), _para(c.verdict_text, S["body"]),
                _para("Recommendation: " + c.recommendation, S["body"])]

        rows = [["Craft category", f"Score /{scale}", "Weight", "Assessment"]]
        for key, title in DIMENSIONS:
            d = getattr(c, key)
            rows.append([title, scoring.fmt(scores[key], scale), f"{(weights or {}).get(key, 1.0):g}",
                         f"{d.summary} {d.detail}".strip() if scores[key] is not None else "Not assessed"])
        out += [_para("Craft scorecard", S["h2"]), _table(rows, [width * .25, width * .12, width * .11, width * .52], S)]
        method = (f"Weighted overall (your weights, {len(used)} of {len(DIMENSIONS)} categories scored): "
                  f"{scoring.fmt(weighted, scale)}/{scale}. The verdict score above is the model's own holistic judgement; "
                  "the weighted figure is computed from the category scores." +
                  (f" Not assessed: {', '.join(scoring.label(k) for k in missing)}." if missing else ""))
        out.append(_para(method, S["small"]))

        out += [_para("Strengths", S["h2"])] + [_para("• " + s, S["body"]) for s in c.strengths]
        out += [_para("Limitations", S["h2"])] + [_para("• " + s, S["body"]) for s in c.flaws]
        if c.themes_tags:
            out.append(_para("Themes (AI interpretation): " + ", ".join(c.themes_tags), S["small"]))
        if show_spoilers:
            out += [_para("SPOILERS BELOW", S["warn"]), _para(c.spoiler_notes, S["body"])]
        elif a.spoiler_level != "none" and c.spoiler_notes:
            out.append(_para("Spoiler notes exist for this film but were left out of this export.", S["small"]))
        out += [Spacer(1, 6), _para("About this report", S["h2"]),
                _para(f"Spoiler setting when generated: {SPOILER_LABELS.get(a.spoiler_level, a.spoiler_level)}. "
                      f"Model: {a.model_used or 'unknown'}" + (f" (fallback: {a.fallback})" if a.fallback else "") +
                      f". Analysed: {_fmt_ts(a.created_at)}.", S["small"]),
                _para(DISCLAIMER, S["small"]), _para(TMDB_NOTE, S["small"])]
        return out

    year = (m.year if m else c.year) or ""
    return _build(f"{c.title or a.query}{f' ({year})' if year else ''}", "Critical report", story,
                  SPOILER_LABELS.get(a.spoiler_level, ""))


# --------------------------------------------------------------------------- comparison
def comparison_pdf(battle, *, scale: int = 10, weights: dict | None = None) -> bytes:
    a, b, comp = battle.a, battle.b, battle.comparison
    wording = {"a": f"{a.critique.title} leads on CineCritic's scores", "b": f"{b.critique.title} leads on CineCritic's scores",
               "too_close": "Too close to call on CineCritic's scores", "inconclusive": "Inconclusive: not enough comparable categories"}

    def story(S, width):
        out = []
        head = [["", a.critique.title, b.critique.title]]
        for k, fa, fb in (("Year", a.critique.year, b.critique.year), ("Director", a.meta.director if a.meta else a.critique.director,
                          b.meta.director if b.meta else b.critique.director),
                          ("Runtime", a.meta.runtime if a.meta else a.critique.runtime, b.meta.runtime if b.meta else b.critique.runtime),
                          ("Metadata source", "TMDB" if a.meta else "AI-supplied", "TMDB" if b.meta else "AI-supplied")):
            head.append([k, fa or "n/a", fb or "n/a"])
        out += [_para("The films", S["h2"]), _table(head, [width * .24, width * .38, width * .38], S)]
        rows = [["Category", a.critique.title, b.critique.title, "Outcome"]]
        names = {"a": a.critique.title, "b": b.critique.title, "tie": "Tie", "insufficient": "Insufficient evidence"}
        for r in comp.dims:
            rows.append([scoring.label(r.key), scoring.fmt(r.a, scale), scoring.fmt(r.b, scale), names[r.outcome]])
        rows.append(["Weighted overall (comparable categories)", scoring.fmt(comp.overall_a, scale),
                     scoring.fmt(comp.overall_b, scale), wording[comp.leader]])
        out += [_para(f"Side-by-side scores (/{scale})", S["h2"]), _table(rows, [width * .34, width * .2, width * .2, width * .26], S),
                _para(comp.rule, S["small"])]
        if battle.narrative:
            out.append(_para("Written comparison (AI-assisted)", S["h2"]))
            out += [_para(p, S["body"]) for p in battle.narrative.split("\n") if p.strip()]
        for n in battle.notices:
            out.append(_para(n, S["small"]))
        out += [_para("About this report", S["h2"]),
                _para("This is an AI-assisted critical comparison, not a statement of objective artistic superiority. " + DISCLAIMER, S["small"]),
                _para(TMDB_NOTE, S["small"])]
        return out

    return _build(f"{a.critique.title} vs {b.critique.title}", "Film comparison", story)


# --------------------------------------------------------------------------- collection + awards
def collection_pdf(entries: list[dict]) -> bytes:
    def story(S, width):
        rows = [["Title", "Year", "Status", "My rating", "Fav"]]
        for e in entries:
            rows.append([e["title"], e.get("year", ""), e["status"].title(),
                         f"{e['rating']:.1f}" if e.get("rating") is not None else "—", "★" if e.get("favorite") else ""])
        out = [_para(f"{len(entries)} film(s)", S["h2"]), _table(rows, [width * .46, width * .1, width * .16, width * .16, width * .12], S)]
        noted = [e for e in entries if e.get("review") or e.get("notes")]
        if noted:
            out.append(_para("Reviews and notes", S["h2"]))
            for e in noted:
                out.append(_para(e["title"], S["cellb"]))
                if e.get("review"):
                    out.append(_para("Review: " + e["review"], S["body"]))
                if e.get("notes"):
                    out.append(_para("Notes: " + e["notes"], S["body"]))
        out.append(_para("Personal ratings are yours; they are separate from CineCritic's AI scores and TMDB ratings. " + TMDB_NOTE, S["small"]))
        return out

    return _build("My film collection", "Personal collection summary", story)


def awards_pdf(results: list[AwardResult], *, name: str = "CineCritic Awards Night", scale: int = 10) -> bytes:
    def story(S, width):
        out = [_para(AWARDS_LABEL, S["small"])]
        for r in results:
            out.append(_para(r.category.title, S["h2"]))
            winners = ", ".join(w.title for w in r.winners) or "No winner"
            label = {"winner": "Winner", "tie": "Tie", "inconclusive": "Inconclusive"}[r.status]
            out.append(_para(f"{label}: {winners}  ·  selected by {r.selected_by}", S["cellb"]))
            out.append(_table([["Nominee", f"Score /{scale}"]] + [[n.title, scoring.fmt(n.score, scale)] for n in r.nominees],
                              [width * .7, width * .3], S))
            out.append(_para(r.explanation, S["small"]))
        out.append(_para(DISCLAIMER, S["small"]))
        return out

    return _build(name, "AI-generated awards from CineCritic scores", story)


# --------------------------------------------------------------------------- JSON / CSV
def analysis_json(a: Analysis, *, include_spoilers: bool = False) -> str:
    data = analysis_to_dict(a)
    data["format"] = "cinecritic-analysis"
    data["exported_at"] = time.time()
    if not (include_spoilers and a.spoiler_level != "none"):
        data["critique"]["spoiler_notes"] = ""
    data.pop("alternatives", None)
    return json.dumps(data, ensure_ascii=False, indent=2)


def archive_csv(entries: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["title", "year", "status", "my_rating", "favorite", "review", "notes", "genres", "director", "tmdb_id"])
    for e in entries:
        m = e.get("meta") or {}
        w.writerow([_csv_safe(e["title"]), e.get("year", ""), e["status"], e.get("rating") if e.get("rating") is not None else "",
                    int(bool(e.get("favorite"))), _csv_safe(e.get("review", "")), _csv_safe(e.get("notes", "")),
                    _csv_safe("; ".join(m.get("genres", []))), _csv_safe(m.get("director", "")), m.get("tmdb_id", "")])
    return buf.getvalue()


def _csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection from user-entered text."""
    s = str(value or "")
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def archive_json(entries: list[dict]) -> str:
    return json.dumps({"format": "cinecritic-collection", "exported_at": time.time(), "films": entries},
                      ensure_ascii=False, indent=2)
