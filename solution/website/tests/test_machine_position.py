import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from machine_library import _matches_query


def claim(left, right, **extra):
    return dict(left_form=left, right_form=right, relation_type="gloss",
                directionality="left_to_right", target_forms_json='["農", "努", "毋", "無", "畏"]', **extra)


class PositionMatching(unittest.TestCase):
    def test_directional_ends(self):
        row = claim("農", "努")
        self.assertTrue(_matches_query(row, ["農"], "all", "source")[0])
        self.assertFalse(_matches_query(row, ["農"], "all", "target")[0])
        self.assertTrue(_matches_query(row, ["努"], "all", "target")[0])

    def test_and_must_match_selected_end(self):
        row = claim("農", "努")
        self.assertTrue(_matches_query(row, ["農", "努"], "all")[0])
        for position in ("source", "target"):
            self.assertFalse(_matches_query(row, ["農", "努"], "all", position)[0])
            self.assertTrue(_matches_query(row, ["農", "努"], "any", position)[0])

    def test_symmetric_has_no_arbitrary_role(self):
        row = claim("毋", "無")
        row["directionality"] = "symmetric"
        for position in ("any", "source", "target"):
            self.assertTrue(_matches_query(row, ["毋", "無"], "all", position)[0])

    def test_rejected_single_glyph_remains_excluded(self):
        row = claim("都奚反", "移")
        for position in ("any", "source", "target"):
            self.assertFalse(_matches_query(row, ["反"], "all", position)[0])

    def test_emendation_uses_changed_glyphs(self):
        row = claim("敬畏戚農", "敬農戚農")
        row.update(relation_type="emendation", changed_from="畏", changed_to="農")
        self.assertFalse(_matches_query(row, ["農"], "all", "source")[0])
        self.assertTrue(_matches_query(row, ["農"], "all", "target")[0])

    def test_empty_query_keeps_browsing(self):
        for position in ("any", "source", "target"):
            self.assertTrue(_matches_query(claim("農", "努"), [], "all", position)[0])


if __name__ == "__main__":
    unittest.main()
