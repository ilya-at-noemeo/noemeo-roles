"""Parse decisions from Markdown.

Two forms hold a decision:

* Front matter: a `---` block at the very top of a decision record. The
  delivered text is the record's `How to apply` and `Review checks`
  sections (or the headings named by `deliver`, or everything with
  `deliver: all`).
* Section marker: a multi-line `<!-- decision` ... `-->` comment directly
  under a heading. The delivered text is the section body, up to the next
  heading of the same or a higher level.

Both hold `key: value` lines. Values are `true`/`false`, an inline list
`[a, "b, c"]` (double quotes protect commas) or a string (optionally
double-quoted). Lines starting with `#` are comments. Unknown keys are
errors, so a typo never silently drops a scope.

`parse_file` never raises on bad content: problems come back as
`FormatError`s, and a decision with any problem is dropped while the
file's other decisions are kept.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

KINDS = ("policy", "architecture", "product", "finding")
STATUSES = (
    "proposed",
    "accepted",
    "temporary",
    "superseded",
    "retired",
    "rejected",
    "open",
)
CURRENT = ("accepted", "temporary")

REQUIRED = ("id", "kind", "status", "binding", "summary")
STR_KEYS = ("id", "kind", "status", "summary", "repo", "origin")
BOOL_KEYS = ("binding", "always")
LIST_KEYS = (
    "paths",
    "commands",
    "tasks",
    "depends_on",
    "supersedes",
    "amends",
    "evidence",
)
DEFAULT_DELIVERED = ("how to apply", "review checks")

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Decision:
    id: str
    kind: str
    status: str
    binding: bool
    summary: str
    paths: tuple[str, ...]
    repo: str | None
    commands: tuple[str, ...]
    tasks: tuple[str, ...]
    always: bool
    depends_on: tuple[str, ...]
    supersedes: tuple[str, ...]
    amends: tuple[str, ...]
    origin: str
    evidence: tuple[str, ...]
    text: str
    source: Path
    heading: str | None
    content_hash: str


class FormatError(Exception):
    def __init__(self, path: Path, line: int, message: str):
        super().__init__(f"{path}:{line}: {message}")
        self.path = path
        self.line = line
        self.message = message


def _read(path: Path) -> list[str]:
    return _lines(Path(path).read_bytes().decode("utf-8"))


def _lines(raw: str) -> list[str]:
    if raw.startswith("﻿"):
        raw = raw[1:]
    return raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _headings(lines: list[str], start: int = 0) -> list[tuple[int, int, str]]:
    """(index, level, text) of each heading, skipping fenced code."""
    found = []
    fenced = in_marker = False
    for i in range(start, len(lines)):
        if in_marker:
            in_marker = lines[i].strip() != "-->"
            continue
        if _FENCE.match(lines[i]):
            fenced = not fenced
            continue
        if fenced:
            continue
        if lines[i].strip() == "<!-- decision":
            in_marker = True
            continue
        m = _HEADING.match(lines[i])
        if m:
            found.append((i, len(m.group(1)), m.group(2)))
    return found


def title_of(path: Path) -> str:
    """First `#` heading outside front matter, else the file name."""
    path = Path(path)
    try:
        lines = _read(path)
    except (OSError, UnicodeDecodeError):
        return path.name
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    for _, level, text in _headings(lines, start):
        if level == 1:
            return text
    return path.name


def _split_list(inner: str) -> list[str]:
    """Split on commas outside double quotes. Blanks outside quotes are
    dropped; blanks inside quotes are kept."""
    items: list[list[tuple[str, bool]]] = [[]]
    quoted = False
    for ch in inner:
        if ch == '"':
            quoted = not quoted
            if quoted:
                items[-1].append(("", True))  # marks a quoted item
        elif ch == "," and not quoted:
            items.append([])
        else:
            items[-1].append((ch, quoted))
    out = []
    for chars in items:
        was_quoted = any(q for _, q in chars)
        while chars and not chars[0][1] and chars[0][0].isspace():
            chars.pop(0)
        while chars and not chars[-1][1] and chars[-1][0].isspace():
            chars.pop()
        text = "".join(c for c, _ in chars)
        if text or was_quoted:
            out.append(text)
    return out


def _parse_value(raw: str):
    raw = raw.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith("["):
        if not raw.endswith("]") or raw.count('"') % 2:
            raise ValueError("unterminated list")
        return _split_list(raw[1:-1])
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1]
    return raw


def _parse_fields(
    block: list[str], first_line: int, path: Path, allow_deliver: bool
) -> tuple[dict | None, list[FormatError]]:
    """Parse `key: value` lines; first_line is the 1-based line of block[0]."""
    fields: dict = {}
    errors: list[FormatError] = []

    def err(offset: int, msg: str):
        errors.append(FormatError(path, first_line + offset, msg))

    for off, line in enumerate(block):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, rest = line.partition(":")
        key = key.strip()
        if not sep or not key:
            err(off, f"expected 'key: value', got {line.strip()!r}")
            continue
        known = (
            REQUIRED + STR_KEYS + BOOL_KEYS + LIST_KEYS + (("deliver",) if allow_deliver else ())
        )
        if key not in known:
            err(off, f"unknown key {key!r}")
            continue
        if key in fields:
            err(off, f"duplicate key {key!r}")
            continue
        try:
            value = _parse_value(rest)
        except ValueError as e:
            err(off, f"{key}: {e}")
            continue
        if key in BOOL_KEYS:
            if not isinstance(value, bool):
                err(off, f"{key} must be true or false")
                continue
        elif key in LIST_KEYS:
            if isinstance(value, bool):
                err(off, f"{key} must be a list")
                continue
            if isinstance(value, str):
                value = [value] if value else []
        elif key == "deliver":
            if isinstance(value, bool):
                err(off, "deliver must be 'all' or a list of headings")
                continue
            if isinstance(value, str):
                if value != "all":
                    err(off, "deliver must be 'all' or a list of headings")
                    continue
        else:  # string keys
            if isinstance(value, (bool, list)):
                err(off, f"{key} must be a string")
                continue
        fields[key] = (value, off)
    return fields, errors


def _finish(
    fields: dict,
    errors: list[FormatError],
    first_line: int,
    path: Path,
    text: str,
    heading: str | None,
) -> Decision | None:
    """Validate parsed fields and build the Decision, or add errors."""
    values = {k: v for k, (v, _) in fields.items()}
    for key in REQUIRED:
        if key not in values:
            errors.append(FormatError(path, first_line, f"missing required field {key!r}"))
    if "kind" in values and values["kind"] not in KINDS:
        errors.append(
            FormatError(
                path,
                first_line + fields["kind"][1],
                f"kind {values['kind']!r} is not one of {', '.join(KINDS)}",
            )
        )
    if "status" in values and values["status"] not in STATUSES:
        errors.append(
            FormatError(
                path,
                first_line + fields["status"][1],
                f"status {values['status']!r} is not one of {', '.join(STATUSES)}",
            )
        )
    if "id" in values and not values["id"].strip():
        errors.append(FormatError(path, first_line + fields["id"][1], "id is empty"))
    if errors:  # this decision's own errors: drop it
        return None

    def tup(key: str) -> tuple[str, ...]:
        return tuple(values.get(key, ()))

    data = {
        "id": values["id"].strip(),
        "kind": values["kind"],
        "status": values["status"],
        "binding": values["binding"],
        "summary": values["summary"],
        "paths": tup("paths"),
        "repo": values.get("repo") or None,
        "commands": tup("commands"),
        "tasks": tup("tasks"),
        "always": values.get("always", False),
        "depends_on": tup("depends_on"),
        "supersedes": tup("supersedes"),
        "amends": tup("amends"),
        "origin": values.get("origin", ""),
        "evidence": tup("evidence"),
        "heading": heading,
    }
    digest = hashlib.sha256(
        (json.dumps(data, sort_keys=True) + text).encode("utf-8")
    ).hexdigest()[:12]
    return Decision(text=text, source=path, content_hash=digest, **data)


def _section_end(heads: list[tuple[int, int, str]], pos: int, total: int) -> int:
    level = heads[pos][1]
    for j in range(pos + 1, len(heads)):
        if heads[j][1] <= level:
            return heads[j][0]
    return total


def _record_text(body: list[str], deliver) -> str:
    if deliver == "all":
        return "\n".join(body).strip()
    wanted = (
        DEFAULT_DELIVERED
        if deliver is None
        else tuple(h.strip().lower() for h in deliver)
    )
    heads = _headings(body)
    parts, covered_to = [], -1
    for pos, (idx, _, name) in enumerate(heads):
        if idx < covered_to or name.strip().lower() not in wanted:
            continue
        end = _section_end(heads, pos, len(body))
        parts.append("\n".join(body[idx:end]).rstrip())
        covered_to = end
    return "\n\n".join(parts).strip()


def _parse_front_matter(
    lines: list[str], path: Path
) -> tuple[list[Decision], list[FormatError], int]:
    """Returns (decisions, errors, index of first line after front matter)."""
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if close is None:
        return [], [FormatError(path, 1, "front matter is not closed by '---'")], len(lines)
    if not any(re.match(r"\s*id\s*:", ln) for ln in lines[1:close]):
        return [], [], close + 1  # other front matter, not a decision
    fields, errors = _parse_fields(lines[1:close], 2, path, allow_deliver=True)
    deliver = fields.pop("deliver", (None, 0))[0]
    body = lines[close + 1 :]
    text = _record_text(body, deliver)
    d = _finish(fields, errors, 1, path, text, None)
    return ([d] if d else []), errors, close + 1


def _parse_markers(
    lines: list[str], start: int, path: Path
) -> tuple[list[Decision], list[FormatError]]:
    decisions: list[Decision] = []
    errors: list[FormatError] = []
    heads = _headings(lines, start)
    fenced = False
    i = start
    while i < len(lines):
        line = lines[i]
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced and line.strip() == "<!-- decision":
            open_at = i
            close = next((j for j in range(i + 1, len(lines)) if lines[j].strip() == "-->"), None)
            if close is None:
                errors.append(FormatError(path, open_at + 1, "decision marker is not closed by '-->'"))
                break
            i = close
            above = open_at - 1
            while above >= start and not lines[above].strip():
                above -= 1
            pos = next((p for p, h in enumerate(heads) if h[0] == above), None)
            if pos is None:
                errors.append(
                    FormatError(path, open_at + 1, "decision marker must sit directly under a heading")
                )
                i += 1
                continue
            fields, errs = _parse_fields(
                lines[open_at + 1 : close], open_at + 2, path, allow_deliver=False
            )
            end = _section_end(heads, pos, len(lines))
            text = "\n".join(lines[close + 1 : end]).strip()
            d = _finish(fields, errs, open_at + 1, path, text, heads[pos][2])
            errors.extend(errs)
            if d:
                decisions.append(d)
        i += 1
    return decisions, errors


def parse_file(path: Path) -> tuple[list[Decision], list[FormatError]]:
    path = Path(path)
    try:
        raw = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return [], [FormatError(path, 1, f"cannot read file: {e}")]
    return parse_text(raw, path)


def parse_text(text: str, path: Path) -> tuple[list[Decision], list[FormatError]]:
    """Parse `text` as the content of `path`; the file itself is not read."""
    path = Path(path)
    lines = _lines(text)
    decisions: list[Decision] = []
    errors: list[FormatError] = []
    start = 0
    if lines and lines[0].strip() == "---":
        decisions, errors, start = _parse_front_matter(lines, path)
    md, me = _parse_markers(lines, start, path)
    return decisions + md, errors + me
