import json
import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root (two levels up from src/form-extraction/)
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

import azure.functions as func

from utils.doc_intelligence import analyze_layout, build_word_confidence_map, strip_page_numbers
from utils.llm_extraction import extract_fields
from utils.normalizer import normalize_fields

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="extract_form", methods=["POST"])
async def extract_form(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("extract_form triggered")

    body = req.get_body()
    if not body:
        return func.HttpResponse(
            json.dumps({"error": "Request body is empty. Provide a file."}),
            status_code=400,
            mimetype="application/json",
        )

    content_type = req.headers.get("Content-Type", "")

    if "application/json" in content_type:
        try:
            payload = req.get_json()
            blob_url = payload.get("blob_url")
            prompt = payload.get("prompt")
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON"}),
                status_code=400,
                mimetype="application/json",
            )
        if not blob_url:
            return func.HttpResponse(
                json.dumps({"error": "blob_url is required"}),
                status_code=400,
                mimetype="application/json",
            )
        file_content = None
    else:
        file_content = body
        blob_url = None
        prompt = req.params.get("prompt")

    try:
        result = analyze_layout(file_content=file_content, blob_url=blob_url)
        layout_text = strip_page_numbers(result)
        fields = extract_fields(layout_text, prompt=prompt)
        word_conf_map = build_word_confidence_map(result)
        fields = normalize_fields(fields, word_confidence_map=word_conf_map)

        return func.HttpResponse(
            json.dumps(fields, ensure_ascii=False),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as e:
        logging.exception("Error processing form")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )