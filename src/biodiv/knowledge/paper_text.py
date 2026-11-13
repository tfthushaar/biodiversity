"""Checks on the text of the paper: every citation, every quotation of a source, every number.

A paper is read by people who cannot see the code behind it, so each statement in it has to be
traceable by a rule that a machine enforces. These are the rules.

  * **Every citation resolves.** An author-year citation names exactly one paper, either in the
    evidence base or in the verified references. A name that matches nothing, or two papers, fails.
  * **Every reference is used.** A verified article that no sentence cites is removed, and a
    resource is named in the text.
  * **Numbers beside a citation come from the paper.** A sentence that cites a paper in the
    evidence base or a claim article may state a number only if the paper's quotes contain it.
  * **Every other number has a recorded origin.** A number in the prose that is not a data value
    (those are filled in by the build) must be registered with where it comes from: a value in a
    metrics file, a constant in the code, or a line in a document. The check reads the origin and
    confirms the number is there, so a number cannot be typed from memory.
  * **No preprints.** The prose names no preprint server except to say none was used.
"""

from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from biodiv.knowledge.references import first_surname
from biodiv.knowledge.verify import Problem, alnum, normalise, numbers_in

_NAME = r"[A-Z][\w'’-]+"
_PART = re.compile(rf"^(?P<name>{_NAME})(?: et al\.?|(?: and {_NAME}))? (?P<year>(?:19|20)\d\d)$")
_GROUP = re.compile(r"\(([^()]*)\)")
_PREPRINT_WORDS = re.compile(r"\b(arXiv|bioRxiv|medRxiv|SSRN|preprints?)\b", re.IGNORECASE)
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_NUMBER = re.compile(r"(?<![\w.,])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")
_YEAR = re.compile(r"^(?:19|20)\d\d$")
# Names that contain a digit and are not quantities.
_NAMES = re.compile(r"\b(?:top-1|Apache-2\.0|ViT-S/14|CDLA-Permissive-1\.0)\b|\bDINOv2\b")


@dataclass(frozen=True)
class Citation:
    name: str
    year: int
    sentence: str


def split_sentences(text: str) -> list[str]:
    """Sentences, without breaking at "et al." or "e.g."."""
    protected = text.replace("et al.", "et al").replace("e.g.", "e.g")
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z*(])", protected) if s.strip()]


def citations(text: str) -> tuple[list[Citation], list[str]]:
    """Every author-year citation in a parenthesis, and the parts of those parentheses that look
    like a citation but could not be read."""
    found: list[Citation] = []
    unread: list[str] = []
    for sentence in split_sentences(text):
        for group in _GROUP.findall(sentence):
            parts = [p.strip() for p in group.split(";")]
            matched = [_PART.match(p) for p in parts]
            if not any(matched):
                continue
            for part, m in zip(parts, matched, strict=True):
                if m:
                    found.append(Citation(m["name"], int(m["year"]), sentence))
                else:
                    unread.append(part)
    return found, unread


def _strip_for_numbers(sentence: str) -> str:
    """What is left of a sentence once citations, table and figure labels and dates are removed."""
    def drop_citation(m: re.Match[str]) -> str:
        return " " if _PART.match(m.group(1).split(";")[0].strip()) else m.group(0)

    s = _GROUP.sub(drop_citation, sentence)
    s = re.sub(r"\b(?:Tables?|Figures?|Sections?)\s+\d+(?:\.\d+)?", " ", s)
    s = _NAMES.sub(" ", s)
    return re.sub(rf"\b\d{{1,2}} (?:{_MONTHS}) \d{{4}}", " ", s)


def body_of(text: str) -> str:
    """The paper without its reference list, which is generated from verified records."""
    return text.split("\n## References", 1)[0]


def check_text(body: str, evidence: dict[str, Any], refs: dict[str, Any]) -> list[Problem]:
    problems: list[Problem] = []
    index: dict[tuple[str, int], list[tuple[str, str]]] = {}
    for key, s in (evidence.get("sources") or {}).items():
        name = alnum(first_surname(s["authors"]))
        index.setdefault((name, s["year"]), []).append(("evidence", key))
    for key, a in (refs.get("articles") or {}).items():
        name = alnum(first_surname(a["authors"]))
        index.setdefault((name, a["year"]), []).append(("reference", key))

    quotes_of: dict[tuple[str, str], list[str]] = {}
    for row in [*evidence.get("playbooks", []), *evidence.get("impact_findings", [])]:
        quotes_of.setdefault(("evidence", row["source"]), []).extend(row.get("quotes", []))
    for key, a in (refs.get("articles") or {}).items():
        quotes_of[("reference", key)] = list(a.get("quotes", []))

    cited: set[tuple[str, str]] = set()
    found, unread = citations(body)
    for part in unread:
        problems.append(Problem("text", f"a citation could not be read: {part!r}"))
    by_sentence: dict[str, list[tuple[str, str]]] = {}
    for c in found:
        hits = index.get((alnum(c.name), c.year), [])
        if not hits:
            problems.append(Problem("text", f"cites {c.name} {c.year}, which is in neither the "
                                            "evidence base nor the verified references"))
        elif len(hits) > 1:
            problems.append(Problem("text", f"{c.name} {c.year} names more than one paper: {hits}"))
        else:
            cited.add(hits[0])
            by_sentence.setdefault(c.sentence, []).append(hits[0])

    for key in refs.get("articles") or {}:
        if ("reference", key) not in cited:
            problems.append(Problem(f"articles.{key}", "is in the references but no sentence cites "
                                                       "it: remove it or cite it"))
    for key, r in (refs.get("resources") or {}).items():
        if r["mention"] not in body:
            problems.append(Problem(f"resources.{key}", f"is credited but the text never names "
                                                        f"{r['mention']!r}"))

    # A number beside a citation must be one the cited paper's quotes contain.
    for sentence, sources in by_sentence.items():
        pool: set[str] = set()
        graded = False
        for kind, key in sources:
            role = "evidence" if kind == "evidence" else (refs["articles"][key].get("role"))
            if role in ("evidence", "claim"):
                graded = True
                pool |= numbers_in(" ".join(quotes_of.get((kind, key), [])), words=True)
        if not graded:
            continue
        stated = {n for n in numbers_in(_strip_for_numbers(sentence))}
        missing = sorted(stated - pool)
        if missing:
            problems.append(Problem("text", f"states {missing} beside a citation, but no quote "
                                            f"of the cited paper has it: {sentence[:100]!r}"))

    for sentence in split_sentences(body):
        if _PREPRINT_WORDS.search(sentence) and "did not use" not in sentence:
            problems.append(Problem("text", f"names a preprint server: {sentence[:100]!r}"))
    return problems


