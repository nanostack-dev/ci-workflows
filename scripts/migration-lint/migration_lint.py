#!/usr/bin/env python3
"""Lint the Postgres migrations a pull request adds or changes.

Two layers, one report:

1. squawk (https://github.com/sbdchd/squawk) for lock and rewrite hazards, run
   with a shared rule set (see BASE_EXCLUDED_RULES) and a few false positives
   filtered out where this script has more context than squawk does.
2. Custom checks for what squawk cannot see because it does not know how
   golang-migrate or TimescaleDB run a file:

   concurrently-alone  A statement that cannot run in a transaction block
                       (CREATE/DROP INDEX CONCURRENTLY, REINDEX CONCURRENTLY,
                       DETACH PARTITION CONCURRENTLY, CREATE INDEX WITH
                       timescaledb.transaction_per_chunk) must be the only
                       statement in its file. golang-migrate sends a
                       multi-statement file as one query, which Postgres runs
                       in an implicit transaction.
   update-backfill     An UPDATE of a table the file did not create is a
                       backfill: it rewrites every row it matches in the
                       migration's transaction.
   unbounded-delete    A DELETE without a WHERE that bounds the rows.
   hypertable-index    CREATE INDEX on a TimescaleDB hypertable must use
                       WITH (timescaledb.transaction_per_chunk); CONCURRENTLY
                       is not supported there.

   Opt-outs are comments directly before (or inside) the statement:

       -- lint: allow-backfill <reason>           update-backfill, unbounded-delete
       -- lint: allow-hypertable-index <reason>  hypertable-index

   A reason is required. concurrently-alone has no opt-out: the migration fails
   at runtime otherwise.

Only the files a change adds or modifies are linted (--base), because
migrations are append-only and history would only produce noise.

Exit status: 0 clean, 1 findings, 2 the linter could not run (a missing base or
squawk binary is an error, never a silent pass).
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# Rules switched off for every caller, and why. A caller can add more with
# --exclude-rules, and can silence one statement with `-- squawk-ignore <rule>`.
BASE_EXCLUDED_RULES: Dict[str, str] = {
    "require-lock-timeout": (
        "wants SET lock_timeout in the file, which adds a second statement and "
        "breaks CREATE INDEX CONCURRENTLY (concurrently-alone)"
    ),
    "require-statement-timeout": (
        "wants SET statement_timeout in the file, same conflict as "
        "require-lock-timeout"
    ),
    "prefer-robust-stmts": (
        "asks for BEGIN/COMMIT around the file; golang-migrate already runs a "
        "file in one transaction, and a transaction block is exactly what "
        "CONCURRENTLY cannot run in"
    ),
    "prefer-text-field": "style, not safety: varchar(n) is the repositories' convention",
    "prefer-bigint-over-int": "style, not safety",
    "prefer-bigint-over-smallint": "style, not safety",
    "prefer-identity": "style, not safety",
    "prefer-timestamptz": "style, not safety",
    "ban-drop-constraint": (
        "relaxing a constraint is an expand-phase step with a brief lock; "
        "ban-drop-column and ban-drop-table still guard data loss"
    ),
    "ban-drop-not-null": "same as ban-drop-constraint",
}

DIRECTIVE_RE = re.compile(r"^\s*lint:\s*allow-([A-Za-z0-9-]+)\b[ \t]*(.*?)\s*$", re.S)
KNOWN_DIRECTIVES = {"backfill", "hypertable-index"}
MIN_REASON_CHARS = 3


# --------------------------------------------------------------------------
# SQL tokenizer
# --------------------------------------------------------------------------

@dataclass
class Token:
    kind: str  # word | ident | string | dollar | number | punct
    text: str
    off: int
    upper: str = ""

    def is_word(self, *names: str) -> bool:
        return self.kind == "word" and self.upper in names


@dataclass
class Comment:
    line: int  # 1-based
    text: str


@dataclass
class Statement:
    toks: List[Token]
    comments: List[Comment]
    start: int
    end: int
    start_line: int
    end_line: int


_WORD_START = re.compile(r"[A-Za-z_\u0080-\U0010ffff]")
_WORD = re.compile(r"[A-Za-z_\u0080-\U0010ffff][A-Za-z0-9_$\u0080-\U0010ffff]*")
_NUMBER = re.compile(r"[0-9][0-9A-Za-z_.]*")
_DOLLAR_TAG = re.compile(r"\$([A-Za-z_\u0080-\U0010ffff][A-Za-z0-9_\u0080-\U0010ffff]*)?\$")


class LineIndex:
    def __init__(self, src: str) -> None:
        self._starts = [0] + [m.end() for m in re.finditer(r"\n", src)]

    def line(self, off: int) -> int:
        return bisect.bisect_right(self._starts, off)


def split_statements(src: str) -> List[Statement]:
    """Split a migration into statements, honouring comments, quoting and
    dollar quoting. A trailing comment on the line of a statement's `;`
    belongs to that statement; every other comment belongs to the next one."""
    lines = LineIndex(src)
    n = len(src)
    i = 0
    statements: List[Statement] = []
    toks: List[Token] = []
    pending: List[Comment] = []
    last: Optional[Statement] = None
    seen_since_last = False

    def add_comment(off: int, text: str) -> None:
        nonlocal seen_since_last
        c = Comment(lines.line(off), text)
        if last is not None and not seen_since_last and c.line == last.end_line:
            last.comments.append(c)
        else:
            pending.append(c)

    def flush(end: int) -> None:
        nonlocal toks, pending, last, seen_since_last
        if toks:
            st = Statement(
                toks=toks,
                comments=pending,
                start=toks[0].off,
                end=end,
                start_line=lines.line(toks[0].off),
                end_line=lines.line(max(end - 1, toks[0].off)),
            )
            statements.append(st)
            last = st
            seen_since_last = False
            pending = []
        toks = []

    while i < n:
        ch = src[i]
        if ch in " \t\r\n\f\v":
            i += 1
        elif src.startswith("--", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            add_comment(i, src[i + 2 : j])
            i = j
        elif src.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith("/*", j):
                    depth += 1
                    j += 2
                elif src.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            add_comment(i, src[i + 2 : max(j - 2, i + 2)])
            i = j
        elif ch == ";":
            seen_since_last = True
            flush(i + 1)
            i += 1
        else:
            seen_since_last = True
            if ch == "'":
                tok, i = _read_string(src, i, escapes=False)
            elif ch == '"':
                j = i + 1
                while j < n:
                    if src[j] == '"':
                        if src.startswith('""', j):
                            j += 2
                            continue
                        break
                    j += 1
                tok, i = Token("ident", src[i : j + 1], i), min(j + 1, n)
            elif ch == "$" and (m := _DOLLAR_TAG.match(src, i)):
                close = src.find(m.group(0), m.end())
                j = n if close < 0 else close + len(m.group(0))
                tok, i = Token("dollar", src[i:j], i), j
            elif _WORD_START.match(ch):
                m = _WORD.match(src, i)
                assert m
                word = m.group(0)
                if word.lower() == "e" and src.startswith("'", m.end()):
                    tok, i = _read_string(src, m.end(), escapes=True, start=i)
                else:
                    tok, i = Token("word", word, i, word.upper()), m.end()
            elif ch.isdigit():
                m = _NUMBER.match(src, i)
                assert m
                tok, i = Token("number", m.group(0), i), m.end()
            else:
                tok, i = Token("punct", ch, i), i + 1
            toks.append(tok)
    flush(n)
    return statements


def _read_string(src: str, i: int, escapes: bool, start: Optional[int] = None) -> Tuple[Token, int]:
    n = len(src)
    j = i + 1
    while j < n:
        if escapes and src[j] == "\\":
            j += 2
            continue
        if src[j] == "'":
            if src.startswith("''", j):
                j += 2
                continue
            break
        j += 1
    end = min(j + 1, n)
    begin = i if start is None else start
    return Token("string", src[begin:end], begin), end


# --------------------------------------------------------------------------
# Statement parsing helpers
# --------------------------------------------------------------------------

def norm_ident(tok: Token) -> str:
    if tok.kind == "ident":
        return tok.text[1:-1].replace('""', '"')
    return tok.text.lower()


def qualified_name(toks: Sequence[Token], i: int) -> Tuple[Optional[str], int]:
    """Read `[schema.]name`, returning the last component (schema is ignored)."""
    if i >= len(toks) or toks[i].kind not in ("word", "ident"):
        return None, i
    name = norm_ident(toks[i])
    i += 1
    while i + 1 < len(toks) and toks[i].text == "." and toks[i + 1].kind in ("word", "ident"):
        name = norm_ident(toks[i + 1])
        i += 2
    return name, i


def name_from_string(text: str) -> str:
    inner = text[1:-1] if text[:1] == "'" else text
    last = inner.split(".")[-1].strip()
    if last.startswith('"') and last.endswith('"') and len(last) >= 2:
        return last[1:-1].replace('""', '"')
    return last.lower()


def has_sequence(toks: Sequence[Token], *words: str) -> bool:
    """True if `words` appear consecutively, with `.` matched literally."""
    n = len(words)
    for i in range(len(toks) - n + 1):
        if all(
            (toks[i + k].text == w) if w == "." else (toks[i + k].kind == "word" and toks[i + k].upper == w)
            for k, w in enumerate(words)
        ):
            return True
    return False


@dataclass
class CreateIndex:
    concurrently: bool
    table: Optional[str]
    transaction_per_chunk: bool


def parse_create_index(toks: Sequence[Token]) -> Optional[CreateIndex]:
    if not (len(toks) > 1 and toks[0].is_word("CREATE")):
        return None
    i = 1
    if i < len(toks) and toks[i].is_word("UNIQUE"):
        i += 1
    if not (i < len(toks) and toks[i].is_word("INDEX")):
        return None
    i += 1
    concurrently = False
    if i < len(toks) and toks[i].is_word("CONCURRENTLY"):
        concurrently = True
        i += 1
    if i + 2 < len(toks) and toks[i].is_word("IF") and toks[i + 1].is_word("NOT") and toks[i + 2].is_word("EXISTS"):
        i += 3
    if i < len(toks) and not toks[i].is_word("ON"):
        i += 1  # the index name
    table = None
    if i < len(toks) and toks[i].is_word("ON"):
        i += 1
        if i < len(toks) and toks[i].is_word("ONLY"):
            i += 1
        table, _ = qualified_name(toks, i)
    return CreateIndex(
        concurrently=concurrently,
        table=table,
        transaction_per_chunk=has_sequence(toks, "TIMESCALEDB", ".", "TRANSACTION_PER_CHUNK"),
    )


def parse_create_table(toks: Sequence[Token]) -> Optional[str]:
    if not (toks and toks[0].is_word("CREATE")):
        return None
    i = 1
    while i < len(toks) and toks[i].is_word("GLOBAL", "LOCAL", "TEMPORARY", "TEMP", "UNLOGGED"):
        i += 1
    if not (i < len(toks) and toks[i].is_word("TABLE")):
        return None
    i += 1
    if i + 2 < len(toks) and toks[i].is_word("IF") and toks[i + 1].is_word("NOT") and toks[i + 2].is_word("EXISTS"):
        i += 3
    name, _ = qualified_name(toks, i)
    return name


_CREATE_HYPERTABLE = re.compile(r"create_hypertable\s*\(\s*'((?:[^']|'')*)'", re.I)


def hypertables_created_by(st: Statement) -> Set[str]:
    found: Set[str] = set()
    toks = st.toks
    for i, t in enumerate(toks):
        if t.is_word("CREATE_HYPERTABLE") and i + 2 < len(toks) and toks[i + 1].text == "(":
            if toks[i + 2].kind == "string":
                found.add(name_from_string(toks[i + 2].text))
        elif t.kind == "dollar":
            for m in _CREATE_HYPERTABLE.finditer(t.text):
                found.add(name_from_string("'" + m.group(1) + "'"))
    table = parse_create_table(toks)
    if table and (has_sequence(toks, "TSDB", ".", "HYPERTABLE") or has_sequence(toks, "TIMESCALEDB", ".", "HYPERTABLE")):
        found.add(table)
    return found


def requires_no_transaction(toks: Sequence[Token]) -> Optional[str]:
    """Describe why a statement cannot run in a transaction block, if it cannot."""
    if not toks:
        return None
    ci = parse_create_index(toks)
    if ci:
        if ci.concurrently:
            return "CREATE INDEX CONCURRENTLY"
        if ci.transaction_per_chunk:
            return "CREATE INDEX ... WITH (timescaledb.transaction_per_chunk)"
        return None
    first = toks[0]
    if first.is_word("DROP") and len(toks) > 2 and toks[1].is_word("INDEX") and toks[2].is_word("CONCURRENTLY"):
        return "DROP INDEX CONCURRENTLY"
    if first.is_word("REINDEX") and any(t.is_word("CONCURRENTLY") for t in toks):
        return "REINDEX ... CONCURRENTLY"
    if first.is_word("ALTER") and any(t.is_word("DETACH") for t in toks) and any(t.is_word("CONCURRENTLY") for t in toks):
        return "ALTER TABLE ... DETACH PARTITION ... CONCURRENTLY"
    return None


# --------------------------------------------------------------------------
# Data-modifying statements
# --------------------------------------------------------------------------

@dataclass
class Dml:
    kind: str  # UPDATE | DELETE
    table: Optional[str]
    bounded: bool  # DELETE: has a WHERE that limits rows
    line: int


_START_PREV = {";", "(", ")"}
_BLOCK_WORDS = {"BEGIN", "THEN", "ELSE", "LOOP", "DECLARE"}


def _dml_at(toks: Sequence[Token], i: int, base_line: int, line_of) -> Optional[Dml]:
    """Parse UPDATE/DELETE at toks[i] (already known to start a DML statement)."""
    t = toks[i]
    j = i + 1
    if t.is_word("UPDATE"):
        if j < len(toks) and toks[j].is_word("ONLY"):
            j += 1
        table, k = qualified_name(toks, j)
        if table is None:
            return None
        # Require a SET before the statement ends, to avoid FOR UPDATE and the like.
        depth = 0
        for u in toks[k:]:
            if u.text == "(":
                depth += 1
            elif u.text == ")":
                depth -= 1
            elif u.text == ";" and depth <= 0:
                break
            elif depth == 0 and u.is_word("SET"):
                return Dml("UPDATE", table, True, line_of(t))
        return None
    if t.is_word("DELETE"):
        if not (j < len(toks) and toks[j].is_word("FROM")):
            return None
        j += 1
        if j < len(toks) and toks[j].is_word("ONLY"):
            j += 1
        table, k = qualified_name(toks, j)
        if table is None:
            return None
        depth = 0
        where_at = None
        for idx in range(k, len(toks)):
            u = toks[idx]
            if u.text == "(":
                depth += 1
            elif u.text == ")":
                if depth == 0:
                    break  # end of the enclosing CTE
                depth -= 1
            elif u.text == ";" and depth == 0:
                break
            elif depth == 0 and u.is_word("WHERE"):
                where_at = idx
                break
        if where_at is None:
            return Dml("DELETE", table, False, line_of(t))
        cond: List[str] = []
        depth = 0
        for u in toks[where_at + 1 :]:
            if u.text == "(":
                depth += 1
            elif u.text == ")":
                if depth == 0:
                    break
                depth -= 1
            elif u.text == ";" and depth == 0:
                break
            elif depth == 0 and u.is_word("RETURNING"):
                break
            cond.append(u.upper if u.kind == "word" else u.text)
        flat = "".join(cond)
        flat = re.sub(r"[()]", "", flat)
        bounded = bool(flat) and flat not in ("TRUE", "1=1", "1<>0", "1!=0")
        return Dml("DELETE", table, bounded, line_of(t))
    return None


def find_dml(st: Statement, line_of) -> List[Dml]:
    """UPDATE/DELETE the statement performs: as the statement itself, in a
    data-modifying CTE, or inside a DO block's body."""
    toks = st.toks
    out: List[Dml] = []
    if not toks:
        return out
    first = toks[0]
    if first.is_word("UPDATE", "DELETE"):
        d = _dml_at(toks, 0, st.start_line, line_of)
        if d:
            out.append(d)
    elif first.is_word("WITH"):
        for i in range(1, len(toks)):
            if toks[i].is_word("UPDATE", "DELETE") and toks[i - 1].text in ("(", ")"):
                d = _dml_at(toks, i, st.start_line, line_of)
                if d:
                    out.append(d)
    elif first.is_word("DO"):
        for t in toks:
            if t.kind != "dollar":
                continue
            tag = _DOLLAR_TAG.match(t.text)
            if not tag:
                continue
            open_tag = tag.group(0)
            body = t.text[len(open_tag):]
            if body.endswith(open_tag):
                body = body[: -len(open_tag)]
            inner = split_statements(body)
            body_line = line_of(t)
            for s in inner:
                # plpgsql glues keywords to statements without a `;`: split there.
                segs: List[List[Token]] = [[]]
                for u in s.toks:
                    segs[-1].append(u)
                    if u.is_word(*_BLOCK_WORDS):
                        segs.append([])
                for seg in segs:
                    if seg and seg[0].is_word("UPDATE", "DELETE"):
                        d = _dml_at(seg, 0, body_line, lambda tk, bl=body_line, b=body: bl + b.count("\n", 0, tk.off))
                        if d:
                            out.append(d)
    return out


