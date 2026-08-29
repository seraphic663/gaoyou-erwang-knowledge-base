from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


V2_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(V2_ROOT / "scripts"))

from freeze_external_edition_candidates import (  # noqa: E402
    compact_work,
    download_file,
    quote_match,
    safe_component,
)
from build_external_evidence_packets import (  # noqa: E402
    validate_external_edition_candidate_manifest,
)


class ExternalEditionCandidateTest(unittest.TestCase):
    def test_work_matching_is_only_a_conservative_locator(self) -> None:
        self.assertEqual(compact_work("《礼记·月令》"), "礼记·月令")
        self.assertIn("说文解字", compact_work("《说文解字》"))

    def test_path_component_rejects_traversal(self) -> None:
        self.assertEqual(safe_component("06050615.cn"), "06050615.cn")
        with self.assertRaises(ValueError):
            safe_component("../outside")

    def test_quote_match_is_candidate_only_and_handles_small_mapping(self) -> None:
        result = quote_match("賓，所敬也。", "宾，所敬也。")
        self.assertEqual(result["match_mode"], "candidate_ocr_match")
        self.assertIsInstance(result["start_char"], int)

    def test_download_file_reuses_size_validated_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "candidate.txt"
            target.write_bytes(b"frozen candidate")
            with patch("freeze_external_edition_candidates.urllib.request.urlopen") as urlopen:
                result = download_file(
                    "https://example.invalid/candidate.txt",
                    target,
                    expected_size=target.stat().st_size,
                )
            urlopen.assert_not_called()
            self.assertEqual(result["status"], "reused")
            self.assertEqual(result["size_bytes"], len(b"frozen candidate"))

    def test_production_candidate_manifest_files_and_boundaries_validate(self) -> None:
        result = validate_external_edition_candidate_manifest(
            V2_ROOT / "data/real_runs/external_edition_candidate_manifest.v1.json"
        )
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["counts"]["candidate_count"], 34)
        self.assertEqual(result["counts"]["item_count"], 191)
        self.assertEqual(result["counts"]["complete_file_count"], 191)
        self.assertEqual(result["counts"]["missing_file_count"], 0)
        self.assertEqual(result["database_rows_changed"], 0)


if __name__ == "__main__":
    unittest.main()
