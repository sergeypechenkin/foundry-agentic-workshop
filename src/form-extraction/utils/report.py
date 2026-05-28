"""Generate an HTML report from extracted form fields with confidence highlighting."""

import json
from pathlib import Path


def generate_html_report(
    fields: dict,
    output_path: str | Path | None = None,
    word_confidence_map: dict[str, float] | None = None,
    layout_text: str | None = None,
    llm_fields: dict | None = None,
    word_confidence_sequence: list[tuple[str, float]] | None = None,
    direct_llm_fields: dict | None = None,
) -> str:
    """Generate HTML document with pipeline stages.

    Sections:
        1. Final (normalized) — after layout + LLM + normalization
        2. LLM extraction — JSON from LLM before normalization
        2b. Direct LLM extraction — JSON from GPT-5.2 (raw document, no OCR)
        3. Layout (raw OCR) — text from Document Intelligence before LLM

    Args:
        fields: Normalized fields dict (may contain {value, confidence} entries).
        output_path: Optional path to write the HTML file.
        word_confidence_map: Optional OCR word→confidence mapping.
        layout_text: Raw text from Document Intelligence layout analysis.
        llm_fields: Fields extracted by LLM before normalization.
        word_confidence_sequence: Ordered (word, confidence) pairs for positional rendering.
        direct_llm_fields: Fields extracted by direct GPT-5.2 call (no OCR preprocessing).

    Returns:
        HTML string.
    """
    tree_html = _render_node(fields, depth=0)

    # Section 2: LLM extraction (pre-normalization JSON)
    llm_section = ""
    if llm_fields is not None:
        llm_json = _escape(json.dumps(llm_fields, indent=2, ensure_ascii=False))
        llm_section = (
            '<details class="pipeline-section" open>\n'
            '  <summary class="pipeline-title">2. LLM Extraction (before normalization)</summary>\n'
            f'  <pre class="pipeline-pre">{llm_json}</pre>\n'
            '</details>\n'
        )

    # Section 2b: Direct LLM extraction (raw document → GPT-5.2)
    direct_llm_section = ""
    if direct_llm_fields is not None:
        direct_tree_html = _render_direct_llm(direct_llm_fields)
        direct_llm_section = (
            '<details class="pipeline-section" open>\n'
            '  <summary class="pipeline-title">2b. Direct LLM Extraction (GPT-5.2, no OCR)</summary>\n'
            f'  <div style="margin-top: 0.75rem;">{direct_tree_html}</div>\n'
            '</details>\n'
        )

    # Section 3: Raw layout text with word-level confidence highlighting
    layout_section = ""
    if layout_text is not None:
        if word_confidence_sequence:
            highlighted_layout = _render_layout_with_confidence(layout_text, word_confidence_sequence)
        else:
            highlighted_layout = f'<pre class="pipeline-pre">{_escape(layout_text)}</pre>'
        layout_section = (
            '<details class="pipeline-section">\n'
            '  <summary class="pipeline-title">3. Raw OCR Layout (Document Intelligence)</summary>\n'
            f'  <div class="layout-highlighted">{highlighted_layout}</div>\n'
            '</details>\n'
        )

    ocr_section = _render_ocr_section(word_confidence_map) if word_confidence_map else ""

    html = _HTML_TEMPLATE.replace("{{TREE_CONTENT}}", tree_html)
    html = html.replace("{{LLM_SECTION}}", llm_section)
    html = html.replace("{{DIRECT_LLM_SECTION}}", direct_llm_section)
    html = html.replace("{{LAYOUT_SECTION}}", layout_section)
    html = html.replace("{{OCR_SECTION}}", ocr_section)
    html = html.replace("{{JSON_DATA}}", _escape(json.dumps(fields, indent=2, ensure_ascii=False)))

    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")

    return html


