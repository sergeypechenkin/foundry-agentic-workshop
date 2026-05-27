"""Generate an HTML report from extracted form fields with confidence highlighting."""

import json
from pathlib import Path


def generate_html_report(
    fields: dict,
    output_path: str | Path | None = None,
    word_confidence_map: dict[str, float] | None = None,
) -> str:
    """Generate HTML document preserving document structure as collapsible tree.

    Values with confidence < 0.7 are highlighted in red.
    Values with confidence 0.7-0.9 are highlighted in orange.
    Values with confidence >= 0.9 are green.

    Args:
        fields: Normalized fields dict (may contain {value, confidence} entries).
        output_path: Optional path to write the HTML file.
        word_confidence_map: Optional OCR word→confidence mapping for the layout section.

    Returns:
        HTML string.
    """
    tree_html = _render_node(fields, depth=0)

    ocr_section = _render_ocr_section(word_confidence_map) if word_confidence_map else ""

    html = _HTML_TEMPLATE.replace("{{TREE_CONTENT}}", tree_html)
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

{{TREE_CONTENT}}

    <details class="json-section">
        <summary>Show raw JSON</summary>
        <pre>{{JSON_DATA}}</pre>
    </details>
</body>
</html>
"""
