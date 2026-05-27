import json
import os

from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

_DEFAULT_PROMPT = (
    "Extract all form fields as key-value pairs from the following document layout. "
    "IMPORTANT:\n"
    "- Return ONLY valid JSON\n"
    "- Do NOT include explanations\n"
    "- Do NOT invent values\n"
    "- If a value is missing or empty → return null\n"
    "- Preserve exact text from the document\n"
)


def extract_fields(layout_text: str, prompt: str | None = None) -> dict:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")

    credential = DefaultAzureCredential()
    token = credential.get_token("https://cognitiveservices.azure.com/.default")

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token=token.token,
        api_version="2024-12-01-preview",
    )

    system_prompt = prompt or _DEFAULT_PROMPT

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": layout_text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)