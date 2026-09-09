"""Brief composer (D21): a rough idea becomes `workflow/briefs/<slug>.md` from the template.

Pure over the template file. It fills the fields the pipeline reads — product repo, base
branch, working branch, coding mode — and the sections a story writer needs, then checks
the result with the SAME parsers `pipeline.py run` uses (`parse_brief_product`,
`parse_brief_coding_mode`), so there is exactly one grammar for a brief. The chat
agent's `compose_brief` tool and the Slack bridge's `@lantern <idea>` both call this;
neither carries its own idea of what a brief looks like.

What it refuses, on purpose: overwriting a brief a human wrote by hand. Composed briefs
carry a marker comment; a slug that resolves to an unmarked file is left alone.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from pipeline import CODING_MODES, parse_brief_coding_mode, parse_brief_product

REPO = Path(__file__).resolve().parents[2]
BRIEFS_DIR = REPO / "workflow" / "briefs"
TEMPLATE = BRIEFS_DIR / "_TEMPLATE.md"
MARKER = "<!-- composed by the lantern chat agent"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")

# What the run cannot start without, and what the story stage works badly without.
REQUIRED = ("title", "problem", "product_repo", "coding_mode")
RECOMMENDED = ("outcome", "must_haves")

# template section heading -> field name
SECTIONS = {
    "Problem": "problem",
    "Desired outcome": "outcome",
    "Must-haves": "must_haves",
    "Scope": "scope",
    "Non-goals": "non_goals",
    "Constraints": "constraints",
    "Existing context": "existing_context",
    "Human-in-the-loop preferences": "hitl",
}
EMPTY = "(not specified)"


SLUG_MAX = 40


def slugify(text: str) -> str:
    """A slug becomes the run id, the brief filename and the branch name — it outlives
    the sentence it came from, so truncate at a WORD boundary. `…-shows-when-eac` reads
    as a bug; `…-shows-when` reads as a name."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    if len(s) <= SLUG_MAX:
        return s or "idea"
    cut = s[:SLUG_MAX + 1]
    cut = cut[:cut.rindex("-")] if "-" in cut[1:] else cut[:SLUG_MAX]
    return cut.strip("-") or "idea"


