import os
import re

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.identity import DefaultAzureCredential

# Page numbers typically appear in corners — filter words whose center falls
# beyond these thresholds (fraction of page width/height).
_EDGE_X_THRESHOLD = 0.88  # right 12%
_EDGE_Y_THRESHOLD = 0.92  # bottom 8%


def analyze_layout(
    file_content: bytes | None = None, blob_url: str | None = None
) -> AnalyzeResult:
    endpoint = os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"]
    credential = DefaultAzureCredential()
    client = DocumentIntelligenceClient(endpoint=endpoint, credential=credential)

    if blob_url:
        poller = client.begin_analyze_document(
            "prebuilt-layout", {"urlSource": blob_url}
        )
    elif file_content:
        poller = client.begin_analyze_document(
            "prebuilt-layout", file_content, content_type="application/octet-stream"
        )
    else:
        raise ValueError("Either file_content or blob_url must be provided")

    return poller.result()


def _find_page_numbers(result: AnalyzeResult) -> set[str]:
    """Identify words that are page numbers by their position (bottom-right corner)."""
    page_numbers: set[str] = set()
    for page in result.pages:
        if not page.words:
            continue
        for word in page.words:
            if not word.content.isdigit():
                continue
            poly = word.polygon
            xs = [poly[i] for i in range(0, len(poly), 2)]
            ys = [poly[i] for i in range(1, len(poly), 2)]
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            if cx > page.width * _EDGE_X_THRESHOLD and cy > page.height * _EDGE_Y_THRESHOLD:
                page_numbers.add(word.content)
    return page_numbers


def strip_page_numbers(result: AnalyzeResult) -> str:
    """Return result.content with page-corner numbers removed."""
    page_nums = _find_page_numbers(result)
    if not page_nums:
        return result.content

    content = result.content
    # Remove standalone page numbers (surrounded by whitespace/newlines)
    for num in sorted(page_nums, key=lambda x: -len(x)):
        # Match the number as a standalone token at end of line or surrounded by whitespace
        content = re.sub(rf'(?m)^{re.escape(num)}$', '', content)
        content = re.sub(rf'(?<=\s){re.escape(num)}(?=\s*$)', '', content, flags=re.MULTILINE)
    # Clean up resulting blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content


def build_word_confidence_map(result: AnalyzeResult) -> dict[str, float]:
    """Build a mapping from word text to its minimum confidence across all pages."""
    word_conf: dict[str, list[float]] = {}
    for page in result.pages:
        if not page.words:
            continue
        for word in page.words:
            text = word.content.lower()
            if text not in word_conf:
                word_conf[text] = []
            word_conf[text].append(word.confidence)
    # Return min confidence for each word (worst case)
    return {text: min(confs) for text, confs in word_conf.items()}


def get_value_confidence(value: str, word_confidence_map: dict[str, float]) -> float | None:
    """Calculate confidence for a field value by finding its words in the confidence map.
    Returns the minimum word confidence (worst word determines overall confidence).
    """
    if not value or not value.strip():
        return None

    # Split value into tokens similar to how OCR tokenizes
    tokens = value.lower().split()
    if not tokens:
        return None

    confidences = []
    for token in tokens:
        # Try exact match first
        if token in word_confidence_map:
            confidences.append(word_confidence_map[token])
        else:
            # Try partial match for tokens that might have been split differently
            matched = False
            for word, conf in word_confidence_map.items():
                if token in word or word in token:
                    confidences.append(conf)
                    matched = True
                    break
            if not matched:
                # Token not found in OCR — could be OCR error, assign low confidence
                confidences.append(0.5)

    return min(confidences) if confidences else None