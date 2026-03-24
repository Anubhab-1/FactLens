from __future__ import annotations
import textwrap
from collections import Counter
from datetime import datetime
from storage.report_diagnostics import build_report_diagnostics

from typing import Any, Callable, Optional

# --- PDF Styling Constants ---
PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT_MARGIN = 50
RIGHT_MARGIN = 50
TOP_MARGIN = 740
BOTTOM_MARGIN = 50
LINE_HEIGHT = 14
TEXT_WRAP_WIDTH = 85  # Adjusted for Helvetica

# Colors (R, G, B) normalized 0-1
COLOR_WHITE = "1 1 1"
COLOR_BLACK = "0 0 0"
COLOR_GREY_DARK = "0.2 0.2 0.2"
COLOR_GREY_LIGHT = "0.5 0.5 0.5"
COLOR_EMERALD = "0.06 0.69 0.44"  # Emerald 500
COLOR_ROSE = "0.88 0.22 0.33"    # Rose 500
COLOR_AMBER = "0.96 0.62 0.04"   # Amber 500
COLOR_BLUE = "0.23 0.51 0.96"    # Blue 500

STYLES = {
    "TITLE": {"font": "/F1-Bold", "size": 18, "color": COLOR_WHITE},
    "HEADER": {"font": "/F1-Bold", "size": 14, "color": COLOR_BLACK},
    "SECTION_HEAD": {"font": "/F1-Bold", "size": 11, "color": COLOR_BLUE},
    "METADATA_LABEL": {"font": "/F1-Bold", "size": 9, "color": COLOR_GREY_DARK},
    "DEFAULT": {"font": "/F1", "size": 10, "color": COLOR_BLACK},
    "MONO": {"font": "/F3", "size": 9, "color": COLOR_GREY_DARK},
    "TRUE": {"font": "/F1-Bold", "size": 10, "color": COLOR_EMERALD},
    "FALSE": {"font": "/F1-Bold", "size": 10, "color": COLOR_ROSE},
    "PARTIALLY_TRUE": {"font": "/F1-Bold", "size": 10, "color": COLOR_AMBER},
    "UNVERIFIABLE": {"font": "/F1-Bold", "size": 10, "color": COLOR_GREY_LIGHT},
}

class StyledLine:
    def __init__(self, text: str, style: str = "DEFAULT", indent: int = 0):
        self.text = text
        self.style = style
        self.indent = indent

def build_report_pdf(report: dict) -> bytes:
    lines = _build_report_lines(report)
    pages = _paginate_lines(lines)
    return _render_pdf(pages)

def _build_report_lines(report: dict) -> list[StyledLine]:
    evaluation = report.get("evaluation") or build_report_diagnostics(report)
    claims = report.get("claims", [])
    results = report.get("results", [])
    verdict_counts = Counter(result.get("verdict", "UNVERIFIABLE") for result in results)
    average_confidence = sum(_safe_float(r.get("confidence")) for r in results) / len(results) if results else 0
    
    lines: list[StyledLine] = []
    
    # Title Section (will be rendered with background)
    lines.append(StyledLine("FactLens Verification Report", "TITLE"))
    lines.append(StyledLine(f"Report ID: {report.get('id', 'unknown')}", "TITLE"))
    
    # Diagnostics Grid
    lines.append(StyledLine("RUN DIAGNOSTICS", "SECTION_HEAD"))
    lines.append(StyledLine(f"Completed: {_format_timestamp(report.get('completed_at'))}", "METADATA_LABEL"))
    lines.append(StyledLine(f"Average Confidence: {round(average_confidence * 100)}% | Verdicts: {len(results)}", "DEFAULT"))
    
    mix_text = "Verdict Mix: " + ", ".join(f"{VERDICT_LABELS.get(k, k)}: {verdict_counts.get(k, 0)}" for k in ["TRUE", "FALSE", "PARTIALLY_TRUE", "UNVERIFIABLE"])
    lines.append(StyledLine(mix_text, "DEFAULT"))
    
    # Signal Summary
    lines.append(StyledLine("AUTHENTICITY SIGNALS", "SECTION_HEAD"))
    _add_detection_lines(lines, "Source Content", report.get("ai_detection"), AI_LABELS)
    _add_detection_lines(lines, "Visual Media", report.get("media_detection"), MEDIA_LABELS)

    # Detailed Claim Review
    lines.append(StyledLine("CLAIM-BY-CLAIM ANALYSIS", "SECTION_HEAD"))
    if not results:
        lines.append(StyledLine("No claims verified yet.", "DEFAULT"))
    
    for idx, res in enumerate(results, start=1):
        verdict = res.get("verdict", "UNVERIFIABLE")
        lines.append(StyledLine(f"CLAIM {idx}: {VERDICT_LABELS.get(verdict, verdict)}", verdict))
        
        # Wrapped Statement
        _wrap_and_add(lines, f"Statement: {res.get('claim', '')}", "DEFAULT", indent=0)
        
        # Reasoning
        if res.get("reasoning"):
            _wrap_and_add(lines, f"Reasoning: {res['reasoning']}", "MONO", indent=2)
            
        steps = res.get("reasoning_steps") or []
        if steps:
            lines.append(StyledLine("Audit Trail (Chain of Thought):", "METADATA_LABEL", indent=2))
            for s_idx, step in enumerate(steps, start=1):
                _wrap_and_add(lines, f"{s_idx}. {step}", "MONO", indent=4)

        # Sources
        top_sources = (res.get("evidence_used") or [])[:3]
        if top_sources:
            lines.append(StyledLine("Top Evidence:", "METADATA_LABEL", indent=2))
            for s_idx, source in enumerate(top_sources, start=1):
                label = f"{source.get('domain', 'Web')} | {source.get('title', 'Untitled')}"
                lines.append(StyledLine(f"  [{s_idx}] {label}", "DEFAULT", indent=2))
                if source.get("url"):
                    lines.append(StyledLine(f"      {source['url']}", "MONO", indent=2))
        
        lines.append(StyledLine("-" * 60, "MONO"))

    return lines