# --------------------------------------------------------------------------
# Findings and checks
# --------------------------------------------------------------------------

@dataclass(order=True)
class Finding:
    file: str
    line: int
    rule: str
    message: str = field(compare=False)
    source: str = field(default="custom", compare=False)


def directives_of(st: Statement) -> Tuple[Dict[str, str], List[Tuple[int, str, str]]]:
    """Opt-outs attached to a statement: {name: reason}, plus malformed ones."""
    ok: Dict[str, str] = {}
    bad: List[Tuple[int, str, str]] = []
    for c in st.comments:
        for chunk in c.text.splitlines() or [c.text]:
            m = DIRECTIVE_RE.match(chunk)
            if not m:
                continue
            name, reason = m.group(1), m.group(2).strip()
            if name not in KNOWN_DIRECTIVES:
                bad.append((c.line, name, f"unknown opt-out `lint: allow-{name}` (known: {', '.join(sorted('allow-' + k for k in KNOWN_DIRECTIVES))})"))
            elif len(reason) < MIN_REASON_CHARS:
                bad.append((c.line, name, f"`lint: allow-{name}` needs a reason, e.g. `-- lint: allow-{name} table has under 10k rows`"))
            else:
                ok[name] = reason
    return ok, bad


def collect_hypertables(directory: str, extra: Iterable[str]) -> Set[str]:
    found = {name_from_string(e) for e in extra if e.strip()}
    for root, _dirs, files in os.walk(directory):
        for f in sorted(files):
            if not f.endswith(".sql") or f.endswith(".down.sql"):
                continue
            with open(os.path.join(root, f), encoding="utf-8", errors="replace") as fh:
                for st in split_statements(fh.read()):
                    found |= hypertables_created_by(st)
    return found


