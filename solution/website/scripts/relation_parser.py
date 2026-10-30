"""Conservative, deterministic extraction of relations from quoted forms.

This module is intentionally small and explainable.  It treats the old
nearest-quoted-form parser as a candidate generator, not as a semantic oracle:
only cue-bound arguments are emitted, rejected/conditional claims can be
retained for evaluation, and ambiguous parallel constructions abstain.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable


HAN = r"[\u3400-\u9fff\U00020000-\U0002FA1F]"
HAN_FORM = re.compile(rf"{HAN}{{1,16}}\Z")
QUOTE_RE = re.compile(
    rf"「(?P<guillemet>{HAN}{{1,16}})」|"
    rf"『(?P<corner>{HAN}{{1,16}})』|"
    rf"‘(?P<single>{HAN}{{1,16}})’|"
    rf"“(?P<double>{HAN}{{1,16}})”|"
    rf'"(?P<ascii_double>{HAN}{{1,16}})"|'
    rf"'(?P<ascii_single>{HAN}{{1,16}})'"
)

RELATION_LABELS = {
    "reading": "讀音/讀法候選",
    "loan": "通假/相通候選",
    "emendation": "校勘異文候選",
    "emendation_phrase": "短語校勘候選",
    "gloss": "訓釋/轉語候選",
}

_CUE_KIND = {
    "古通作": "loan", "通作": "loan", "通用": "loan", "相通": "loan",
    "通假": "loan", "假借": "loan", "借作": "loan", "借爲": "loan",
    "借為": "loan", "當讀爲": "reading", "當讀為": "reading",
    "應讀爲": "reading", "應讀為": "reading", "当读为": "reading", "应读为": "reading",
    "讀爲": "reading", "讀為": "reading", "讀若": "reading",
    "讀如": "reading", "读为": "reading", "读若": "reading", "读如": "reading",
    "當作": "emendation", "当作": "emendation", "當爲": "emendation",
    "當為": "emendation", "当为": "emendation", "應作": "emendation",
    "应作": "emendation", "譌作": "emendation", "訛作": "emendation",
    "讹作": "emendation", "誤作": "emendation", "误作": "emendation",
    "本作": "emendation", "原作": "emendation", "訓爲": "gloss",
    "訓為": "gloss", "训为": "gloss", "猶": "gloss", "犹": "gloss",
    "同義": "gloss", "同义": "gloss", "之爲": "gloss", "之為": "gloss",
}
_CUES = tuple(sorted(_CUE_KIND, key=len, reverse=True))
_CUE_RE = re.compile("|".join(re.escape(cue) for cue in _CUES))
_DIRECT_RE = re.compile(
    rf"(?P<left>{HAN})(?P<marker>疑|或)?(?P<cue>古通作|通作|通用|相通|通假|借作|借爲|借為|"
    rf"當讀爲|當讀為|應讀爲|應讀為|当读为|应读为|讀爲|讀為|讀若|讀如|读为|读若|读如|當作|当作|當爲|當為|当为|"
    rf"應作|应作|譌作|訛作|讹作|誤作|误作|本作|原作)"
    rf"(?P<right>{HAN})(?=(?:也|者|字|[，,。；！？!?]|$))"
)
_DIRECT_TARGET_RE = re.compile(
    rf"^\s*[「『‘“\"']?(?P<target>{HAN})[」』’”\"']?\s*[，,：:]?\s*(?:亦可|亦|即)?\s*"
    rf"(?P<cue>訓爲|訓為|训为|當讀爲|當讀為|應讀爲|應讀為|当读为|应读为|讀爲|讀為|讀若|讀如|读为|读若|读如|"
    rf"通作|通用|相通|古通作|借作|借爲|借為|猶|犹)\s*"
    rf"[「『‘“\"']?(?P<right>{HAN}{{1,8}}?)[」』’”\"']?"
    rf"(?=(?:也|者|字|[，,。；！？!?]|$))"
)
_DIRECT_GLOSS_RE = re.compile(
    rf"(?:^|[。；！？!?：:\n])\s*[「『‘“\"']?(?P<target>{HAN})[」』’”\"']?"
    rf"\s*[，,]\s*[「『‘“\"']?(?P<gloss>{HAN}{{1,4}}?)也(?=[，,。；！？!?]|$)"
)
_DIRECT_GLOSS_PREDICATE_RE = re.compile(r"所(?:作|造|制|製|創|创|成|爲|為|为)")
_DIRECT_GLOSS_NEGATIVE_RHS_RE = re.compile(rf"^非{HAN}+$")
_DIRECT_GLOSS_DESCRIPTION_RE = re.compile(
    r"(?:不定之詞|不定之词|發聲|发声|發語詞|发语词|發語|发语|語助|语助|助語|助语|"
    r"語中助詞|语中助词|語終詞|语终词|語氣詞|语气词|語助詞|语助词)"
)
_STRUCTURAL_UNIT_RHS_RE = re.compile(
    r"^(?:一|二|三|四|五|六|七|八|九|十|兩|两|數|数|幾|几|上|下|前|後|后)"
    r"(?:句|節|节|章|篇|段|條|条|卷)$"
)
_COORDINATED_DIRECT_GLOSS_RE = re.compile(
    rf"(?:^|[。；！？!?\n：:])\s*(?P<forms>{HAN}(?:\s*、\s*{HAN}){{2,8}})"
    rf"\s*[，,]\s*(?P<gloss>{HAN}{{1,4}})也(?=[，,。；！？!?」』’”\"']|$)"
)
_WHOLE_PHRASE_MARKER_RE = re.compile(
    r"(?:[一二三四五六七八九十兩两\d]+字|全句|整句|全篇|整篇|全段|整段)"
)
_POST_REJECTION_TAIL_RE = re.compile(
    r"(?:^|[，,；;])\s*(?:增字以解經|增字以解经)?[，,；;]?\s*"
    r"(?:非也|非其本義(?:也)?|非其本义(?:也)?|非本義(?:也)?|非本义(?:也)?|非是(?:也)?|不然)\s*$"
)
_NEGATION_RE = re.compile(
    r"(?:並非|并非|非|不|未|不可|不能|"
    r"(?:無煩|无烦|無庸|无庸|無須|无须|毋庸|毋須|不必)\s*(?:改)?|無|无)"
    r"\s*(?:即|謂|谓|訓|训|讀|读|通|作|爲|為)?\s*$"
)
_CONDITIONAL_RE = re.compile(r"(?:若|倘若|倘|假使|如若)[^。；！？!?\n]{0,18}$")
_PROPOSAL_RE = re.compile(r"(?:疑|或|恐|似)\s*(?:當|当|應|应|訓|训|讀|读|作|爲|為)?\s*$")
_REPORT_RE = re.compile(r"(?:曰|云|雲|謂|谓|言|稱|称|注曰|注云)\s*[：:]?\s*[「『‘“\"']?\s*$")
_BOUNDARY_CHARS = set("。；！？!?\n")
_QUOTE_OPEN_TO_CLOSE = {
    "「": "」", "『": "』", "‘": "’", "“": "”", '"': '"', "'": "'",
    "﹁": "﹂", "﹃": "﹄", "〝": "〞", "《": "》", "〈": "〉",
}
_ARGUMENT_QUOTE_OPEN_TO_CLOSE = {
    "「": "」", "『": "』", "‘": "’", "“": "”", '"': '"', "'": "'",
    "﹁": "﹂", "﹃": "﹄", "〝": "〞",
}
_OPEN_TO_CLOSE = {
    **_QUOTE_OPEN_TO_CLOSE,
    "（": "）", "(": ")", "【": "】", "[": "]", "〔": "〕",
}
_CLOSE_CHARS = set(_OPEN_TO_CLOSE.values()) | {"）", ")", "】"}
_QUOTE_BOUNDARY_CHARS = set(_QUOTE_OPEN_TO_CLOSE) | set(_QUOTE_OPEN_TO_CLOSE.values())

# Cross-sentence alignment is intentionally limited to an explicit correction
# formula. A nearby 猶/犹 or other generic cue cannot inherit the last quote
# from a preceding sentence.
_EXPLICIT_CROSS_SENTENCE_RE = re.compile(
    r"^\s*(?:[^。；：:\n]{1,12}[：:]\s*)?"
    r"(?:(?:此字|此|今本|今|本字|該字|该字)\s*)?"
    r"(?P<cue>當作|当作|當爲|當為|当为|應作|应作|宜作|正作|本作|原作|"
    r"誤作|误作|譌作|訛作|讹作)\s*$"
)

DEFAULT_MODULES = frozenset({"alignment", "stance", "parallel", "shared_subject", "scope"})
ALL_MODULES = DEFAULT_MODULES


@dataclass(frozen=True)
class _Quote:
    form: str
    start: int
    end: int
    is_argument: bool


@lru_cache(maxsize=64)
def _segments(text: str) -> tuple[tuple[int, int, str], ...]:
    """Split at outer sentence boundaries, retaining exact code-point offsets."""
    output: list[tuple[int, int, str]] = []
    stack: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char in _OPEN_TO_CLOSE:
            stack.append(_OPEN_TO_CLOSE[char])
        elif stack and char == stack[-1]:
            stack.pop()
        elif char in _CLOSE_CHARS and stack:
            # A malformed or nested quote should not poison all following text.
            if char in stack:
                while stack and stack[-1] != char:
                    stack.pop()
                if stack:
                    stack.pop()
        if char in _BOUNDARY_CHARS and not stack:
            if text[start:index + 1].strip():
                output.append((start, index + 1, text[start:index + 1]))
            start = index + 1
    if text[start:].strip():
        output.append((start, len(text), text[start:]))
    return tuple(output)


@lru_cache(maxsize=512)
def _quotes(segment: str) -> tuple[_Quote, ...]:
    """Return balanced quote spans, including quotes unsuitable as arguments.

    Punctuation inside a quotation must not make that quotation disappear from
    boundary checks. Only a short, punctuation-free Han quote is an argument;
    all other matched quote spans remain explicit barriers.
    """
    stack: list[tuple[str, str, int]] = []
    found: list[_Quote] = []
    closing_to_open = {close: opening for opening, close in _QUOTE_OPEN_TO_CLOSE.items()}

    for index, char in enumerate(segment):
        if char in _QUOTE_OPEN_TO_CLOSE:
            close = _QUOTE_OPEN_TO_CLOSE[char]
            # ASCII quotes open and close with the same character.
            if char == close and stack and stack[-1][1] == char:
                opening, _, start = stack.pop()
                form = segment[start + 1:index]
                found.append(_Quote(
                    form=form, start=start, end=index + 1,
                    is_argument=(opening in _ARGUMENT_QUOTE_OPEN_TO_CLOSE
                                 and HAN_FORM.fullmatch(form) is not None),
                ))
            else:
                stack.append((char, close, index))
            continue

        if char not in closing_to_open:
            continue
        matching = next(
            (position for position in range(len(stack) - 1, -1, -1)
             if stack[position][1] == char),
            None,
        )
        if matching is None:
            continue
        opening, _, start = stack[matching]
        del stack[matching:]
        form = segment[start + 1:index]
        found.append(_Quote(
            form=form, start=start, end=index + 1,
            is_argument=(opening in _ARGUMENT_QUOTE_OPEN_TO_CLOSE
                         and HAN_FORM.fullmatch(form) is not None),
        ))

    return tuple(sorted(found, key=lambda quote: (quote.start, -quote.end)))


def _quote_gap_is_clear(segment: str, left: _Quote, right: _Quote) -> bool:
    """Whether two quote arguments are adjacent without another quote boundary."""
    return left.end <= right.start and not any(
        char in _QUOTE_BOUNDARY_CHARS for char in segment[left.end:right.start]
    )


def _fanqie_annotation(form: str) -> bool:
    """Recognize the common two-character-plus-反 phonetic annotation form."""
    return re.fullmatch(rf"{HAN}{{2}}反", form) is not None


def _ambiguous_loan_endpoint_lengths(left: str, right: str) -> bool:
    """Flag an unanchored phrase-to-character loan pairing for review."""
    return min(len(left), len(right)) == 1 and max(len(left), len(right)) >= 3


def _ambiguous_emendation_endpoint_lengths(left: str, right: str) -> bool:
    """Flag a large edit whose single-/two-character endpoint is unanchored."""
    return min(len(left), len(right)) <= 2 and abs(len(left) - len(right)) >= 2


def _span_is_quoted(text: str, start: int, end: int) -> bool:
    if start <= 0 or end >= len(text):
        return False
    opening, closing = text[start - 1], text[end]
    return _QUOTE_OPEN_TO_CLOSE.get(opening) == closing


def _direct_gloss_target_is_description(target: str, right: str) -> bool:
    if target not in right:
        return False
    # The particle 之 inside a direct gloss phrase such as 不定之詞 or 大之殷
    # is explanatory grammar, not a primary term endpoint. Other lexicalized
    # phrase endpoints remain searchable unless they carry a functional label.
    if target == "之" and "之" in right:
        return True
    return _DIRECT_GLOSS_DESCRIPTION_RE.search(right) is not None


def _has_postposed_rejection(text: str, claim_end: int,
                             segments: tuple[tuple[int, int, str], ...]) -> bool:
    segment_end = next((end for start, end, _ in segments if start <= claim_end <= end), len(text))
    tail = text[claim_end:segment_end][-64:].rstrip("。；！？!? \t\r\n")
    return bool(_POST_REJECTION_TAIL_RE.search(tail))


def _stance(segment: str, cue_start: int, left_start: int, *, enabled: bool) -> str:
    if not enabled:
        return "uncertain"
    before_cue = segment[max(0, cue_start - 16):cue_start]
    before_left = segment[max(0, left_start - 16):left_start]
    if _NEGATION_RE.search(before_cue):
        return "rejected"
    if _CONDITIONAL_RE.search(before_cue) or _CONDITIONAL_RE.search(before_left):
        return "conditional"
    if _PROPOSAL_RE.search(before_cue):
        return "proposed"
    if _REPORT_RE.search(before_left):
        return "reported"
    return "asserted"


def _changed(left: str, right: str) -> list[tuple[str, str, int, int, int, int]]:
    return [
        (left[a0:a1], right[b0:b1], a0, a1, b0, b1)
        for tag, a0, a1, b0, b1 in difflib.SequenceMatcher(a=left, b=right, autojunk=False).get_opcodes()
        if tag != "equal"
    ]


def _spans(form: str, target: str, side: str) -> list[dict[str, int | str]]:
    return [
        {"side": side, "start_cp": m.start(), "end_cp": m.end()}
        for m in re.finditer(re.escape(target), form)
    ]


def _record(
    *, text: str, segment_start: int, left: str, right: str, cue: str,
    relation_type: str, target: str, stance: str, directionality: str = "left_to_right",
    modules: frozenset[str], evidence_start: int, evidence_end: int,
    cue_start: int, cue_end: int, alignment_rule: str | None = None,
) -> dict | None:
    is_emendation = relation_type == "emendation"
    if "scope" in modules and target not in left and target not in right:
        return None
    # Fanqie belongs to phonetic annotation, not a relation endpoint for each
    # character in that notation. Keep e.g. 隄→都奚反 when querying 隄, but do
    # not create separate 都/奚/反 relation hits from the sound annotation.
    if "scope" in modules:
        if (_fanqie_annotation(left) and target in left and target not in right) or (
                _fanqie_annotation(right) and target in right and target not in left):
            return None
    changed = _changed(left, right)
    changed_target = any(target in before or target in after for before, after, *_ in changed)
    # A query hit must occur in a changed span. This also removes unchanged
    # context characters from phrase gloss/loan hits, not just emendations.
    if "scope" in modules and not changed_target:
        return None
    if is_emendation:
        if len(changed) == 1 and max(len(changed[0][0]), len(changed[0][1])) <= 1 and changed_target:
            scope = "single_character"
            changed_from, changed_to = changed[0][0], changed[0][1]
        else:
            scope = "phrase_level"
            changed_from = changed_to = None
            relation_type = "emendation_phrase"
    else:
        scope = "single_character" if left == target or right == target else "phrase_contains_target"
        changed_from = changed_to = None
    spans = []
    for before, after, left_start, _, right_start, _ in changed:
        spans.extend(
            {"side": "left", "start_cp": left_start + match.start(), "end_cp": left_start + match.end()}
            for match in re.finditer(re.escape(target), before)
        )
        spans.extend(
            {"side": "right", "start_cp": right_start + match.start(), "end_cp": right_start + match.end()}
            for match in re.finditer(re.escape(target), after)
        )
    record = {
        "relation_type": relation_type,
        "relation_scope": scope,
        "relation_label": RELATION_LABELS[relation_type],
        "relation_cue": cue,
        "left_form": left,
        "right_form": right,
        "target_side": spans[0]["side"] if spans else None,
        "target_spans": spans,
        "changed_from": changed_from,
        "changed_to": changed_to,
        "author_stance": stance,
        "directionality": directionality,
        "claim_span": {"start_cp": segment_start + evidence_start, "end_cp": segment_start + evidence_end},
        "trigger_span": {"start_cp": segment_start + cue_start, "end_cp": segment_start + cue_end},
        "quote": text[segment_start + evidence_start:segment_start + evidence_end],
        "status": "pending",
    }
    if alignment_rule:
        record["alignment_rule"] = alignment_rule
    return record


def _cue_between(between: str, prefix: str) -> tuple[str, str, int, int, str] | None:
    match = _CUE_RE.search(between)
    if match:
        cue = match.group(0)
        kind = _CUE_KIND[cue]
        if cue in {"同義", "同义"} and not re.search(r"與|与|、", between[:match.start()]):
            return None
        if cue in {"同義", "同义", "相通"}:
            directionality = "symmetric"
        else:
            directionality = "left_to_right"
        return cue, kind, match.start(), match.end(), directionality
    from_witness = re.search(r"(?:當|当)從[^。；！？!?\n]{0,18}作", between)
    if from_witness:
        return "當從…作", "emendation", from_witness.start(), from_witness.end(), "left_to_right"
    # Some classical glosses use 訓「A」爲「B」, with 訓 outside the pair.
    bare_for = re.search(r"(?:爲|為)", between)
    if bare_for and re.search(r"訓\s*$", prefix[-8:]):
        return "訓…爲", "gloss", bare_for.start(), bare_for.end(), "left_to_right"
    return None


def _direct_gloss_parts(raw_gloss: str) -> tuple[str, str, str]:
    """Separate a leading relation marker from a compact 直訓 gloss."""
    for cue in _CUES:
        if raw_gloss.startswith(cue) and len(raw_gloss) > len(cue):
            return cue, _CUE_KIND[cue], raw_gloss[len(cue):]
    return "直訓", "gloss", raw_gloss


def analyze_relation_candidates(
    text: str,
    target: str,
    *,
    modules: Iterable[str] = DEFAULT_MODULES,
) -> tuple[list[dict], list[dict]]:
    """Return extracted relation candidates and explicit abstention diagnostics.

    `alignment` uses cue-bound quoted arguments; across sentence boundaries it
    only inherits a prior quote for an explicit correction formula such as
    `此當作`; `stance` tags locally rejected, conditional, reported, and
    proposed claims; `parallel` recognizes the high-precision A之爲C，猶B之爲C
    frame and suppresses ambiguous nearby-quote pairings; `scope` requires the
    query glyph to occur in a changed endpoint span and filters fanqie notation
    as a phonetic annotation rather than a word endpoint.
    """
    value = str(text or "")
    enabled = frozenset(modules)
    if len(target) != 1:
        return [], [{"reason": "query_not_single_character"}]
    output: list[dict] = []
    abstentions: list[dict] = []
    seen: set[tuple] = set()
    segments = _segments(value)

    def add(**kwargs) -> None:
        right_is_quoted = kwargs.pop("_right_is_quoted", None)
        direct_gloss = kwargs.pop("_direct_gloss", False)
        left = str(kwargs.get("left") or "")
        right = str(kwargs.get("right") or "")
        if ("scope" in enabled and right_is_quoted is False
                and (target in left or target in right)
                and _STRUCTURAL_UNIT_RHS_RE.fullmatch(right)):
            abstentions.append({
                "reason": "unquoted_structural_unit_rhs",
                "target": target,
                "left_form": left,
                "right_form": right,
                "relation_cue": kwargs.get("cue"),
            })
            return
        if ("scope" in enabled and direct_gloss and target not in left
                and _direct_gloss_target_is_description(target, right)):
            abstentions.append({
                "reason": "direct_gloss_description_rhs",
                "target": target,
                "left_form": left,
                "right_form": right,
                "relation_cue": kwargs.get("cue"),
            })
            return
        if ("scope" in enabled and kwargs.get("relation_type") == "loan"
                and (target in left or target in right)
                and _ambiguous_loan_endpoint_lengths(left, right)):
            abstentions.append({
                "reason": "asymmetric_loan_endpoint_lengths",
                "target": target,
                "left_form": left,
                "right_form": right,
                "relation_cue": kwargs.get("cue"),
            })
            return
        if ("scope" in enabled and kwargs.get("relation_type") == "emendation"
                and (target in left or target in right)
                and _ambiguous_emendation_endpoint_lengths(left, right)):
            segment_start = int(kwargs.get("segment_start") or 0)
            evidence_start = segment_start + int(kwargs.get("evidence_start") or 0)
            evidence_end = segment_start + int(kwargs.get("evidence_end") or 0)
            phrase_context = value[max(0, evidence_start - 16):evidence_end]
            if not _WHOLE_PHRASE_MARKER_RE.search(phrase_context):
                abstentions.append({
                    "reason": "asymmetric_emendation_endpoint_lengths",
                    "target": target,
                    "left_form": left,
                    "right_form": right,
                    "relation_cue": kwargs.get("cue"),
                    "quote": value[evidence_start:evidence_end],
                })
                return
        if "stance" in enabled:
            segment_start = int(kwargs.get("segment_start") or 0)
            claim_end = segment_start + int(kwargs.get("evidence_end") or 0)
            if _has_postposed_rejection(value, claim_end, segments):
                kwargs["stance"] = "rejected"
        item = _record(text=value, target=target, modules=enabled, **kwargs)
        if item is None:
            return
        claim_span = item["claim_span"]
        trigger_span = item["trigger_span"]
        key = (
            item["relation_scope"], item["relation_type"], item["left_form"], item["right_form"],
            item["directionality"], item["author_stance"], item["relation_cue"],
            claim_span["start_cp"], claim_span["end_cp"],
            trigger_span["start_cp"], trigger_span["end_cp"],
            item.get("alignment_rule"),
        )
        if key not in seen:
            seen.add(key)
            output.append(item)

    if "alignment" in enabled:
        # A common editorial pattern places the old quotation in one sentence
        # and begins the next with "念孫案：此當作『新文』".  Bind only when
        # the previous segment ends at a quote and an explicit directional cue
        # occurs before the first quote in the next segment.
        for previous, current in zip(segments, segments[1:]):
            previous_start, _, previous_text = previous
            current_start, _, current_text = current
            previous_quotes = _quotes(previous_text)
            current_quotes = _quotes(current_text)
            if not previous_quotes or not current_quotes:
                continue
            # The final/initial *boundary* quote must itself be a valid form;
            # an unrecognized long quotation still blocks inheritance.
            left_q = max(previous_quotes, key=lambda quote: quote.end)
            right_q = min(current_quotes, key=lambda quote: quote.start)
            if not left_q.is_argument or not right_q.is_argument:
                continue
            if not re.fullmatch(r"\s*[。；！？!?]*\s*", previous_text[left_q.end:]):
                continue
            prefix = current_text[:right_q.start]
            cue_match = _EXPLICIT_CROSS_SENTENCE_RE.fullmatch(prefix)
            if not cue_match:
                continue
            cue = cue_match.group("cue")
            cue_start, cue_end = cue_match.span("cue")
            stance = _stance(
                value, current_start + cue_start, previous_start + left_q.start,
                enabled="stance" in enabled,
            )
            add(segment_start=0, left=left_q.form, right=right_q.form, cue=cue,
                relation_type=_CUE_KIND[cue], stance=stance,
                evidence_start=previous_start + left_q.start,
                evidence_end=current_start + right_q.end,
                cue_start=current_start + cue_start,
                cue_end=current_start + cue_end,
                alignment_rule="explicit_cross_sentence_correction_v1")

    for seg_start, seg_end, segment in segments:
        # Argument candidates are kept separate from other quote spans. The
        # raw gap check below still sees ineligible (for example punctuated)
        # quotations and refuses to pair across them.
        q = [quote for quote in _quotes(segment) if quote.is_argument]
        consumed: set[int] = set()
        shared_subject_pairs: set[int] = set()

        if "parallel" in enabled:
            for i in range(max(0, len(q) - 3)):
                if not all(_quote_gap_is_clear(segment, q[j], q[j + 1])
                           for j in range(i, i + 3)):
                    continue
                b1 = segment[q[i].end:q[i + 1].start]
                b2 = segment[q[i + 1].end:q[i + 2].start]
                b3 = segment[q[i + 2].end:q[i + 3].start]
                if (re.search(r"之\s*(?:爲|為)", b1)
                        and re.search(r"猶|犹", b2)
                        and re.search(r"之\s*(?:爲|為)", b3)
                        and q[i + 1].form == q[i + 3].form):
                    m1 = re.search(r"之\s*(?:爲|為)", b1)
                    m3 = re.search(r"之\s*(?:爲|為)", b3)
                    cue_start = q[i + 2].start + re.search(r"猶|犹", b2).start()
                    stance = _stance(segment, cue_start, q[i].start, enabled="stance" in enabled)
                    add(segment_start=seg_start, left=q[i].form, right=q[i + 1].form,
                        cue="平行之爲", relation_type="gloss", stance=stance,
                        directionality="left_to_right", evidence_start=q[i].start,
                        evidence_end=q[i + 3].end, cue_start=q[i].end + m1.start(),
                        cue_end=q[i].end + m1.end())
                    add(segment_start=seg_start, left=q[i + 2].form, right=q[i + 3].form,
                        cue="平行之爲", relation_type="gloss", stance=stance,
                        directionality="left_to_right", evidence_start=q[i].start,
                        evidence_end=q[i + 3].end, cue_start=q[i + 2].end + m3.start(),
                        cue_end=q[i + 2].end + m3.end())
                    consumed.update({i, i + 1, i + 2, i + 3})

        if "shared_subject" in enabled and "alignment" in enabled:
            for i in range(max(0, len(q) - 2)):
                if not all(_quote_gap_is_clear(segment, q[j], q[j + 1])
                           for j in range(i, i + 2)):
                    continue
                first_between = segment[q[i].end:q[i + 1].start]
                second_between = segment[q[i + 1].end:q[i + 2].start]
                first_prefix = segment[max(0, q[i].start - 12):q[i].start]
                first_info = _cue_between(first_between, first_prefix)
                second_info = _cue_between(second_between, "")
                if not first_info or not second_info:
                    continue
                second_cue, second_kind, second_rel_start, second_rel_end, second_direction = second_info
                second_before_cue = second_between[:second_rel_start]
                if not _NEGATION_RE.search(second_before_cue):
                    continue
                if _stance(segment, q[i + 1].end + second_rel_start, q[i].start,
                           enabled="stance" in enabled) != "rejected":
                    continue
                stance = "rejected"
                add(segment_start=seg_start, left=q[i].form, right=q[i + 2].form,
                    cue=second_cue, relation_type=second_kind, stance=stance,
                    directionality=second_direction, evidence_start=q[i].start,
                    evidence_end=q[i + 2].end, cue_start=q[i + 1].end + second_rel_start,
                    cue_end=q[i + 1].end + second_rel_end)
                shared_subject_pairs.add(i + 1)

            # Strict headword-list glosses such as 薄、怒、文、農，勉也.
            # Require a sentence/line boundary, at least three one-character
            # forms joined by 顿号, and a short explicit 也-gloss; this avoids
            # treating comma-separated narrative as a shared definition.
            for grouped in _COORDINATED_DIRECT_GLOSS_RE.finditer(segment):
                forms = re.findall(HAN, grouped.group("forms"))
                gloss = grouped.group("gloss")
                if len(forms) < 3:
                    continue
                if (_DIRECT_GLOSS_PREDICATE_RE.search(gloss)
                        or _DIRECT_GLOSS_NEGATIVE_RHS_RE.fullmatch(gloss)):
                    continue
                left_start = grouped.start("forms")
                evidence_start = grouped.start("forms")
                evidence_end = grouped.end("gloss") + 1
                cue_start = grouped.start("gloss")
                stance = _stance(segment, cue_start, left_start,
                                 enabled="stance" in enabled)
                for form in forms:
                    add(segment_start=seg_start, left=form, right=gloss,
                        cue="直訓", relation_type="gloss", stance=stance,
                        evidence_start=evidence_start, evidence_end=evidence_end,
                        cue_start=cue_start, cue_end=grouped.end("gloss"),
                        alignment_rule="coordinated_headword_gloss_v1",
                        _direct_gloss=True)

        if "alignment" in enabled:
            # An explicitly introduced fanqie note can sit between a word and
            # a following loan claim: 「X」又音「AB反」，亦與「Y」通. The
            # fanqie quote explains X's reading; the later conjunction still
            # has X as its subject. Bind X↔Y and consume the sound annotation
            # so it cannot become the nearest left endpoint for Y.
            for i in range(max(0, len(q) - 2)):
                if not all(_quote_gap_is_clear(segment, q[j], q[j + 1])
                           for j in range(i, i + 2)):
                    continue
                sound_between = segment[q[i].end:q[i + 1].start]
                relation_between = segment[q[i + 1].end:q[i + 2].start]
                sound_marker = re.fullmatch(r"\s*(?:(?:又|亦)\s*)?音\s*", sound_between)
                conjunction = re.search(r"(?:亦\s*)?[與与]", relation_between)
                after = segment[q[i + 2].end:min(len(segment), q[i + 2].end + 10)]
                if (not _fanqie_annotation(q[i + 1].form) or not sound_marker
                        or not conjunction or not re.search(r"通|同義|同义", after)):
                    continue
                cue_start = q[i + 1].end + conjunction.start()
                cue_end = q[i + 1].end + conjunction.end()
                stance = _stance(segment, cue_start, q[i].start, enabled="stance" in enabled)
                add(segment_start=seg_start, left=q[i].form, right=q[i + 2].form,
                    cue="與…通", relation_type="loan", stance=stance,
                    directionality="symmetric", evidence_start=q[i].start,
                    evidence_end=q[i + 2].end, cue_start=cue_start, cue_end=cue_end)
                consumed.update({i, i + 1, i + 2})

            for i, (left_q, right_q) in enumerate(zip(q, q[1:])):
                if i in consumed or i + 1 in consumed or i in shared_subject_pairs:
                    continue
                if not _quote_gap_is_clear(segment, left_q, right_q):
                    continue
                between = segment[left_q.end:right_q.start]
                after = segment[right_q.end:min(len(segment), right_q.end + 10)]
                prefix = segment[max(0, left_q.start - 12):left_q.start]
                cue_info = _cue_between(between, prefix)
                symmetric = None
                if (not cue_info and re.search(r"與|与", between)
                        and re.search(r"同義|同义|通", after)):
                    conjunction = between.find("與") if "與" in between else between.find("与")
                    if re.search(r"通", after):
                        cue_info = ("與…通", "loan", conjunction, conjunction + 1, "symmetric")
                    else:
                        cue_info = ("與…同義", "gloss", conjunction, conjunction + 1, "symmetric")
                if (not cue_info and re.search(r"、|與|与", between)
                        and re.search(r"二字.{0,3}(?:同義|同义)", after)):
                    cue_info = ("二字同義", "gloss", 0, len(between), "symmetric")
                if not cue_info:
                    continue
                cue, kind, cue_rel_start, cue_rel_end, directionality = cue_info
                if cue in {"猶", "犹"} and len(q) > 2 and "parallel" in enabled:
                    abstentions.append({"reason": "ambiguous_parallel_nearby_quotes", "target": target,
                                       "left_form": left_q.form, "right_form": right_q.form,
                                       "segment": segment})
                    continue
                if len(between) > 28 or any(mark in between for mark in "。；！？!?\n"):
                    continue
                cue_start = left_q.end + cue_rel_start
                cue_end = left_q.end + cue_rel_end
                stance = _stance(segment, cue_start, left_q.start, enabled="stance" in enabled)
                add(segment_start=seg_start, left=left_q.form, right=right_q.form, cue=cue,
                    relation_type=kind, stance=stance, directionality=directionality,
                    evidence_start=left_q.start, evidence_end=right_q.end,
                    cue_start=cue_start, cue_end=cue_end)

            # Classical prose sometimes quotes only the first form: 「農力」猶努力。
            # Accept a short unquoted right argument after a cue, but leave
            # quote-led or discourse-led continuations to the parallel parser.
            for left_q in q:
                tail = segment[left_q.end:]
                cue_match = re.match(rf"\s*(?P<cue>{_CUE_RE.pattern})\s*", tail)
                if not cue_match:
                    continue
                right_start = cue_match.end()
                if right_start >= len(tail) or tail[right_start] in _OPEN_TO_CLOSE:
                    continue
                if tail[right_start:right_start + 2] in {"彼言", "彼謂", "彼曰", "彼云"}:
                    continue
                right_match = re.match(
                    rf"(?P<form>{HAN}{{1,8}}?)(?=(?:也|者|字|[，,。；！？!?]|$))",
                    tail[right_start:],
                )
                if not right_match:
                    continue
                cue = cue_match.group("cue")
                cue_start = left_q.end + cue_match.start("cue")
                cue_end = left_q.end + cue_match.end("cue")
                stance = _stance(segment, cue_start, left_q.start, enabled="stance" in enabled)
                add(segment_start=seg_start, left=left_q.form, right=right_match.group("form"),
                    cue=cue, relation_type=_CUE_KIND[cue], stance=stance,
                    directionality="symmetric" if cue in {"同義", "同义", "相通"} else "left_to_right",
                    evidence_start=left_q.start,
                    evidence_end=left_q.end + right_start + right_match.end(),
                    cue_start=cue_start, cue_end=cue_end,
                    _right_is_quoted=False)

            # Unquoted direct constructions are accepted only when the queried
            # character is an actual one-character argument, not nearby prose.
            for direct in _DIRECT_RE.finditer(segment):
                left, right = direct.group("left"), direct.group("right")
                cue = direct.group("cue")
                cue_start, cue_end = direct.span("cue")
                stance = _stance(segment, cue_start, direct.start("left"), enabled="stance" in enabled)
                add(segment_start=seg_start, left=left, right=right, cue=cue,
                    relation_type=_CUE_KIND[cue], stance=stance,
                    evidence_start=direct.start(), evidence_end=direct.end(),
                    cue_start=cue_start, cue_end=cue_end)

            direct_target = _DIRECT_TARGET_RE.match(segment)
            if direct_target:
                cue = direct_target.group("cue")
                kind = _CUE_KIND.get(cue, "gloss")
                right = re.match(rf"{HAN}{{1,8}}", direct_target.group("right"))
                if right:
                    cue_start, cue_end = direct_target.span("cue")
                    stance = _stance(segment, cue_start, direct_target.start("target"), enabled="stance" in enabled)
                    right_start, right_end = direct_target.span("right")
                    add(segment_start=seg_start, left=direct_target.group("target"), right=right.group(0), cue=cue,
                        relation_type=kind, stance=stance,
                        evidence_start=direct_target.start(), evidence_end=direct_target.end(),
                        cue_start=cue_start, cue_end=cue_end,
                        _right_is_quoted=_span_is_quoted(segment, right_start, right_end))

            for gloss in _DIRECT_GLOSS_RE.finditer(segment):
                start = gloss.start("target")
                end = gloss.end("gloss") + 1
                raw_gloss = gloss.group("gloss")
                cue, kind, right_form = _direct_gloss_parts(raw_gloss)
                if not right_form:
                    continue
                left_form = gloss.group("target")
                if _DIRECT_GLOSS_PREDICATE_RE.search(right_form):
                    if target in left_form or target in right_form:
                        abstentions.append({
                            "reason": "direct_gloss_predicate_rhs",
                            "target": target,
                            "left_form": left_form,
                            "right_form": right_form,
                            "quote": segment[start:end],
                        })
                    continue
                if _DIRECT_GLOSS_NEGATIVE_RHS_RE.fullmatch(right_form):
                    if target in left_form or target in right_form:
                        abstentions.append({
                            "reason": "direct_gloss_negative_rhs",
                            "target": target,
                            "left_form": left_form,
                            "right_form": right_form,
                            "quote": segment[start:end],
                        })
                    continue
                cue_start = gloss.start("gloss")
                if cue != "直訓":
                    cue_start += len(cue)
                add(segment_start=seg_start, left=left_form, right=right_form,
                    cue=cue, relation_type=kind,
                    stance=_stance(segment, cue_start, start, enabled="stance" in enabled),
                    evidence_start=start, evidence_end=end, cue_start=cue_start,
                    cue_end=cue_start + len(cue) if cue != "直訓" else gloss.end("gloss"),
                    _right_is_quoted=False, _direct_gloss=True)
                coordinated_gloss = re.compile(rf"\s*[，,、]\s*(?P<gloss>{HAN}{{1,4}})也")
                suffix_start = gloss.end()
                for _ in range(8):
                    suffix = coordinated_gloss.match(segment, suffix_start)
                    if not suffix:
                        break
                    cue, kind, right_form = _direct_gloss_parts(suffix.group("gloss"))
                    if _DIRECT_GLOSS_PREDICATE_RE.search(right_form):
                        if target in left_form or target in right_form:
                            abstentions.append({
                                "reason": "direct_gloss_predicate_rhs",
                                "target": target,
                                "left_form": left_form,
                                "right_form": right_form,
                                "quote": segment[start:suffix.end()],
                            })
                        suffix_start = suffix.end()
                        continue
                    if _DIRECT_GLOSS_NEGATIVE_RHS_RE.fullmatch(right_form):
                        if target in left_form or target in right_form:
                            abstentions.append({
                                "reason": "direct_gloss_negative_rhs",
                                "target": target,
                                "left_form": left_form,
                                "right_form": right_form,
                                "quote": segment[start:suffix.end()],
                            })
                        suffix_start = suffix.end()
                        continue
                    cue_start = suffix.start("gloss")
                    if cue != "直訓":
                        cue_start += len(cue)
                    add(segment_start=seg_start, left=left_form, right=right_form,
                        cue=cue, relation_type=kind,
                        stance=_stance(segment, cue_start, start, enabled="stance" in enabled),
                        evidence_start=start, evidence_end=suffix.end(),
                        cue_start=cue_start,
                        cue_end=cue_start + len(cue) if cue != "直訓" else suffix.end("gloss"),
                        _right_is_quoted=False, _direct_gloss=True)
                    suffix_start = suffix.end()

    # All emitted claims must name the query glyph in one of their endpoints.
    # This is a candidate-scope rule, not evidence that the interpretation is true.
    return output, abstentions


def extract_relation_candidates(text: str, target: str) -> list[dict]:
    """Production entry point: keep attributed reports visible, suppress refutations and hypotheticals."""
    relations, _ = analyze_relation_candidates(text, target, modules=DEFAULT_MODULES)
    return [item for item in relations if item["author_stance"] not in {"rejected", "conditional"}]