def _render_node(obj, depth: int) -> str:
    """Recursively render a dict/list/value as nested HTML sections."""
    if isinstance(obj, dict):
        # Leaf node: {value, confidence}
        if "value" in obj and "confidence" in obj and len(obj) == 2:
            return _render_value(obj["value"], obj["confidence"])
        # Section node
        html = ""
        for key, val in obj.items():
            label = _format_key(key)
            child_html = _render_node(val, depth + 1)

            if isinstance(val, dict) and not _is_leaf(val):
                # Collapsible section
                html += (
                    f'<details class="section depth-{min(depth, 3)}" open>\n'
                    f'  <summary class="section-title">{_escape(label)}</summary>\n'
                    f'  <div class="section-body">{child_html}</div>\n'
                    f'</details>\n'
                )
            elif isinstance(val, list):
                html += (
                    f'<details class="section depth-{min(depth, 3)}" open>\n'
                    f'  <summary class="section-title">{_escape(label)}</summary>\n'
                    f'  <div class="section-body">{child_html}</div>\n'
                    f'</details>\n'
                )
            else:
                # Key-value row
                html += (
                    f'<div class="field-row">\n'
                    f'  <span class="field-key">{_escape(label)}</span>\n'
                    f'  <span class="field-value">{child_html}</span>\n'
                    f'</div>\n'
                )
        return html

    elif isinstance(obj, list):
        html = ""
        for i, item in enumerate(obj):
            child_html = _render_node(item, depth + 1)
            if isinstance(item, dict) and not _is_leaf(item):
                html += (
                    f'<details class="section depth-{min(depth, 3)}" open>\n'
                    f'  <summary class="section-title">#{i + 1}</summary>\n'
                    f'  <div class="section-body">{child_html}</div>\n'
                    f'</details>\n'
                )
            else:
                html += f'<div class="list-item">{child_html}</div>\n'
        return html

    else:
        return _render_value(obj, None)


def _render_value(value, confidence: float | None) -> str:
    """Render a single value with confidence badge."""
    if value is None:
        return '<span class="value-null">—</span>'

    color, badge = _confidence_style(confidence)
    conf_str = f"{confidence:.2f}" if confidence is not None else ""

    return (
        f'<span class="value-text" style="color:{color}">{_escape(str(value))}</span>'
        f'<span class="conf-badge" style="color:{color}" title="Confidence: {conf_str}">'
        f'{badge} {conf_str}</span>'
    )


def _is_leaf(obj: dict) -> bool:
    """Check if dict is a {value, confidence} leaf."""
    return "value" in obj and "confidence" in obj and len(obj) == 2


def _format_key(key: str) -> str:
    """Format snake_case/prefixed keys to readable labels."""
    # Remove leading number prefixes like "1a_", "2b_"
    key = key.replace("_", " ").strip()
    return key.title()


def _confidence_style(confidence: float | None) -> tuple[str, str]:
    """Return (css_color, badge) for a confidence value."""
    if confidence is None:
        return "#666", ""
    if confidence < 0.7:
        return "#dc3545", "⚠️"
    if confidence < 0.9:
        return "#fd7e14", "●"
    return "#28a745", "✓"