def run_id_for(slug: str, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return f"feat-{when:%Y%m%d}-{slug}"


def _bullets(value) -> str:
    if isinstance(value, str):
        items = [v.strip().lstrip("-•* ").strip() for v in value.splitlines()]
    else:
        items = [str(v).strip() for v in (value or [])]
    items = [i for i in items if i]
    return "\n".join(f"- {i}" for i in items)


def _text(value) -> str:
    if isinstance(value, (list, tuple)):
        return _bullets(value)
    return (value or "").strip()


def _header_lines(template: str) -> list[str]:
    """The `- **Label:** …` lines of the template, in order (labels only)."""
    labels = []
    for line in template.splitlines():
        m = re.match(r"^\s*-\s*\*\*(.+?):\*\*", line)
        if m:
            labels.append(m.group(1))
        elif line.startswith("## "):
            break
    return labels


def _section_order(template: str) -> list[str]:
    return [re.sub(r"^##\s+", "", line).split("(")[0].strip()
            for line in template.splitlines() if line.startswith("## ")]


def compose(fields: dict, by: str, today: datetime | None = None,
            template_path: Path = TEMPLATE) -> dict:
    """Render a brief from `fields` and validate it the way `pipeline.py run` will.

    fields: title, problem, outcome, must_haves (list or newline text), scope, non_goals,
    constraints, existing_context, hitl, product_repo, base_branch, working_branch,
    coding_mode, developer, target_release, slug (optional; derived from the title).

    Returns {slug, run_id, markdown, missing, recommended, problems, ok}. `ok` is False
    when a REQUIRED field is empty or the rendered brief fails the pipeline's parsers —
    the caller asks the human for what is missing instead of starting a run.
    """
    today = today or datetime.now(timezone.utc)
    template = template_path.read_text(encoding="utf-8")
    f = {k: (v if v is not None else "") for k, v in (fields or {}).items()}
    title = _text(f.get("title"))
    slug = _text(f.get("slug")) or slugify(title)
    coding_mode = (_text(f.get("coding_mode")) or "human").lower()
    base_branch = _text(f.get("base_branch")) or "main"
    run_id = run_id_for(slug, today)

    values = {
        "Run ID": run_id,
        "Author": by,
        "Assigned developer": _text(f.get("developer")),
        "Date": f"{today:%Y-%m-%d}",
        "Target release": _text(f.get("target_release")),
        "Product repo": _text(f.get("product_repo")),
        "Base branch": base_branch,
        "Working branch": _text(f.get("working_branch")),
        "Coding mode": coding_mode,
    }
    out = [f"# Feature Brief: {title or EMPTY}", ""]
    for label in _header_lines(template):
        out.append(f"- **{label}:** {values.get(label, '')}".rstrip())
    for heading in _section_order(template):
        key = SECTIONS.get(heading)
        body = _text(f.get(key)) if key else ""
        if key == "must_haves" and body:
            body = _bullets(f.get("must_haves"))
        out += ["", f"## {heading}", "", body or EMPTY]
    out += ["", f"{MARKER} for {by} on {today:%Y-%m-%d} -->", ""]
    markdown = "\n".join(out)

    # coding_mode renders as 'human' when unset so the brief parses, but the human is
    # still asked — a silent default is exactly what the composer must not do.
    missing = [k for k in REQUIRED if not _text(f.get(k))]
    recommended = [k for k in RECOMMENDED if not _text(f.get(k))]
    problems: list[str] = []
    if not SLUG_RE.match(slug):
        problems.append(f"slug '{slug}' must be lowercase letters, digits and dashes (2-40 chars)")
    if coding_mode not in CODING_MODES:
        problems.append(f"coding mode must be one of {', '.join(CODING_MODES)} — got '{coding_mode}'")
    elif parse_brief_coding_mode(markdown) != coding_mode:
        problems.append("the rendered brief's coding mode does not parse — check the value")
    repo_in, base_in, work_in = parse_brief_product(markdown)
    if values["Product repo"] and repo_in != values["Product repo"]:
        problems.append("the rendered brief's product repo does not parse — check the value")
    if values["Product repo"] and base_in != base_branch:
        problems.append("the rendered brief's base branch does not parse")
    if values["Working branch"] and work_in != values["Working branch"]:
        problems.append("the rendered brief's working branch does not parse")
    if coding_mode == "auto" and not values["Product repo"]:
        problems.append("auto coding mode needs a product repo")
    return {"slug": slug, "run_id": run_id, "markdown": markdown, "missing": missing,
            "recommended": recommended, "problems": problems,
            "ok": not missing and not problems}


def brief_path(slug: str, briefs_dir: Path = BRIEFS_DIR) -> Path:
    if not SLUG_RE.match(slug or ""):
        raise ValueError(f"invalid slug '{slug}'")
    p = (briefs_dir / f"{slug}.md").resolve()
    if p.parent != briefs_dir.resolve():
        raise ValueError("brief path escaped the briefs directory")
    return p


def write_brief(slug: str, markdown: str, briefs_dir: Path = BRIEFS_DIR) -> Path:
    """Write a composed brief. A file that exists WITHOUT the composer marker was written
    by a human — never overwritten; pick another slug or pass that brief_path instead."""
    p = brief_path(slug, briefs_dir)
    if p.exists() and MARKER not in p.read_text(encoding="utf-8"):
        raise FileExistsError(f"{p.relative_to(REPO) if p.is_relative_to(REPO) else p} exists and "
                              "was written by hand — choose another slug")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown, encoding="utf-8", newline="\n")
    return p


def check_brief_file(path: Path) -> dict:
    """What `pipeline.py run` will see in an existing brief: product target, coding mode."""
    text = path.read_text(encoding="utf-8")
    repo, base, work = parse_brief_product(text)
    mode = parse_brief_coding_mode(text)
    m = re.search(r"^#\s*Feature Brief:\s*(.+)$", text, re.M)
    return {"title": (m.group(1).strip() if m else path.stem), "product_repo": repo,
            "base_branch": base or "main", "working_branch": work,
            "coding_mode": mode or "human", "composed": MARKER in text}
