from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import textwrap

from storage.report_diagnostics import build_report_diagnostics

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT_MARGIN = 54
TOP_MARGIN = 748
LINE_HEIGHT = 14
MAX_LINES_PER_PAGE = 46
TEXT_WRAP_WIDTH = 94

AI_LABELS = {
    "LIKELY_AI": "Likely AI-generated text",
    "POSSIBLY_AI": "Possibly AI-generated text",
    "LIKELY_HUMAN": "Likely human-written text",
    "UNKNOWN": "Text authenticity unavailable",
}

MEDIA_LABELS = {
    "LIKELY_SYNTHETIC": "Likely synthetic-media signal",
    "POSSIBLY_SYNTHETIC": "Possible synthetic-media signal",
    "NO_STRONG_SIGNAL": "No strong synthetic-media signal",
    "LIKELY_AI": "Likely synthetic-media signal",
    "POSSIBLY_AI": "Possible synthetic-media signal",
    "LIKELY_HUMAN": "No strong synthetic-media signal",
    "UNKNOWN": "Visual authenticity unavailable",
}

VERDICT_LABELS = {
    "TRUE": "True",
    "FALSE": "False",
    "PARTIALLY_TRUE": "Partially true",
    "UNVERIFIABLE": "Unverifiable",
}


def build_report_pdf(report: dict) -> bytes:
    lines = _build_report_lines(report)
    pages = _paginate_lines(lines)
    return _render_pdf(pages)


