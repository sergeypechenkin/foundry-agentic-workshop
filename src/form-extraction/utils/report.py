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
    editable: bool = False,
    editor_data: dict | None = None,
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
        editable: If True, render an editable reconstruction UI from direct extraction data.
        editor_data: Optional explicit data source for editable mode.

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

    editor_section = ""
    if editable:
        editor_source = editor_data if editor_data is not None else fields
        if editor_source is not None:
            editor_section = _render_editable_form(editor_source)
        else:
            editor_section = (
                '<details class="pipeline-section" open>\n'
                '  <summary class="pipeline-title">Editable Form</summary>\n'
                '  <div style="margin-top: 0.75rem; color:#6c757d;">'
                'Direct LLM data was not available, so no editable form could be rendered.'
                '</div>\n'
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
    html = html.replace("{{EDITOR_SECTION}}", editor_section)
    html = html.replace("{{LLM_SECTION}}", llm_section)
    html = html.replace("{{DIRECT_LLM_SECTION}}", direct_llm_section)
    html = html.replace("{{LAYOUT_SECTION}}", layout_section)
    html = html.replace("{{OCR_SECTION}}", ocr_section)
    html = html.replace("{{JSON_DATA}}", _escape(json.dumps(fields, indent=2, ensure_ascii=False)))
    html = html.replace("{{EDITOR_JSON}}", _json_script_payload(editor_data if editor_data is not None else fields))
    html = html.replace("{{EDITOR_SCRIPT}}", _build_editor_script())

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
    return isinstance(obj, dict) and "value" in obj and "confidence" in obj


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


def _render_editable_form(data: dict) -> str:
    """Render an editable reconstruction of the direct extraction structure."""
    if _looks_like_normalized_tree(data):
        return _render_editable_normalized_form(data)

    if "document" in data and "pages" in data["document"]:
        pages = data["document"]["pages"]
    elif "pages" in data:
        pages = data["pages"]
    else:
        pages = []

    html = (
        '<details class="pipeline-section" open>\n'
        '  <summary class="pipeline-title">Editable Form</summary>\n'
        '  <div style="margin-top: 0.75rem;">\n'
        '    <div class="editor-toolbar">\n'
        '      <button type="button" class="editor-button" data-action="download">Download JSON</button>\n'
        '      <button type="button" class="editor-button editor-secondary" data-action="copy">Copy JSON</button>\n'
        '      <button type="button" class="editor-button editor-secondary" data-action="reset">Reset</button>\n'
        '      <span class="editor-status" id="editor-status">Ready</span>\n'
        '    </div>\n'
        '    <form id="editable-form" class="editable-form">\n'
    )

    for page_index, page in enumerate(pages):
        page_number = page.get("page_number", page_index + 1)
        html += (
            f'<details class="editor-page" open>\n'
            f'  <summary class="editor-page-title">Page {page_number}</summary>\n'
            f'  <div class="editor-page-body">\n'
        )
        for section_index, section in enumerate(page.get("sections", [])):
            html += _render_editable_section(section, ["document", "pages", page_index, "sections", section_index])
        html += '  </div>\n</details>\n'

    html += (
        '    </form>\n'
        '  </div>\n'
        '</details>\n'
    )
    return html


def _render_editable_normalized_form(data: dict) -> str:
    """Render an editable form from normalized OCR+LLM output."""
    return (
        '<details class="pipeline-section" open>\n'
        '  <summary class="pipeline-title">Editable Form</summary>\n'
        '  <div style="margin-top: 0.75rem;">\n'
        '    <div class="editor-toolbar">\n'
        '      <button type="button" class="editor-button" data-action="download">Download JSON</button>\n'
        '      <button type="button" class="editor-button editor-secondary" data-action="copy">Copy JSON</button>\n'
        '      <button type="button" class="editor-button editor-secondary" data-action="reset">Reset</button>\n'
        '      <span class="editor-status" id="editor-status">Ready</span>\n'
        '    </div>\n'
        '    <form id="editable-form" class="editable-form paper-form">\n'
        f'{_render_editable_normalized_node(data, [])}'
        '    </form>\n'
        '  </div>\n'
        '</details>\n'
    )


def _render_editable_normalized_node(obj, path: list) -> str:
    if isinstance(obj, dict):
        if _is_leaf(obj):
            return _render_editable_leaf(obj, path, label=None)

        html = ""
        for key, value in obj.items():
            label = _format_key(key)
            child_path = path + [key]
            if isinstance(value, dict) and _is_leaf(value):
                html += _render_editable_leaf(value, child_path, label)
            elif isinstance(value, dict) and not _is_leaf(value):
                html += (
                    f'<details class="editor-section paper-section depth-{min(len(child_path), 3)}" open>\n'
                    f'  <summary class="section-title paper-section-title">{_escape(label)}</summary>\n'
                    f'  <div class="section-body">{_render_editable_normalized_node(value, child_path)}</div>\n'
                    f'</details>\n'
                )
            elif isinstance(value, list):
                html += (
                    f'<details class="editor-section paper-section depth-{min(len(child_path), 3)}" open>\n'
                    f'  <summary class="section-title paper-section-title">{_escape(label)}</summary>\n'
                    f'  <div class="section-body">{_render_editable_normalized_node(value, child_path)}</div>\n'
                    f'</details>\n'
                )
            else:
                html += _render_editable_generic_value(value, child_path, label)
        return html

    if isinstance(obj, list):
        html = ""
        for index, item in enumerate(obj):
            item_path = path + [index]
            item_label = f'#{index + 1}'
            if isinstance(item, dict) and _is_leaf(item):
                html += _render_editable_leaf(item, item_path, item_label)
            elif isinstance(item, dict) and not _is_leaf(item):
                html += (
                    f'<details class="editor-section paper-section paper-repeat depth-{min(len(item_path), 3)}" open>\n'
                    f'  <summary class="section-title paper-section-title">{item_label}</summary>\n'
                    f'  <div class="section-body">{_render_editable_normalized_node(item, item_path)}</div>\n'
                    f'</details>\n'
                )
            elif isinstance(item, list):
                html += (
                    f'<details class="editor-section paper-section paper-repeat depth-{min(len(item_path), 3)}" open>\n'
                    f'  <summary class="section-title paper-section-title">{item_label}</summary>\n'
                    f'  <div class="section-body">{_render_editable_normalized_node(item, item_path)}</div>\n'
                    f'</details>\n'
                )
            else:
                html += _render_editable_generic_value(item, item_path, item_label)
        return html

    return _render_editable_generic_value(obj, path, _format_key(str(path[-1])) if path else "Value")


def _render_editable_leaf(obj: dict, path: list, label: str | None) -> str:
    value = obj.get("value")
    conf = obj.get("confidence")
    color, badge = _confidence_style(conf)
    level = _confidence_level(conf)
    conf_str = f"{conf:.2f}" if conf is not None else ""
    value_text = "" if value is None else str(value)
    path_attr = _escape(json.dumps(path + ["value"], ensure_ascii=False))
    title = _escape(label or _format_key(str(path[-1])) if path else "Value")
    return (
        f'<div class="editor-row paper-row confidence-{level}" data-kind="field" style="--confidence-color:{color}">\n'
        f'  <div class="editor-label">'
        f'<span class="editor-label-text">{title}</span>'
        f'<span class="conf-badge paper-conf" style="color:{color}" title="Confidence: {conf_str}">{badge} {conf_str}</span>'
        f'</div>\n'
        f'  <input type="text" class="editor-control editor-input" data-path="{path_attr}" value="{_escape(value_text)}">\n'
        f'</div>\n'
    )


def _render_editable_generic_value(value, path: list, label: str) -> str:
    path_attr = _escape(json.dumps(path, ensure_ascii=False))
    title = _escape(label)
    if isinstance(value, bool):
        return (
            f'<div class="editor-row paper-row confidence-none" data-kind="checkbox" style="--confidence-color:#6c757d">\n'
            f'  <div class="editor-label"><span class="editor-label-text">{title}</span></div>\n'
            f'  <label class="editor-control checkbox-control">'
            f'<input type="checkbox" data-path="{path_attr}" {"checked" if value else ""}>'
            f'<span>{"Checked" if value else "Unchecked"}</span>'
            f'</label>\n'
            f'</div>\n'
        )

    value_text = "" if value is None else str(value)
    return (
        f'<div class="editor-row paper-row confidence-none" data-kind="field" style="--confidence-color:#6c757d">\n'
        f'  <div class="editor-label"><span class="editor-label-text">{title}</span></div>\n'
        f'  <input type="text" class="editor-control editor-input" data-path="{path_attr}" value="{_escape(value_text)}">\n'
        f'</div>\n'
    )


def _confidence_level(confidence: float | None) -> str:
    if confidence is None:
        return "none"
    if confidence < 0.7:
        return "low"
    if confidence < 0.9:
        return "medium"
    return "high"


def _looks_like_normalized_tree(data: dict) -> bool:
    return isinstance(data, dict) and not (
        ("document" in data and isinstance(data.get("document"), dict) and "pages" in data["document"])
        or "pages" in data
    )


def _render_editable_section(section: dict, path: list) -> str:
    title = section.get("title") or "Untitled Section"
    conf = section.get("confidence")
    color, badge = _confidence_style(conf)
    title_html = _escape(title)
    if conf is not None:
        title_html += (
            f' <span class="conf-badge" style="color:{color}" '
            f'title="Section confidence: {conf:.2f}">{badge} {conf:.2f}</span>'
        )

    html = (
        f'<details class="editor-section depth-{min(len(path), 3)}" open>\n'
        f'  <summary class="section-title">{title_html}</summary>\n'
        f'  <div class="section-body">\n'
    )

    for content_index, item in enumerate(section.get("content", [])):
        html += _render_editable_content_item(item, path + ["content", content_index])

    for subsection_index, subsection in enumerate(section.get("subsections", [])):
        html += _render_editable_section(subsection, path + ["subsections", subsection_index])

    html += '  </div>\n</details>\n'
    return html


def _render_editable_content_item(item: dict, path: list) -> str:
    item_type = item.get("type", "field")
    conf = item.get("confidence")
    color, badge = _confidence_style(conf)
    conf_str = f"{conf:.2f}" if conf is not None else ""
    path_attr = _escape(json.dumps(path, ensure_ascii=False))

    if item_type == "checkbox":
        checked = bool(item.get("checked"))
        label = item.get("label", "")
        return (
            f'<div class="editor-row" data-path="{path_attr}" data-kind="checkbox">\n'
            f'  <div class="editor-label">'
            f'<span class="editor-label-text">{_escape(label)}</span>'
            f'<span class="conf-badge" style="color:{color}" title="Confidence: {conf_str}">{badge} {conf_str}</span>'
            f'</div>\n'
            f'  <label class="editor-control checkbox-control">'
            f'<input type="checkbox" data-field="checked" {"checked" if checked else ""}>'
            f'<span>{"Checked" if checked else "Unchecked"}</span>'
            f'</label>\n'
            f'</div>\n'
        )

    if item_type == "text_block":
        text = item.get("text", "") or ""
        label = item.get("label") or "Text"
        return (
            f'<div class="editor-row" data-path="{path_attr}" data-kind="text_block">\n'
            f'  <div class="editor-label">'
            f'<span class="editor-label-text">{_escape(label)}</span>'
            f'<span class="conf-badge" style="color:{color}" title="Confidence: {conf_str}">{badge} {conf_str}</span>'
            f'</div>\n'
            f'  <textarea class="editor-control editor-textarea" data-field="text" rows="3">{_escape(text)}</textarea>\n'
            f'</div>\n'
        )

    if item_type == "table":
        headers = item.get("headers", [])
        rows = item.get("rows", [])
        html = (
            f'<div class="editor-row editor-table-wrap" data-path="{path_attr}" data-kind="table">\n'
            f'  <div class="editor-label">'
            f'<span class="editor-label-text">Table</span>'
            f'<span class="conf-badge" style="color:{color}" title="Confidence: {conf_str}">{badge} {conf_str}</span>'
            f'</div>\n'
            f'  <table class="editor-table">\n'
            f'    <thead><tr>'
        )
        for header in headers:
            html += f'<th>{_escape(str(header))}</th>'
        html += '</tr></thead>\n    <tbody>\n'
        for row_index, row in enumerate(rows):
            html += '<tr>'
            for col_index, cell in enumerate(row):
                cell_path = _escape(json.dumps(path + ["rows", row_index, col_index], ensure_ascii=False))
                html += (
                    f'<td><input type="text" class="editor-control editor-cell" '
                    f'data-path="{cell_path}" value="{_escape(str(cell))}"></td>'
                )
            html += '</tr>\n'
        html += '    </tbody>\n  </table>\n</div>\n'
        return html

    label = item.get("label", "")
    value = item.get("value")
    value_text = "" if value is None else str(value)
    return (
        f'<div class="editor-row" data-path="{path_attr}" data-kind="field">\n'
        f'  <div class="editor-label">'
        f'<span class="editor-label-text">{_escape(label)}</span>'
        f'<span class="conf-badge" style="color:{color}" title="Confidence: {conf_str}">{badge} {conf_str}</span>'
        f'</div>\n'
        f'  <input type="text" class="editor-control editor-input" data-field="value" value="{_escape(value_text)}">\n'
        f'</div>\n'
    )


def _json_script_payload(data: dict | None) -> str:
    if data is None:
        return "null"
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _build_editor_script() -> str:
    return """
(function () {
    const dataNode = document.getElementById('editor-data');
    const statusNode = document.getElementById('editor-status');
    const form = document.getElementById('editable-form');
    const toolbar = document.querySelector('.editor-toolbar');

    if (!dataNode || !form || !toolbar) {
        return;
    }

    const initialData = JSON.parse(dataNode.textContent || 'null');
    let dirty = false;

    function setStatus(message) {
        if (statusNode) {
            statusNode.textContent = message;
        }
    }

    function cloneData(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function setAtPath(root, path, value) {
        let target = root;
        for (let index = 0; index < path.length - 1; index += 1) {
            const key = path[index];
            if (target[key] === undefined || target[key] === null) {
                target[key] = typeof path[index + 1] === 'number' ? [] : {};
            }
            target = target[key];
        }
        target[path[path.length - 1]] = value;
    }

    function serializeForm() {
        const snapshot = cloneData(initialData);
        const controls = form.querySelectorAll('[data-path]');

        controls.forEach((control) => {
            const path = JSON.parse(control.dataset.path);
            if (control.matches('input[type="checkbox"]:not([data-field="checked"])')) {
                setAtPath(snapshot, path, control.checked);
                return;
            }
            if (control.matches('input[type="checkbox"][data-field="checked"]')) {
                setAtPath(snapshot, path.concat(['checked']), control.checked);
                return;
            }
            if (control.matches('textarea[data-field="text"]')) {
                setAtPath(snapshot, path.concat(['text']), control.value);
                return;
            }
            if (control.matches('input.editor-input:not([data-field="value"])')) {
                setAtPath(snapshot, path, control.value);
                return;
            }
            if (control.matches('input[data-field="value"]')) {
                setAtPath(snapshot, path.concat(['value']), control.value);
                return;
            }
            if (control.matches('input.editor-cell')) {
                setAtPath(snapshot, path, control.value);
            }
        });

        return snapshot;
    }

    function downloadJson() {
        const payload = serializeForm();
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = 'corrected-form.json';
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
        setStatus('JSON downloaded');
        dirty = false;
    }

    async function copyJson() {
        const payload = JSON.stringify(serializeForm(), null, 2);
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(payload);
        } else {
            const fallback = document.createElement('textarea');
            fallback.value = payload;
            document.body.appendChild(fallback);
            fallback.select();
            document.execCommand('copy');
            fallback.remove();
        }
        setStatus('JSON copied to clipboard');
        dirty = false;
    }

    function resetEditor() {
        window.location.reload();
    }

    toolbar.addEventListener('click', async (event) => {
        const button = event.target.closest('button[data-action]');
        if (!button) {
            return;
        }
        const action = button.dataset.action;
        try {
            if (action === 'download') {
                downloadJson();
            } else if (action === 'copy') {
                await copyJson();
            } else if (action === 'reset') {
                resetEditor();
            }
        } catch (error) {
            console.error(error);
            setStatus('Unable to complete action');
        }
    });

    form.addEventListener('input', () => {
        dirty = true;
        setStatus('Unsaved changes');
    });

    form.addEventListener('change', () => {
        dirty = true;
        setStatus('Unsaved changes');
    });

    window.addEventListener('beforeunload', (event) => {
        if (!dirty) {
            return;
        }
        event.preventDefault();
        event.returnValue = '';
    });

    setStatus('Ready');
})();
""".strip()


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

        /* Editable reconstruction */
        .editor-toolbar {
            display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
            margin-bottom: 1rem;
        }
        .editor-button {
            border: 1px solid #343a40; background: #343a40; color: #fff;
            padding: 0.45rem 0.8rem; border-radius: 6px; cursor: pointer;
            font-size: 0.86rem;
        }
        .editor-button:hover { filter: brightness(1.05); }
        .editor-secondary {
            background: #fff; color: #343a40; border-color: #adb5bd;
        }
        .editor-status { color: #6c757d; font-size: 0.85rem; margin-left: auto; }
        .editable-form { display: block; }
        .paper-form {
            background: linear-gradient(180deg, #f6f0e2 0%, #f9f4ea 100%);
            border: 1px solid #d7ccb7; border-radius: 18px;
            box-shadow: 0 16px 40px rgba(72, 55, 20, 0.08);
            padding: 1.5rem;
        }
        .editor-page, .editor-section {
            border-left: 3px solid #ced4da; margin: 0.5rem 0; padding-left: 1rem;
        }
        .editor-page-title {
            cursor: pointer; font-weight: 700; font-size: 0.98rem; color: #343a40;
        }
        .paper-section {
            border-left: none; padding-left: 0; margin: 1rem 0;
            border: 1px solid #d7ccb7; border-radius: 14px;
            background: rgba(255, 255, 255, 0.72);
            overflow: hidden;
        }
        .paper-repeat {
            background: rgba(248, 243, 233, 0.9);
        }
        .paper-section-title {
            background: #efe6d5;
            padding: 0.75rem 1rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            font-size: 0.82rem;
            border-bottom: 1px solid #ddcfb1;
        }
        .paper-section > .section-body {
            padding: 0.8rem 1rem 1rem;
        }
        .editor-row {
            margin: 0.5rem 0 0.75rem; padding: 0.6rem 0.75rem;
            background: #fff; border: 1px solid #dee2e6; border-radius: 8px;
        }
        .paper-row {
            display: grid;
            grid-template-columns: minmax(220px, 34%) minmax(0, 1fr);
            align-items: end;
            gap: 0.9rem;
            border: none;
            border-bottom: 2px solid color-mix(in srgb, var(--confidence-color) 32%, #d7ccb7 68%);
            border-radius: 0;
            background: transparent;
            padding: 0.55rem 0 0.7rem;
            margin: 0;
        }
        .paper-row + .paper-row {
            margin-top: 0.1rem;
        }
        .editor-label {
            display: flex; justify-content: space-between; gap: 0.75rem;
            align-items: baseline; margin-bottom: 0.35rem;
        }
        .paper-row .editor-label {
            margin-bottom: 0;
            padding-right: 0.75rem;
            border-right: 1px solid #e4d8c3;
            min-height: 100%;
        }
        .editor-label-text {
            font-weight: 600; color: #2f2a20;
            font-family: Georgia, 'Times New Roman', serif;
        }
        .editor-control {
            width: 100%; border: 1px solid #ced4da; border-radius: 6px;
            padding: 0.55rem 0.7rem; font-size: 0.92rem; background: #fff;
        }
        .paper-row .editor-control {
            border: none;
            border-radius: 0;
            border-bottom: 2px solid color-mix(in srgb, var(--confidence-color) 55%, #c9baa1 45%);
            background: rgba(255,255,255,0.65);
            padding: 0.42rem 0.15rem 0.35rem;
            color: #1f2933;
            font-weight: 600;
            box-shadow: none;
        }
        .editor-control:focus {
            outline: none; border-color: #343a40; box-shadow: 0 0 0 3px rgba(52, 58, 64, 0.12);
        }
        .paper-row .editor-control:focus {
            border-bottom-color: #1f2933;
            box-shadow: 0 10px 18px rgba(31, 41, 51, 0.08);
        }
        .editor-textarea { resize: vertical; min-height: 5rem; }
        .checkbox-control {
            display: inline-flex; align-items: center; gap: 0.5rem; width: auto;
            border: none; padding: 0.15rem 0;
        }
        .paper-conf {
            min-width: 4rem;
            text-align: right;
        }
        .checkbox-control input { width: 1rem; height: 1rem; }
        .editor-table-wrap { overflow-x: auto; }
        .editor-table {
            width: 100%; border-collapse: collapse; margin-top: 0.35rem;
            background: #fff;
        }
        .editor-table th, .editor-table td {
            border: 1px solid #dee2e6; padding: 0.35rem; vertical-align: top;
        }
        .editor-table th { background: #f8f9fa; text-align: left; }
        .editor-cell { min-width: 8rem; }
        @media (max-width: 900px) {
            .paper-row {
                grid-template-columns: 1fr;
                gap: 0.45rem;
            }
            .paper-row .editor-label {
                border-right: none;
                padding-right: 0;
            }
        }
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

{{EDITOR_SECTION}}

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

    <script id="editor-data" type="application/json">{{EDITOR_JSON}}</script>
    <script>
{{EDITOR_SCRIPT}}
    </script>
</body>
</html>
"""