def custom_checks(path: str, src: str, hypertables: Set[str]) -> Tuple[List[Finding], List[Statement], Dict[int, Set[str]]]:
    findings: List[Finding] = []
    stmts = split_statements(src)
    lines = LineIndex(src)
    line_of = lambda tok: lines.line(tok.off)  # noqa: E731
    created: Set[str] = set()
    created_before: Dict[int, Set[str]] = {}
    used: Set[Tuple[int, str]] = set()

    # concurrently-alone: one finding per file, on the first such statement.
    if len(stmts) > 1:
        for st in stmts:
            why = requires_no_transaction(st.toks)
            if why:
                findings.append(Finding(path, st.start_line, "concurrently-alone",
                    f"{why} cannot run in a transaction block, and golang-migrate runs a multi-statement "
                    f"file as one implicit transaction ({len(stmts)} statements here). Move it to a file "
                    "of its own, with nothing else in it.", "custom"))
                break

    for idx, st in enumerate(stmts):
        created_before[idx] = set(created)
        allowed, bad = directives_of(st)
        for line, _name, msg in bad:
            findings.append(Finding(path, line, "lint-opt-out", msg, "custom"))

        def flag(rule: str, directive: str, line: int, message: str) -> None:
            if directive in allowed:
                used.add((idx, directive))
                return
            findings.append(Finding(path, line, rule, message + f" To accept it, add `-- lint: allow-{directive} <reason>` above the statement.", "custom"))

        ci = parse_create_index(st.toks)
        if ci and ci.table and ci.table in hypertables and ci.table not in created:
            if ci.concurrently:
                flag("hypertable-index", "hypertable-index", st.start_line,
                     f"`{ci.table}` is a TimescaleDB hypertable, which does not support CREATE INDEX CONCURRENTLY. "
                     "Use CREATE INDEX ... WITH (timescaledb.transaction_per_chunk) in a file of its own.")
            elif not ci.transaction_per_chunk:
                flag("hypertable-index", "hypertable-index", st.start_line,
                     f"CREATE INDEX on the hypertable `{ci.table}` locks out inserts for the whole build. "
                     "Use WITH (timescaledb.transaction_per_chunk), one chunk per transaction, in a file of its own.")

        for d in find_dml(st, line_of):
            if d.table in created:
                continue  # a table this file just created is empty
            if d.kind == "UPDATE":
                flag("update-backfill", "backfill", d.line,
                     f"UPDATE of the existing table `{d.table}` runs as one statement in the migration's transaction: "
                     "it holds a row lock on every row it touches until the migration ends, and on a large table "
                     "that stalls writers and bloats the WAL. Backfill in bounded batches outside the migration, "
                     "or avoid the backfill (a VIRTUAL generated column needs none).")
            elif not d.bounded:
                flag("unbounded-delete", "backfill", d.line,
                     f"DELETE FROM `{d.table}` without a WHERE that bounds the rows empties the table in one "
                     "transaction.")

        table = parse_create_table(st.toks)
        if table:
            created.add(table)

    for idx, st in enumerate(stmts):
        allowed, _bad = directives_of(st)
        for name in allowed:
            if (idx, name) not in used:
                findings.append(Finding(path, st.start_line, "lint-opt-out-unused",
                    f"`lint: allow-{name}` opts out of nothing here; remove it.", "custom-warning"))
    return findings, stmts, created_before