def _escape(text: str) -> str:
    """Basic HTML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_direct_llm(data: dict) -> str:
    """Render direct LLM extraction as a flat tree (no page split).

    - Sections/subsections become collapsible <details>
    - Fields render as key-value rows with confidence coloring
    - Checkboxes show ☑/☐ icon next to label
    - Tables render headers + rows as field rows
    - Removes type/handwritten/uncertain display
    """
    # Flatten pages — collect all sections regardless of page
    pages = []
    if "document" in data and "pages" in data["document"]:
        pages = data["document"]["pages"]
    elif "pages" in data:
        pages = data["pages"]

    all_sections: list[dict] = []
    for page in pages:
        all_sections.extend(page.get("sections", []))

    if not all_sections:
        # Fallback: render as generic tree if structure is unexpected
        return _render_node(data, depth=0)

    html = ""
    for section in all_sections:
        html += _render_direct_section(section, depth=0)
    return html


def _render_direct_section(section: dict, depth: int) -> str:
    """Render a single section (with title, content, subsections)."""
    title = section.get("title") or "Untitled Section"
    conf = section.get("confidence")
    color, badge = _confidence_style(conf)

    # Section header with confidence
    title_html = f'{_escape(title)}'
    if conf is not None:
        title_html += (
            f' <span class="conf-badge" style="color:{color}" '
            f'title="Section confidence: {conf:.2f}">{badge} {conf:.2f}</span>'
        )

    html = (
        f'<details class="section depth-{min(depth, 3)}" open>\n'
        f'  <summary class="section-title">{title_html}</summary>\n'
        f'  <div class="section-body">\n'
    )

    # Render content items
    for item in section.get("content", []):
        html += _render_direct_content_item(item)

    # Render subsections recursively
    for subsection in section.get("subsections", []):
        html += _render_direct_section(subsection, depth + 1)

    html += '  </div>\n</details>\n'
    return html


def _render_direct_content_item(item: dict) -> str:
    """Render a content item (field, checkbox, text_block, table)."""
    item_type = item.get("type", "field")
    conf = item.get("confidence")

    if item_type == "checkbox":
        checked = item.get("checked")
        icon = "☑" if checked else "☐"
        label = item.get("label", "")
        color, badge = _confidence_style(conf)
        conf_str = f"{conf:.2f}" if conf is not None else ""
        return (
            f'<div class="field-row">\n'
            f'  <span class="field-key">{icon} {_escape(label)}</span>\n'
            f'  <span class="field-value">'
            f'<span class="value-text" style="color:{color}">{"Yes" if checked else "No" if checked is not None else "—"}</span>'
            f'<span class="conf-badge" style="color:{color}" title="Confidence: {conf_str}">'
            f'{badge} {conf_str}</span>'
            f'</span>\n'
            f'</div>\n'
        )

    elif item_type == "text_block":
        text = item.get("text", "")
        color, badge = _confidence_style(conf)
        conf_str = f"{conf:.2f}" if conf is not None else ""
        return (
            f'<div class="field-row">\n'
            f'  <span class="field-key">Text</span>\n'
            f'  <span class="field-value">'
            f'<span class="value-text" style="color:{color}">{_escape(text)}</span>'
            f'<span class="conf-badge" style="color:{color}" title="Confidence: {conf_str}">'
            f'{badge} {conf_str}</span>'
            f'</span>\n'
            f'</div>\n'
        )

    elif item_type == "table":
        headers = item.get("headers", [])
        rows = item.get("rows", [])
        color, badge = _confidence_style(conf)
        conf_str = f"{conf:.2f}" if conf is not None else ""
        html = ""
        # Render each row with headers as labels
        for row in rows:
            for i, cell in enumerate(row):
                label = headers[i] if i < len(headers) else f"Column {i+1}"
                html += (
                    f'<div class="field-row">\n'
                    f'  <span class="field-key">{_escape(label)}</span>\n'
                    f'  <span class="field-value">'
                    f'<span class="value-text" style="color:{color}">{_escape(str(cell))}</span>'
                    f'<span class="conf-badge" style="color:{color}" title="Confidence: {conf_str}">'
                    f'{badge} {conf_str}</span>'
                    f'</span>\n'
                    f'</div>\n'
                )
        return html

    else:
        # Default: field type
        label = item.get("label", "")
        value = item.get("value")
        color, badge = _confidence_style(conf)
        conf_str = f"{conf:.2f}" if conf is not None else ""
        value_html = f'<span class="value-text" style="color:{color}">{_escape(str(value))}</span>' if value is not None else '<span class="value-null">—</span>'
        return (
            f'<div class="field-row">\n'
            f'  <span class="field-key">{_escape(label)}</span>\n'
            f'  <span class="field-value">'
            f'{value_html}'
            f'<span class="conf-badge" style="color:{color}" title="Confidence: {conf_str}">'
            f'{badge} {conf_str}</span>'
            f'</span>\n'
            f'</div>\n'
        )


def _render_layout_with_confidence(layout_text: str, word_sequence: list[tuple[str, float]]) -> str:
    """Render layout text with each word colored by its positional OCR confidence.

    Uses the ordered word_sequence from Document Intelligence so each word instance
    gets its own confidence (not the aggregated min across all occurrences).
    Uses index-based lookahead to avoid losing sync when tokenization differs.
    """
    import re as _re

    def _color_for_conf(conf: float) -> str:
        if conf < 0.7:
            return "#dc3545"
        if conf < 0.9:
            return "#fd7e14"
        return "#28a745"

    def _normalize(s: str) -> str:
        """Normalize text for matching: strip punctuation, lowercase."""
        return s.strip('.,;:!?()[]"\'-\u2013\u2014/\\').lower()

    # Use index-based approach to allow lookahead without losing sync
    seq_idx = 0
    max_lookahead = 10  # how far ahead to search in sequence for a match

    lines = layout_text.split('\n')
    html_lines = []
    for line in lines:
        tokens = _re.split(r'(\s+)', line)
        html_tokens = []
        for token in tokens:
            if not token.strip():
                html_tokens.append(_escape(token))
                continue

            # Try to match token against word_sequence[seq_idx..seq_idx+max_lookahead]
            conf = None
            norm_token = _normalize(token)

            if seq_idx < len(word_sequence) and norm_token:
                # Try exact match at current position first
                seq_text, seq_conf = word_sequence[seq_idx]
                norm_seq = _normalize(seq_text)

                if norm_token == norm_seq or norm_token in norm_seq or norm_seq in norm_token:
                    conf = seq_conf
                    seq_idx += 1
                else:
                    # Lookahead: search ahead for a match
                    end = min(seq_idx + max_lookahead, len(word_sequence))
                    for k in range(seq_idx + 1, end):
                        sk_text, sk_conf = word_sequence[k]
                        norm_sk = _normalize(sk_text)
                        if norm_token == norm_sk or norm_token in norm_sk or norm_sk in norm_token:
                            conf = sk_conf
                            seq_idx = k + 1
                            break

            if conf is not None:
                color = _color_for_conf(conf)
                html_tokens.append(
                    f'<span class="ocr-hl" style="color:{color}" '
                    f'title="{_escape(token)}: {conf:.3f}">'
                    f'{_escape(token)}</span>'
                )
            else:
                html_tokens.append(f'<span class="ocr-hl" style="color:#f8f8f2">{_escape(token)}</span>')
        html_lines.append(''.join(html_tokens))

    return '<pre class="pipeline-pre layout-conf">' + '\n'.join(html_lines) + '</pre>'


def _render_ocr_section(word_confidence_map: dict[str, float]) -> str:
    """Render a collapsible OCR word confidence table sorted by confidence (lowest first)."""
    sorted_words = sorted(word_confidence_map.items(), key=lambda x: x[1])
    total = len(sorted_words)
    low = sum(1 for _, c in sorted_words if c < 0.7)
    med = sum(1 for _, c in sorted_words if 0.7 <= c < 0.9)
    high = total - low - med

    rows = ""
    for word, conf in sorted_words:
        color, badge = _confidence_style(conf)
        rows += (
            f'<tr>'
            f'<td class="ocr-word">{_escape(word)}</td>'
            f'<td style="color:{color}">{badge} {conf:.3f}</td>'
            f'</tr>\n'
        )

    return (
        f'<details class="ocr-section">\n'
        f'  <summary>OCR Word Confidence '
        f'<span class="ocr-stats">'
        f'({total} words: '
        f'<span style="color:#28a745">{high} high</span>, '
        f'<span style="color:#fd7e14">{med} medium</span>, '
        f'<span style="color:#dc3545">{low} low</span>)'
        f'</span></summary>\n'
        f'  <div class="ocr-table-wrap">\n'
        f'    <table class="ocr-table">\n'
        f'      <thead><tr><th>Word</th><th>Confidence</th></tr></thead>\n'
        f'      <tbody>{rows}</tbody>\n'
        f'    </table>\n'
        f'  </div>\n'
        f'</details>\n'
    )


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Form Extraction Report</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0; padding: 2rem;
            background: #f8f9fa; color: #212529;
        }
        h1 { color: #343a40; margin-bottom: 0.3rem; }
        .subtitle { color: #6c757d; margin-bottom: 1.5rem; font-size: 0.9rem; }
        .legend {
            display: flex; gap: 1.5rem; margin-bottom: 1.5rem;
            font-size: 0.82rem; color: #495057;
        }
        .legend span { display: flex; align-items: center; gap: 0.3rem; }

        /* Tree structure */
        .section {
            border-left: 3px solid #dee2e6;
            margin: 0.4rem 0 0.4rem 0.5rem;
            padding-left: 1rem;
        }
        .section.depth-0 { border-left-color: #343a40; }
        .section.depth-1 { border-left-color: #6c757d; }
        .section.depth-2 { border-left-color: #adb5bd; }
        .section.depth-3 { border-left-color: #dee2e6; }

        .section-title {
            cursor: pointer;
            font-weight: 600;
            font-size: 0.95rem;
            padding: 0.3rem 0;
            color: #343a40;
            user-select: none;
        }
        .section.depth-0 > summary { font-size: 1.1rem; }
        .section.depth-1 > summary { font-size: 1rem; }

        .section-body { padding: 0.2rem 0; }

        /* Field rows */
        .field-row {
            display: flex;
            align-items: baseline;
            padding: 0.25rem 0;
            gap: 0.75rem;
            border-bottom: 1px solid #f1f3f5;
        }
        .field-row:hover { background: #f1f3f5; border-radius: 4px; }
        .field-key {
            min-width: 180px;
            font-size: 0.85rem;
            color: #495057;
            font-weight: 500;
            flex-shrink: 0;
        }
        .field-value {
            display: flex; align-items: center; gap: 0.5rem;
            font-family: 'Cascadia Code', 'Fira Code', monospace;
            font-size: 0.85rem;
        }
        .value-null { color: #adb5bd; font-style: italic; }
        .value-text { font-weight: 500; }
        .conf-badge { font-size: 0.75rem; white-space: nowrap; }

        .list-item {
            padding: 0.2rem 0 0.2rem 1rem;
            border-left: 2px solid #e9ecef;
            margin: 0.2rem 0;
        }

        /* JSON toggle */
        details.json-section { margin-top: 2rem; }
        details.json-section summary {
            cursor: pointer; color: #6c757d; font-size: 0.82rem;
        }
        pre {
            background: #272822; color: #f8f8f2;
            padding: 1rem; border-radius: 6px;
            overflow-x: auto; font-size: 0.78rem;
            max-height: 500px;
        }

        /* OCR section */
        .ocr-section { margin-top: 1.5rem; margin-bottom: 1.5rem; }
        .ocr-section > summary {
            cursor: pointer; font-weight: 600; font-size: 0.95rem;
            color: #343a40; padding: 0.3rem 0;
        }
        .ocr-stats { font-weight: 400; font-size: 0.82rem; color: #6c757d; }
        .ocr-table-wrap { max-height: 400px; overflow-y: auto; margin-top: 0.5rem; }
        .ocr-table {
            width: 100%; border-collapse: collapse; font-size: 0.82rem;
        }
        .ocr-table th {
            text-align: left; border-bottom: 2px solid #dee2e6;
            padding: 0.3rem 0.5rem; color: #495057; position: sticky; top: 0;
            background: #f8f9fa;
        }
        .ocr-table td { padding: 0.2rem 0.5rem; border-bottom: 1px solid #f1f3f5; }
        .ocr-table tr:hover td { background: #f1f3f5; }
        .ocr-word { font-family: 'Cascadia Code', 'Fira Code', monospace; }

        /* Pipeline sections */
        .pipeline-section {
            margin: 1.5rem 0;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 1rem;
            background: #fff;
        }
        .pipeline-title {
            cursor: pointer;
            font-weight: 700;
            font-size: 1.05rem;
            color: #343a40;
        }
        .pipeline-pre {
            background: #272822; color: #f8f8f2;
            padding: 1rem; border-radius: 6px;
            overflow-x: auto; font-size: 0.78rem;
            max-height: 500px; white-space: pre-wrap;
            word-break: break-word; margin-top: 0.75rem;
        }
        .layout-highlighted { margin-top: 0.75rem; }
        .layout-conf { background: #1e1e1e; }
        .ocr-hl { cursor: default; }
    </style>
</head>
<body>
    <h1>Form Extraction Report</h1>
    <p class="subtitle">Structured extraction with OCR confidence scores</p>
    <div class="legend">
        <span style="color:#28a745">✓ High (&ge;0.90)</span>
        <span style="color:#fd7e14">● Medium (0.70–0.89)</span>
        <span style="color:#dc3545">⚠️ Low (&lt;0.70)</span>
        <span style="color:#666">— No data</span>
    </div>

{{OCR_SECTION}}

    <details class="pipeline-section" open>
        <summary class="pipeline-title">1. Final Result (after normalization)</summary>
        <div style="margin-top: 0.75rem;">{{TREE_CONTENT}}</div>
    </details>

{{LLM_SECTION}}

{{DIRECT_LLM_SECTION}}

{{LAYOUT_SECTION}}

    <details class="json-section">
        <summary>Show raw JSON (final)</summary>
        <pre>{{JSON_DATA}}</pre>
    </details>
</body>
</html>
"""
