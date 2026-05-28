"""Direct LLM extraction — send raw document to GPT-5.2 without OCR preprocessing."""

import io
import json
import os
from pathlib import Path

from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

_PROMPT_FILE = Path(__file__).resolve().parent.parent / "direct_extraction_prompt.txt"

_DEFAULT_PROMPT = (
    "Extract all form fields as key-value pairs from the following raw document. "
    "IMPORTANT:\n"
    "- Return ONLY valid JSON\n"
    "- Do NOT include explanations\n"
    "- Do NOT invent values\n"
    "- If a value is missing or empty → return null\n"
    "- Preserve exact text from the document\n"
)

# Extensions that should be sent as text (decoded UTF-8)
_TEXT_EXTENSIONS = {".html", ".htm", ".txt", ".csv", ".xml", ".json", ".md"}


def _load_prompt() -> str:
    """Load prompt from file if exists, otherwise use default."""
    if _PROMPT_FILE.exists():
        return _PROMPT_FILE.read_text(encoding="utf-8").strip()
    return _DEFAULT_PROMPT


def extract_fields_direct(
    file_content: bytes,
    prompt: str | None = None,
    file_path: str | Path | None = None,
) -> dict:
    """Send raw document content directly to GPT-5.2 for extraction.

    For text files (HTML, TXT, etc.) sends as plain text.
    For binary files (PDF, TIFF, images) uploads via Files API, then references file_id.

    Args:
        file_content: Raw file bytes (HTML, PDF, image, etc.)
        prompt: Optional custom prompt override. If None, loads from file or uses default.
        file_path: Optional file path for MIME type detection.

    Returns:
        Extracted fields as dict.
    """
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_GPT_5_2", "gpt-5.2")

    credential = DefaultAzureCredential()
    token = credential.get_token("https://cognitiveservices.azure.com/.default")

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token=token.token,
        api_version="2025-04-01-preview",
    )

    system_prompt = prompt or _load_prompt()

    # Determine if file is text or binary
    ext = Path(file_path).suffix.lower() if file_path else None
    is_text = ext in _TEXT_EXTENSIONS if ext else False

    if is_text:
        # Send as plain text content
        try:
            document_text = file_content.decode("utf-8")
        except UnicodeDecodeError:
            document_text = file_content.decode("latin-1")

        user_input = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": document_text},
        ]
    else:
        # Upload file via Files API, then reference by file_id
        filename = Path(file_path).name if file_path else "document.pdf"
        uploaded_file = client.files.create(
            file=(filename, io.BytesIO(file_content)),
            purpose="assistants",
        )

        user_input = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "input_file", "file_id": uploaded_file.id},
                    {"type": "input_text", "text": "Extract all form fields from this document."},
                ],
            },
        ]

    try:
        response = client.responses.create(
            model=deployment,
            input=user_input,
            temperature=0,
            text={"format": {"type": "json_object"}},
        )

        # Extract text from response output
        result_text = response.output_text
        return json.loads(result_text)
    finally:
        # Clean up uploaded file
        if not is_text:
            try:
                client.files.delete(uploaded_file.id)
            except Exception:
                pass
