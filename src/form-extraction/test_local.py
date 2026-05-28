"""Quick local test for Document Intelligence + GPT extraction pipeline."""

import copy
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from utils.doc_intelligence import analyze_layout, build_word_confidence_map, build_word_confidence_sequence, strip_page_numbers
from utils.llm_extraction import extract_fields
from utils.direct_llm_extraction import extract_fields_direct
from utils.normalizer import normalize_fields
from utils.report import generate_html_report


def _get_sample_files() -> list[Path]:
    """Return all non-HTML files in the samples folder."""
    samples_dir = Path(__file__).resolve().parent / "samples"
    return sorted(p for p in samples_dir.iterdir() if p.is_file() and p.suffix.lower() != ".html")


def main():
    if len(sys.argv) > 1:
        files = [Path(sys.argv[1])]
    else:
        files = _get_sample_files()
        if not files:
            print("No sample files found in samples/")
            sys.exit(1)

    prompt = sys.argv[2] if len(sys.argv) > 2 else None

    for file_path in files:
        if not file_path.exists():
            print(f"File not found: {file_path}")
            continue

        print(f"\n{'='*60}\nProcessing: {file_path.name}\n{'='*60}")

        print(f"Analyzing layout: {file_path}")
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        result = analyze_layout(file_content=file_bytes)

        print(f"\n--- Layout content (first 1000 chars) ---\n{result.content[:1000]}\n")

        print("--- OCR word confidence (sample) ---")
        word_conf_map = build_word_confidence_map(result)
        word_conf_seq = build_word_confidence_sequence(result)
        # Show first 30 words sorted by confidence (lowest first)
        sorted_words = sorted(word_conf_map.items(), key=lambda x: x[1])
        for word, conf in sorted_words[:30]:
            print(f"  {word:20s} {conf:.3f}")
        print(f"  ... ({len(word_conf_map)} words total)\n")

        layout_text = strip_page_numbers(result)
        print("--- Extracting fields with GPT ---")
        fields = extract_fields(layout_text, prompt=prompt)
        llm_fields = copy.deepcopy(fields)
        print(json.dumps(fields, indent=2, ensure_ascii=False))

        # Parallel path: direct LLM extraction (raw document → GPT-5.2)
        print("\n--- Direct LLM extraction (GPT-5.2, no OCR) ---")
        direct_llm_fields = None
        try:
            direct_llm_fields = extract_fields_direct(file_bytes, file_path=file_path)
            print(json.dumps(direct_llm_fields, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"  [SKIPPED] Direct LLM extraction failed: {e}")

        print("\n--- Normalizing extracted fields ---")
        fields = normalize_fields(fields, word_confidence_map=word_conf_map)

        print("\n--- Final normalized fields ---")
        print(json.dumps(fields, indent=2, ensure_ascii=False))

        # Generate HTML report with all pipeline stages
        report_path = file_path.with_suffix(".html")
        generate_html_report(
            fields,
            output_path=report_path,
            word_confidence_map=word_conf_map,
            layout_text=layout_text,
            llm_fields=llm_fields,
            word_confidence_sequence=word_conf_seq,
            direct_llm_fields=direct_llm_fields,
        )
        print(f"\n--- HTML report saved to: {report_path} ---")


if __name__ == "__main__":
    main()