def _build_report_lines(report: dict) -> list[str]:
    evaluation = report.get("evaluation") or build_report_diagnostics(report)
    claims = report.get("claims", [])
    results = report.get("results", [])
    verdict_counts = Counter(result.get("verdict", "UNVERIFIABLE") for result in results)
    average_confidence = (
        sum(float(result.get("confidence", 0.0) or 0.0) for result in results) / len(results)
        if results
        else 0.0
    )
    conflict_count = sum(1 for result in results if result.get("conflict_detected"))
    time_sensitive_count = sum(1 for result in results if result.get("time_sensitive"))

    lines: list[str] = []
    _add_heading(lines, "Report summary")
    lines.append(f"Report ID: {report.get('id', 'unknown')}")
    lines.append(f"Status: {_title_case(report.get('status', 'unknown'))}")
    lines.append(f"Created: {_format_timestamp(report.get('created_at'))}")
    lines.append(f"Updated: {_format_timestamp(report.get('updated_at'))}")
    lines.append(f"Completed: {_format_timestamp(report.get('completed_at'))}")
    lines.append(f"Input mode: {_title_case(report.get('input_mode', 'text'))}")
    _add_wrapped_line(lines, "Input: ", report.get("input_value") or "No input captured.")
    lines.append(f"Claims extracted: {len(claims)}")
    lines.append(f"Completed verdicts: {len(results)}")
    lines.append(f"Average confidence: {round(average_confidence * 100)}%")
    lines.append(f"Claims with conflicting evidence: {conflict_count}")
    lines.append(f"Time-sensitive claims: {time_sensitive_count}")
    lines.append(
        "Verdict mix: "
        + ", ".join(
            f"{VERDICT_LABELS[key]} {verdict_counts.get(key, 0)}"
            for key in ("TRUE", "FALSE", "PARTIALLY_TRUE", "UNVERIFIABLE")
        )
    )

    _add_heading(lines, "Run diagnostics")
    _add_wrapped_line(
        lines,
        "Extraction: ",
        (
            f"mode {_title_case(str(evaluation.get('extraction', {}).get('mode', 'unknown')).replace('_', ' '))}; "
            f"warnings {evaluation.get('extraction', {}).get('warning_count', 0)}; "
            f"compound claims {evaluation.get('extraction', {}).get('compound_claim_count', 0)}; "
            f"atomic claim rate {round(float(evaluation.get('extraction', {}).get('atomic_claim_rate', 0.0) or 0.0) * 100)}%"
        ),
    )
    _add_wrapped_line(
        lines,
        "Retrieval: ",
        (
            f"recovery on {evaluation.get('retrieval', {}).get('recovery_triggered_claim_count', 0)} claim(s); "
            f"avg queries {evaluation.get('retrieval', {}).get('avg_query_attempt_count', 0)}; "
            f"provider instability on {evaluation.get('retrieval', {}).get('provider_instability_claim_count', 0)} claim(s)"
        ),
    )
    top_contradiction = (evaluation.get("verification", {}) or {}).get("top_contradiction_type") or {}
    _add_wrapped_line(
        lines,
        "Verification: ",
        (
            f"average confidence {round(float(evaluation.get('summary', {}).get('average_confidence', 0.0) or 0.0) * 100)}%; "
            f"conservative verdict rate {round(float(evaluation.get('summary', {}).get('conservative_claim_rate', 0.0) or 0.0) * 100)}%; "
            f"top contradiction {top_contradiction.get('label', 'none')}"
        ),
    )
    quality_flags = [str(item).strip() for item in evaluation.get("quality_flags", []) if str(item).strip()]
    if quality_flags:
        _add_wrapped_line(lines, "Quality flags: ", "; ".join(quality_flags))

    _add_heading(lines, "Authenticity signals")
    _add_detection_lines(lines, "Submitted text", report.get("ai_detection"), AI_LABELS)
    _add_detection_lines(lines, "Detected media", report.get("media_detection"), MEDIA_LABELS)

    _add_heading(lines, "Claim review")
    if not results:
        lines.append("No completed claim verdicts were available in this saved report.")
    for index, result in enumerate(results, start=1):
        verdict_label = VERDICT_LABELS.get(result.get("verdict"), _title_case(result.get("verdict", "Unknown")))
        confidence = round(float(result.get("confidence", 0.0) or 0.0) * 100)
        claim_type = _title_case(str(result.get("claim_type", "entity")).replace("_", " "))
        lines.append(f"Claim {index}: {verdict_label} ({confidence}% confidence)")
        lines.append(
            "Metadata: "
            f"type {claim_type}; "
            f"time-sensitive {'yes' if result.get('time_sensitive') else 'no'}; "
            f"conflict detected {'yes' if result.get('conflict_detected') else 'no'}"
        )
        _add_wrapped_line(lines, "Statement: ", result.get("claim") or "No claim text available.")

        claim_record = next(
            (claim for claim in claims if claim.get("id") == result.get("claim_id")),
            None,
        )
        context = (claim_record or {}).get("context")
        if context and context != result.get("claim"):
            _add_wrapped_line(lines, "Original context: ", context)

        _add_wrapped_line(lines, "Reasoning: ", result.get("reasoning") or "No reasoning returned.")

        risk_flags = result.get("risk_flags") or []
        if risk_flags:
            _add_wrapped_line(lines, "Risk flags: ", "; ".join(str(flag) for flag in risk_flags))

        query_variants = result.get("query_variants") or []
        if query_variants:
            queries = "; ".join(
                f"{_title_case(str(query.get('objective', 'query')).replace('_', ' '))}: {query.get('query', '')}"
                for query in query_variants
                if query.get("query")
            )
            if queries:
                _add_wrapped_line(lines, "Search strategy: ", queries)

        retrieval_summary = result.get("retrieval_summary") or {}
        lines.append(
            "Evidence summary: "
            f"{len(result.get('supporting_evidence') or [])} supporting, "
            f"{len(result.get('conflicting_evidence') or [])} conflicting, "
            f"{len(result.get('mixed_evidence') or [])} mixed, "
            f"{len(result.get('neutral_evidence') or [])} low-signal; "
            f"{retrieval_summary.get('distinct_domain_count', 0)} domains; "
            f"freshest evidence {retrieval_summary.get('freshest_date') or 'unknown'}"
        )
        contradiction_types = result.get("conflict_summary", {}).get("contradiction_types") or []
        if contradiction_types:
            _add_wrapped_line(
                lines,
                "Contradiction types: ",
                "; ".join(str(item.get("label") or "Unknown disagreement") for item in contradiction_types),
            )
        temporal_context = result.get("temporal_context") or {}
        if temporal_context.get("summary"):
            _add_wrapped_line(lines, "Temporal context: ", str(temporal_context["summary"]))
        subclaim_results = result.get("subclaim_results") or []
        subclaim_summary = result.get("subclaim_summary") or {}
        if subclaim_results:
            _add_wrapped_line(
                lines,
                "Subclaim synthesis: ",
                str(subclaim_summary.get("synthesis_note") or f"{len(subclaim_results)} subclaims reviewed."),
            )
            for subclaim_index, subclaim in enumerate(subclaim_results[:3], start=1):
                verdict = VERDICT_LABELS.get(subclaim.get("verdict"), _title_case(subclaim.get("verdict", "unknown")))
                confidence_label = round(float(subclaim.get("confidence", 0.0) or 0.0) * 100)
                _add_wrapped_line(
                    lines,
                    f"Subclaim {subclaim_index}: ",
                    f"{verdict} ({confidence_label}% confidence) | {subclaim.get('claim') or 'No subclaim text available.'}",
                )

        top_sources = (result.get("evidence_used") or [])[:2]
        if top_sources:
            for source_index, source in enumerate(top_sources, start=1):
                source_parts = [
                    str(source.get("title") or "Untitled source"),
                    str(source.get("domain") or "unknown domain"),
                ]
                if source.get("published_label"):
                    source_parts.append(str(source["published_label"]))
                _add_wrapped_line(lines, f"Top source {source_index}: ", " | ".join(source_parts))
                if source.get("url"):
                    _add_wrapped_line(lines, "Source URL: ", str(source["url"]))

        evidence_provenance = result.get("evidence_provenance") or []
        for proof_index, proof in enumerate(evidence_provenance[:2], start=1):
            snapshot_bits = [str(proof.get("snapshot_id") or "snapshot unavailable")]
            if proof.get("captured_at"):
                snapshot_bits.append(str(proof["captured_at"]))
            if proof.get("content_hash"):
                snapshot_bits.append(f"hash {proof['content_hash']}")
            _add_wrapped_line(lines, f"Snapshot proof {proof_index}: ", " | ".join(snapshot_bits))
            if proof.get("primary_quote"):
                _add_wrapped_line(lines, "Grounded quote: ", str(proof["primary_quote"]))

        lines.append("")

    return lines