# ------------------------------------------------------------------ where every number comes from


def literal_numbers(template: str) -> list[str]:
    """The numbers typed into the prose of the template, in the form they are typed.

    A number the build fills in from data is a {{TOKEN}}, so it is not here. Tables, figure lines,
    headings, list numbers, citations, dates, years and the reference list are left out."""
    body = body_of(template)
    body = re.sub(r"<!-- table:.*?<!-- /table -->", " ", body, flags=re.S)
    body = re.sub(r"!\[.*?\]\(.*?\)", " ", body)
    body = re.sub(r"https?://\S+", " ", body)
    body = re.sub(r"\{\{\w+\}\}", " ", body)
    kept: list[str] = []
    for line in body.splitlines():
        if line.lstrip().startswith("#"):
            continue
        kept.append(re.sub(r"^\s*\d+\.\s+", "", line))
    out: list[str] = []
    for sentence in split_sentences("\n".join(kept)):
        for n in _NUMBER.findall(_strip_for_numbers(sentence)):
            n = n.rstrip(".,")
            if not _YEAR.match(n) and n not in out:
                out.append(n)
    return out


def _leaves(obj: Any):
    if isinstance(obj, bool):
        return
    if isinstance(obj, int | float):
        yield float(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _leaves(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _leaves(v)


def _decimals(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def _value(literal: str) -> float:
    return float(literal.rstrip("%").replace(",", ""))


def _matches(literal: str, x: float) -> bool:
    """Whether a stored value is the number typed in the paper. A rate stored as a fraction is
    quoted as a percentage to the same number of decimals, and a number typed without its sign may
    be a rate in points (4.4 for 0.0442)."""
    percent = literal.endswith("%")
    value, places = _value(literal), _decimals(literal.rstrip("%").replace(",", ""))
    if percent:
        return round(x * 100, places) == round(value, places)
    if round(x, places) == round(value, places):
        return True
    return 0 < x <= 1 and round(x * 100, places) == round(value, places)


def _at(data: Any, path: str) -> Any:
    """`results.test.answered`: the part of a metrics file a number must come from. Naming the
    place matters, because a file of model weights holds thousands of values and some will match
    any small number."""
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def _origins(entry: Any) -> list[dict[str, Any]]:
    return entry if isinstance(entry, list) else [entry]


def _verify_origin(literal: str, origin: dict[str, Any], root: Path) -> str | None:
    """None when the origin holds the number, otherwise what is wrong."""
    if "json" in origin:
        if not origin.get("path"):
            return f"the origin in {origin['json']} needs a path"
        data = _at(json.loads((root / origin["json"]).read_text(encoding="utf-8")), origin["path"])
        if "length" in origin:
            return None if len(data) == _value(literal) else (
                f"{origin['json']} {origin['path']} has {len(data)} items, not {literal}")
        if not any(_matches(literal, x) for x in _leaves(data)):
            return f"is not a value at {origin['path']} in {origin['json']}"
        return None
    if "code" in origin:
        module, _, name = origin["code"].partition(":")
        try:
            value = getattr(importlib.import_module(module), name)
        except (ImportError, AttributeError):
            return f"{origin['code']} does not exist"
        return None if _value(literal) == float(value) else f"{origin['code']} is {value}"
    if "doc" in origin:
        text = (root / origin["doc"]).read_text(encoding="utf-8")
        wanted = origin.get("contains", literal)
        if wanted not in text and normalise(wanted) not in normalise(text):
            return f"{origin['doc']} does not contain {wanted!r}"
        return None
    if "external" in origin:
        return None if origin.get("checked_on") and origin.get("how") else (
            "an external figure needs checked_on and how")
    return "names no origin (json, code, doc or external)"


def check_numbers(literals: list[str], registry: dict[str, Any], root: Path) -> list[Problem]:
    """Every literal number is registered, and each origin it is registered against has it."""
    problems: list[Problem] = []
    entries = registry.get("numbers") or {}
    for literal in literals:
        entry = entries.get(literal)
        where = f"number {literal}"
        if entry is None:
            problems.append(Problem(where, "is typed into the paper with no recorded origin: add "
                                           "it to docs/paper_numbers.json or make it data"))
            continue
        for origin in _origins(entry):
            try:
                wrong = _verify_origin(literal, origin, root)
            except (OSError, KeyError, IndexError, ValueError) as exc:
                wrong = f"could not be read ({type(exc).__name__}: {exc})"
            if wrong:
                problems.append(Problem(where, wrong))
    for literal in sorted(set(entries) - set(literals)):
        problems.append(Problem(f"number {literal}", "is registered but no longer in the paper: "
                                                     "remove it"))
    return problems
