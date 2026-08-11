from __future__ import annotations

from pathlib import Path
from typing import Any

from .candidate_auditor import audit_candidates
from .candidate_extractor import extract_candidates
from .passage_builder import build_passages


def build_preview(source_path: str | Path, work_key: str) -> dict[str, Any]:
    passages = build_passages(source_path, work_key)
    candidate_layers = extract_candidates(passages)
    all_candidates = (
        candidate_layers["parsed_items"] + candidate_layers["candidate_items"]
    )
    audit = audit_candidates(all_candidates, passages)
    return {
        "passages": passages,
        "candidates": candidate_layers,
        "candidate_audit": audit,
    }
