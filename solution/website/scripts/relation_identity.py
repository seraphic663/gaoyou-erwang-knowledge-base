"""Shared identity and endpoint ordering for machine relation cards.

Evidence rows should keep the parser's original left/right order. Use
``relation_identity`` as the aggregation key and
``canonical_relation_endpoints`` for the card-level endpoint display. Only an
explicitly symmetric relation is unordered; directional readings and
corrections retain their source order.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def canonical_relation_endpoints(
    left_form: str,
    right_form: str,
    directionality: str = "left_to_right",
) -> tuple[str, str]:
    """Return display endpoints, sorting only symmetric relations."""
    left = str(left_form or "")
    right = str(right_form or "")
    if directionality == "symmetric":
        return tuple(sorted((left, right)))
    return left, right


def relation_identity(relation: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    """Build a query-independent card key while preserving directional claims.

    Single-character emendations use ``changed_from``/``changed_to`` so that
    the same correction can group across larger quoted contexts. Phrase-level
    emendations and all other relation types use their full endpoint forms.
    The first key field is structural and derived from these identity endpoints;
    the parser's ``relation_scope`` is query-dependent and is deliberately
    excluded. Author stance, cue, source, and evidence also remain attached to
    each evidence row rather than changing card identity.
    """
    relation_type = str(relation.get("relation_type") or "")
    directionality = str(relation.get("directionality") or "left_to_right")

    if (relation_type == "emendation"
            and relation.get("changed_from") is not None
            and relation.get("changed_to") is not None):
        left = str(relation.get("changed_from") or "")
        right = str(relation.get("changed_to") or "")
    else:
        left = str(relation.get("left_form") or "")
        right = str(relation.get("right_form") or "")

    left, right = canonical_relation_endpoints(left, right, directionality)
    if len(left) <= 1 and len(right) <= 1:
        identity_scope = "single_character"
    elif len(left) == 1 or len(right) == 1:
        identity_scope = "mixed_form"
    else:
        identity_scope = "phrase_level"
    return identity_scope, relation_type, left, right, directionality


__all__ = ["canonical_relation_endpoints", "relation_identity"]