def _add_heading(lines: list[str], title: str) -> None:
    if lines:
        lines.append("")
    lines.append(title.upper())
    lines.append("-" * len(title))


def _add_detection_lines(
    lines: list[str],
    title: str,
    detection: dict | None,
    label_map: dict[str, str],
) -> None:
    if not detection:
        lines.append(f"{title}: unavailable")
        return

    label = label_map.get(detection.get("label"), label_map["UNKNOWN"])
    probability = detection.get("ai_probability")
    probability_label = (
        f"{round(float(probability) * 100)}% AI probability"
        if isinstance(probability, (int, float))
        else "probability unavailable"
    )
    lines.append(f"{title}: {label} ({probability_label})")

    if detection.get("explanation"):
        _add_wrapped_line(lines, "Summary: ", str(detection["explanation"]))

    if detection.get("analysis_mode"):
        _add_wrapped_line(
            lines,
            "Method: ",
            _title_case(str(detection.get("analysis_mode", "unknown")).replace("_", " ")),
        )

    signals = [str(signal) for signal in detection.get("signals_found") or [] if str(signal).strip()]
    if signals:
        _add_wrapped_line(lines, "Signals: ", "; ".join(signals))

    warnings = [str(item) for item in detection.get("warnings") or [] if str(item).strip()]
    if warnings:
        _add_wrapped_line(lines, "Warnings: ", "; ".join(warnings))

    limitations = [str(item) for item in detection.get("limitations") or [] if str(item).strip()]
    if limitations:
        _add_wrapped_line(lines, "Limitations: ", "; ".join(limitations))

    if detection.get("media_url"):
        _add_wrapped_line(lines, "Media URL: ", str(detection["media_url"]))


def _add_wrapped_line(lines: list[str], prefix: str, value: str) -> None:
    wrapped = textwrap.wrap(
        str(value),
        width=TEXT_WRAP_WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=True,
        break_on_hyphens=False,
    )
    if not wrapped:
        lines.append(prefix.rstrip())
        return
    lines.extend(wrapped)


def _paginate_lines(lines: list[str]) -> list[list[str]]:
    page_body_size = MAX_LINES_PER_PAGE - 3
    pages: list[list[str]] = []
    current_page: list[str] = []

    for line in lines:
        if len(current_page) >= page_body_size:
            pages.append(current_page)
            current_page = []
        current_page.append(line)

    if current_page or not pages:
        pages.append(current_page)

    total_pages = len(pages)
    return [
        [
            "FactLens Verification Report" if index == 0 else "FactLens Verification Report (continued)",
            f"Page {index + 1} of {total_pages}",
            "",
            *page_lines,
        ]
        for index, page_lines in enumerate(pages)
    ]


def _render_pdf(pages: list[list[str]]) -> bytes:
    objects: list[bytes] = []
    kids = " ".join(f"{4 + (index * 2)} 0 R" for index in range(len(pages)))

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

    for index, page_lines in enumerate(pages):
        page_object_id = 4 + (index * 2)
        content_object_id = page_object_id + 1
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                "/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_object_id} 0 R >>"
            ).encode("ascii")
        )
        stream = _build_page_stream(page_lines)
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, content in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(content)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("ascii")
    )
    return bytes(output)


def _build_page_stream(lines: list[str]) -> bytes:
    if not lines:
        lines = ["FactLens Verification Report"]

    commands = [
        b"BT",
        b"/F1 10 Tf",
        f"{LINE_HEIGHT} TL".encode("ascii"),
        f"{LEFT_MARGIN} {TOP_MARGIN} Td".encode("ascii"),
    ]

    for index, line in enumerate(lines):
        if index:
            commands.append(b"T*")
        commands.append(f"({_escape_pdf_text(line)}) Tj".encode("latin-1"))

    commands.append(b"ET")
    return b"\n".join(commands)


def _escape_pdf_text(value: str) -> str:
    normalized = (
        str(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )
    return normalized.encode("latin-1", errors="replace").decode("latin-1")


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "Unavailable"

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return str(value)

    return parsed.astimezone(timezone.utc).strftime("%b %d, %Y %H:%M UTC")


def _title_case(value: str) -> str:
    return str(value or "unknown").replace("_", " ").strip().title()