# --------------------------------------------------------------------------
# squawk
# --------------------------------------------------------------------------

def run_squawk(squawk: str, files: Sequence[str], excluded: Sequence[str], included: Sequence[str], pg_version: str) -> List[dict]:
    if not files:
        return []
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as cfg:
        cfg.write("# empty on purpose: the workflow inputs are the only configuration\n")
    try:
        cmd = [squawk, "--config", cfg.name, "--reporter", "json"]
        if excluded:
            cmd += ["--exclude", ",".join(excluded)]
        if included:
            cmd += ["--include", ",".join(included)]
        if pg_version:
            cmd += ["--pg-version", pg_version]
        cmd += list(files)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    finally:
        os.unlink(cfg.name)
    try:
        return json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        sys.stderr.write(f"squawk produced no JSON (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}\n")
        raise SystemExit(2)


def filter_squawk(violations: List[dict], parsed: Dict[str, Tuple[str, List[Statement], Dict[int, Set[str]]]], hypertables: Set[str]) -> List[Finding]:
    out: List[Finding] = []
    for v in violations:
        path, rule = v["file"], v["rule_name"]
        line = int(v["line"]) + 1  # squawk lines are 0-based
        src, stmts, created_before = parsed.get(path, ("", [], {}))
        idx = next((k for k, s in enumerate(stmts) if s.start_line <= line <= s.end_line), None)
        # squawk reports a statement's first line as the line before when it
        # starts the file's first token; fall back to the closest statement.
        if idx is None and stmts:
            idx = min(range(len(stmts)), key=lambda k: abs(stmts[k].start_line - line))
        st = stmts[idx] if idx is not None else None

        if rule == "require-concurrent-index-creation" and st is not None:
            ci = parse_create_index(st.toks)
            if ci and ci.table and (ci.table in created_before.get(idx, set()) or ci.table in hypertables):
                # An index on a table this file created is on an empty table.
                # An index on a hypertable cannot be concurrent: hypertable-index decides.
                continue
        if rule == "adding-field-with-default" and st is not None:
            # squawk treats every generated column as STORED, which rewrites the
            # table. A PostgreSQL 18 VIRTUAL one is metadata-only.
            col = int(v.get("column", 0))
            lines = src.splitlines(keepends=True)
            off = sum(len(x) for x in lines[: line - 1]) + col
            depth = 0
            virtual = False
            for t in (t for t in st.toks if t.off >= off):
                if t.text == "(":
                    depth += 1
                elif t.text == ")":
                    depth -= 1
                elif depth == 0 and t.is_word("VIRTUAL"):
                    virtual = True
                    break
                elif depth == 0 and (t.is_word("STORED") or t.text == ","):
                    break
            if virtual:
                continue
        out.append(Finding(path, line, rule, v["message"] + (f" {v['help']}" if v.get("help") else ""), "squawk"))
    return out