def _wrap_and_add(lines: list[StyledLine], text: str, style: str, indent: int = 0):
    wrapped = textwrap.wrap(text, width=TEXT_WRAP_WIDTH - indent)
    for line in wrapped:
        lines.append(StyledLine(line, style, indent))

def _add_detection_lines(lines: list[StyledLine], title: str, detection: dict | None, labels: dict):
    if not detection:
        lines.append(StyledLine(f"{title}: No detection data.", "DEFAULT"))
        return
    label = labels.get(detection.get("label"), labels.get("UNKNOWN", "Unknown"))
    prob = round(_safe_float(detection.get("ai_probability")) * 100)
    lines.append(StyledLine(f"{title}: {label} ({prob}% probability)", "DEFAULT"))
    if detection.get("explanation"):
        _wrap_and_add(lines, str(detection["explanation"]), "MONO", indent=2)

def _paginate_lines(lines: list[StyledLine]) -> list[list[StyledLine]]:
    # Simple pagination
    per_page = 40
    pages = []
    for i in range(0, len(lines), per_page):
        pages.append(lines[i:i+per_page])
    return pages

def _render_pdf(pages: list[list[StyledLine]]) -> bytes:
    num_pages = len(pages)
    
    # PDF Objects:
    # 1: Catalog
    # 2: Pages
    # 3: Font F1 (Helvetica)
    # 4: Font F2 (Helvetica-Bold)
    # 5: Font F3 (Courier)
    
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Count {num_pages} /Kids [{' '.join(f'{(i*2)+6} 0 R' for i in range(num_pages))}] >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    ]
    
    for i, page_lines in enumerate(pages):
        page_id = (i * 2) + 6
        content_id = (i * 2) + 7
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode()
        )
        stream = _build_page_stream(page_lines, i + 1, num_pages)
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")

    # Header and XRef
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects):
        offsets.append(len(output))
        output.extend(f"{i+1} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
        
    xref_start = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        output.extend(f"{off:010d} 00000 n \n".encode())
    
    output.extend(
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF".encode()
    )
    return bytes(output)

def _build_page_stream(lines: list[StyledLine], page_num: int, total_pages: int) -> bytes:
    # Use Helvetica-Bold as F2
    FONT_MAP = {
        "/F1-Bold": "/F2",
        "/F1": "/F1",
        "/F3": "/F3",
    }
    
    cmds = []
    
    # 1. Header Background (Page 1 only)
    if page_num == 1:
        cmds.append(b"q 0.1 0.3 0.6 rg 0 680 612 112 re f Q") 

    # 2. Text Content
    cmds.append(b"BT")
    
    y = 740
    for line in lines:
        style = STYLES.get(line.style, STYLES["DEFAULT"])
        font_name = FONT_MAP.get(style["font"], "/F1")
        
        # Absolute positioning for each line to avoid cumulative drift
        x = LEFT_MARGIN + (line.indent * 12)
        
        # Format: x y Tm font size Tf color rg (text) Tj
        cmds.append(f"1 0 0 1 {x} {y} Tm".encode())
        cmds.append(f"{style['color']} rg".encode())
        cmds.append(f"{font_name} {style['size']} Tf".encode())
        cmds.append(f"({_escape_pdf_text(line.text)}) Tj".encode())
        
        # Move y down
        if line.style == "TITLE":
            y -= 22
        elif line.style == "SECTION_HEAD":
            y -= 30
        else:
            y -= LINE_HEIGHT
            
        if y < BOTTOM_MARGIN:
            break
            
    # Page Number at bottom
    cmds.append(f"1 0 0 1 {PAGE_WIDTH - 120} 35 Tm 0.5 0.5 0.5 rg /F1 8 Tf (Page {page_num} of {total_pages}) Tj".encode())
    cmds.append(b"ET")
    
    return b"\n".join(cmds)

def _escape_pdf_text(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

def _safe_float(v: any) -> float:
    try: return float(v or 0)
    except: return 0.0

def _format_timestamp(v: str | None) -> str:
    return v or "N/A"

def _title_case(v: str) -> str:
    return str(v or "unknown").replace("_", " ").title()

# Add legacy labels back if needed by functions I didn't fully rewrite
AI_LABELS = { "LIKELY_AI": "Likely AI", "POSSIBLY_AI": "Possibly AI", "LIKELY_HUMAN": "Human", "UNKNOWN": "Unknown" }
MEDIA_LABELS = { "LIKELY_AI": "Synthetic", "POSSIBLY_AI": "Possibly Synthetic", "LIKELY_HUMAN": "Real", "UNKNOWN": "Unknown" }
VERDICT_LABELS = { "TRUE": "VERIFIED TRUE", "FALSE": "FACTUALLY FALSE", "PARTIALLY_TRUE": "PARTIALLY TRUE", "UNVERIFIABLE": "UNVERIFIABLE" }
