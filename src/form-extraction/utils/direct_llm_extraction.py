"""Direct LLM extraction — send raw document to GPT-5.2 without OCR preprocessing."""

import io
import json
import logging
import os
import time
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

_LOGGER = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _with_retries(operation: str, max_attempts: int, backoff_seconds: float, call):
    """Run a callable with simple linear backoff retries."""
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            _LOGGER.info("[direct-llm] %s (attempt %s/%s)", operation, attempt, max_attempts)
            return call()
        except Exception as error:  # noqa: BLE001
            last_error = error
            if attempt >= max_attempts:
                break
            wait_seconds = backoff_seconds * attempt
            _LOGGER.warning(
                "[direct-llm] %s failed on attempt %s/%s: %s. Retrying in %.1fs",
                operation,
                attempt,
                max_attempts,
                error,
                wait_seconds,
            )
            time.sleep(wait_seconds)

    raise RuntimeError(f"Direct LLM step failed: {operation}") from last_error


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
    request_timeout_seconds = _env_float("DIRECT_LLM_TIMEOUT_SECONDS", 120.0)
    retry_attempts = max(1, _env_int("DIRECT_LLM_RETRY_ATTEMPTS", 2))
    retry_backoff_seconds = max(0.5, _env_float("DIRECT_LLM_RETRY_BACKOFF_SECONDS", 2.0))

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_GPT_5_2", "gpt-5.2")

    credential = DefaultAzureCredential()
    token = _with_retries(
        operation="Acquire Azure AD token",
        max_attempts=retry_attempts,
        backoff_seconds=retry_backoff_seconds,
        call=lambda: credential.get_token("https://cognitiveservices.azure.com/.default"),
    )

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token=token.token,
        api_version="2025-04-01-preview",
        timeout=request_timeout_seconds,
    )

    system_prompt = prompt or _load_prompt()

    # Determine if file is text or binary
    ext = Path(file_path).suffix.lower() if file_path else None
    is_text = ext in _TEXT_EXTENSIONS if ext else False

    if is_text:
        _LOGGER.info("[direct-llm] Using text mode for extension: %s", ext)
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
        _LOGGER.info("[direct-llm] Using file upload mode for extension: %s", ext)
        # Upload file via Files API, then reference by file_id
        filename = Path(file_path).name if file_path else "document.pdf"
        uploaded_file = _with_retries(
            operation="Upload source document",
            max_attempts=retry_attempts,
            backoff_seconds=retry_backoff_seconds,
            call=lambda: client.files.create(
                file=(filename, io.BytesIO(file_content)),
                purpose="assistants",
            ),
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
        response = _with_retries(
            operation="Run GPT-5.2 direct extraction",
            max_attempts=retry_attempts,
            backoff_seconds=retry_backoff_seconds,
            call=lambda: client.responses.create(
                model=deployment,
                input=user_input,
                temperature=0,
                text={"format": {"type": "json_object"}},
            ),
        )

        # Extract text from response output
        result_text = response.output_text
        if not result_text:
            raise RuntimeError("Direct extraction response was empty")
        try:
            return json.loads(result_text)
        except json.JSONDecodeError as error:
            snippet = result_text[:300].replace("\n", " ")
            raise RuntimeError(f"Direct extraction returned invalid JSON: {snippet}") from error
    finally:
        # Clean up uploaded file
        if not is_text:
            try:
                client.files.delete(uploaded_file.id)
            except Exception:
                _LOGGER.warning("[direct-llm] Unable to delete uploaded file: %s", uploaded_file.id)