# --------------------------------------------------------------------------
# Selecting the files to lint
# --------------------------------------------------------------------------

def git(*args: str, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd, check=False)


def changed_files(directory: str, base: str, head: str) -> List[str]:
    top = git("rev-parse", "--show-toplevel", cwd=directory)
    if top.returncode != 0:
        sys.stderr.write(f"{directory} is not inside a git checkout.\n")
        raise SystemExit(2)
    root = top.stdout.strip()
    for ref in (base, head):
        if git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=root).returncode != 0:
            sys.stderr.write(
                f"Cannot resolve `{ref}`. Linting nothing would pass a change that was never checked; "
                "fetch the base (checkout fetch-depth: 0) or pass --files.\n")
            raise SystemExit(2)
    rel = os.path.relpath(os.path.abspath(directory), root)
    diff = git("diff", "--name-only", "--diff-filter=ACMR", "-z", f"{base}...{head}", "--", rel, cwd=root)
    if diff.returncode != 0:
        # No merge base (unrelated histories): compare the two trees directly.
        diff = git("diff", "--name-only", "--diff-filter=ACMR", "-z", base, head, "--", rel, cwd=root)
    if diff.returncode != 0:
        sys.stderr.write(f"git diff failed: {diff.stderr}\n")
        raise SystemExit(2)
    names = [n for n in diff.stdout.split("\0") if n.endswith(".sql")]
    cwd = os.getcwd()
    return sorted(os.path.relpath(os.path.join(root, n), cwd) for n in names)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def _esc(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def report(findings: List[Finding], github: bool) -> None:
    for f in sorted(findings):
        level = "warning" if f.source.endswith("warning") else "error"
        if github:
            print(f"::{level} file={f.file},line={f.line},title=migration-lint/{f.rule}::{_esc(f.message)}")
        print(f"{f.file}:{f.line}: {level}: [{f.rule}] {f.message}")


def write_summary(findings: List[Finding], files: Sequence[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("## Migration lint\n\n")
        fh.write(f"Linted {len(files)} migration file(s) added or modified by this change.\n\n")
        errors = [f for f in findings if not f.source.endswith("warning")]
        if not errors:
            fh.write("No findings.\n")
            return
        fh.write("| File | Line | Rule | Finding |\n| --- | --- | --- | --- |\n")
        for f in sorted(errors):
            msg = f.message.replace("|", "\\|").replace("\n", " ")
            fh.write(f"| `{f.file}` | {f.line} | `{f.rule}` | {msg} |\n")
        fh.write("\nSilence one squawk finding with `-- squawk-ignore <rule>` above the statement; the custom checks use `-- lint: allow-<name> <reason>`.\n")


def split_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [x for x in re.split(r"[\s,]+", value) if x]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migrations-dir", help="directory holding the golang-migrate *.sql files")
    ap.add_argument("--base", help="base ref or sha; lints files added or modified since the merge base")
    ap.add_argument("--head", default="HEAD", help="head ref or sha (default HEAD)")
    ap.add_argument("--files", nargs="*", help="lint exactly these files instead of diffing against --base")
    ap.add_argument("--squawk", default="squawk", help="path to the squawk binary")
    ap.add_argument("--no-squawk", action="store_true", help="run only the custom checks")
    ap.add_argument("--exclude-rules", default="", help="extra squawk rules to disable (comma or whitespace separated)")
    ap.add_argument("--include-rules", default="", help="opt-in squawk rules to enable")
    ap.add_argument("--pg-version", default="", help="Postgres version squawk should assume, e.g. 18")
    ap.add_argument("--hypertables", default="", help="extra hypertable names not created by a migration")
    ap.add_argument("--list-base-exclusions", action="store_true", help="print the shared squawk exclusions and exit")
    args = ap.parse_args(argv)

    if args.list_base_exclusions:
        for rule, why in BASE_EXCLUDED_RULES.items():
            print(f"{rule}: {why}")
        return 0

    if not args.migrations_dir or not os.path.isdir(args.migrations_dir):
        sys.stderr.write(f"Migrations directory not found: {args.migrations_dir or '(--migrations-dir not given)'}\n")
        return 2

    if args.files is not None:
        files = sorted(args.files)
    elif args.base:
        files = changed_files(args.migrations_dir, args.base, args.head)
    else:
        sys.stderr.write("Pass --base (the ref to compare against) or --files.\n")
        return 2

    github = os.environ.get("GITHUB_ACTIONS") == "true"
    if not files:
        print(f"No migration in {args.migrations_dir} was added or modified; nothing to lint.")
        write_summary([], files)
        return 0

    print(f"Linting {len(files)} migration file(s):")
    for f in files:
        print(f"  {f}")

    hypertables = collect_hypertables(args.migrations_dir, split_list(args.hypertables))
    if hypertables:
        print(f"Hypertables known from the migrations: {', '.join(sorted(hypertables))}")

    findings: List[Finding] = []
    parsed: Dict[str, Tuple[str, List[Statement], Dict[int, Set[str]]]] = {}
    for path in files:
        if not os.path.isfile(path):
            sys.stderr.write(f"Not a file: {path}\n")
            return 2
        with open(path, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        fs, stmts, created_before = custom_checks(path, src, hypertables)
        findings += fs
        parsed[path] = (src, stmts, created_before)

    if not args.no_squawk:
        excluded = list(BASE_EXCLUDED_RULES) + [r for r in split_list(args.exclude_rules) if r not in BASE_EXCLUDED_RULES]
        up_files = [f for f in files if not f.endswith(".down.sql")]
        violations = run_squawk(args.squawk, up_files, excluded, split_list(args.include_rules), args.pg_version)
        findings += filter_squawk(violations, parsed, hypertables)

    report(findings, github)
    write_summary(findings, files)
    errors = [f for f in findings if not f.source.endswith("warning")]
    if errors:
        print(f"\n{len(errors)} migration lint finding(s).")
        return 1
    print("\nMigration lint passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
