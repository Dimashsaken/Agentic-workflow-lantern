"""Install the software factory into a product repository (D21).

    python pipeline.py init-product <path> [--force] [--dry-run]

One command, three effects, all inspectable before a run touches the repo:

1. Detect the stack from the files that are actually there — package.json → `npm test`,
   pyproject.toml / setup.py / setup.cfg → `pytest -q`, go.mod → `go test ./...`,
   Cargo.toml → `cargo test` — plus lint/typecheck/build commands only where the repo
   shows evidence for them (a `lint` script, a `[tool.ruff]` table, a tsconfig). A repo
   with several stacks gets the commands joined with `&&`: one red command is a red gate.
2. Write `lantern.toml` from `workflow/templates/lantern.toml` with those real commands
   (never over an existing one without --force — that file IS the product's gate, and
   the team may have tuned it).
3. Append a short "built by the Lantern software factory" block to the product's
   AGENTS.md — created when absent, appended when present, never rewritten: the block
   sits between markers, so a second run is a no-op and existing text is untouched.

Then it prints how to point a run at the repo. No database, no network, no model: this
runs on a laptop against a checkout, and the tests run it against fixture repos.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "workflow" / "templates" / "lantern.toml"
QUALITY_KEYS = ("test", "lint", "typecheck", "build")     # same order factory.py runs them
TIMEOUT_S = 900
START = "<!-- lantern-factory:start -->"
END = "<!-- lantern-factory:end -->"
NPM_DEFAULT_TEST = 'echo "Error: no test specified"'


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _node(root: Path) -> dict | None:
    pkg = root / "package.json"
    if not pkg.exists():
        return None
    try:
        data = json.loads(_read(pkg) or "{}")
    except ValueError:
        data = {}
    scripts = data.get("scripts") or {}
    deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    stack: dict = {"name": "node", "evidence": "package.json"}
    test = scripts.get("test", "")
    if test and NPM_DEFAULT_TEST not in test:
        stack["test"] = "npm test"
    else:
        stack["test"] = "npm test"   # the gate still runs it; a missing script is a red gate the team fixes
        stack.setdefault("notes", []).append(
            "package.json has no real `test` script — add one; the gate runs `npm test`")
    if "lint" in scripts:
        stack["lint"] = "npm run lint"
    if "typescript" in deps or (root / "tsconfig.json").exists():
        stack["typecheck"] = "npx tsc --noEmit"
    if "build" in scripts:
        stack["build"] = "npm run build"
    return stack


def _python(root: Path) -> dict | None:
    evidence = [n for n in ("pyproject.toml", "setup.py", "setup.cfg") if (root / n).exists()]
    if not evidence:
        return None
    stack: dict = {"name": "python", "evidence": ", ".join(evidence), "test": "pytest -q"}
    py = {}
    if (root / "pyproject.toml").exists():
        try:
            py = tomllib.loads(_read(root / "pyproject.toml"))
        except tomllib.TOMLDecodeError:
            py = {}
    tool = py.get("tool") or {}
    if "ruff" in tool or (root / "ruff.toml").exists() or (root / ".ruff.toml").exists():
        stack["lint"] = "ruff check ."
    elif "flake8" in tool or (root / ".flake8").exists():
        stack["lint"] = "flake8"
    if "mypy" in tool or (root / "mypy.ini").exists():
        stack["typecheck"] = "mypy ."
    elif "pyright" in tool or (root / "pyrightconfig.json").exists():
        stack["typecheck"] = "pyright"
    return stack


def _go(root: Path) -> dict | None:
    if not (root / "go.mod").exists():
        return None
    return {"name": "go", "evidence": "go.mod", "test": "go test ./...", "lint": "go vet ./..."}


def _rust(root: Path) -> dict | None:
    if not (root / "Cargo.toml").exists():
        return None
    return {"name": "rust", "evidence": "Cargo.toml", "test": "cargo test",
            "typecheck": "cargo check"}


DETECTORS = (_node, _python, _go, _rust)


def detect(root: Path) -> list[dict]:
    """Every stack the root shows evidence for, in a fixed order (node, python, go, rust)."""
    return [s for s in (d(root) for d in DETECTORS) if s]


def quality_commands(stacks: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in QUALITY_KEYS:
        cmds = [s[key] for s in stacks if s.get(key)]
        if cmds:
            out[key] = " && ".join(cmds)
    return out


def render_lantern_toml(commands: dict[str, str], template_text: str | None = None,
                        timeout_s: int = TIMEOUT_S) -> str:
    """The template's header comment, then a [quality] table with the real commands.
    Optional keys the repo showed no evidence for stay as commented placeholders so
    the team sees what the gate could also run."""
    template_text = template_text if template_text is not None else _read(TEMPLATE)
    header = template_text.split("[quality]", 1)[0].rstrip()
    lines = [header, "", "[quality]"]
    if "test" not in commands:
        lines.append('test = "echo TODO: set a real test command - the gate is red until you do && exit 1"')
    for key in QUALITY_KEYS:
        if key in commands:
            lines.append(f'{key} = {json.dumps(commands[key])}')
        elif key != "test":
            lines.append(f'# {key} = "..."                     # optional')
    lines.append(f"timeout_s = {timeout_s}                            # per command")
    return "\n".join(lines) + "\n"


def agents_block(commands: dict[str, str], today: datetime | None = None) -> str:
    today = today or datetime.now(timezone.utc)
    cmds = "\n".join(f"- `{k}`: `{v}`" for k, v in commands.items()) or "- (none detected yet — fill lantern.toml)"
    return (
        f"{START}\n"
        "## Built by the Lantern software factory\n\n"
        f"Since {today:%Y-%m-%d} this repository is worked on by the Lantern software factory "
        "(agents propose, code disposes). Feature runs research, plan, implement and verify "
        "changes here through fixed stages with human gates. What that means for anyone — "
        "human or agent — working in this checkout:\n\n"
        "- The coding agent works on `feat/*`, `fix/*` or `proto/*` branches only, commits as "
        "`lantern-bot`, and never pushes or merges itself; a human reviews every pull request.\n"
        "- After every coding turn the commands in `lantern.toml` run **as code**; only red "
        "output goes back to the agent, for a bounded number of fix rounds, and nothing is "
        "handed off while a command fails. Keep them truthful — they are the gate:\n"
        f"{cmds}\n"
        "- Commits outside the approved plan's write scope are refused at handoff.\n"
        "- Regression tests the factory writes live under `lantern/regressions/`; keep the test "
        "command covering that directory.\n"
        f"{END}\n"
    )


def how_to_point(root: Path) -> str:
    return (
        "Point a run at this repo:\n"
        f"  - in a brief:   - **Product repo:** {root}\n"
        f"  - on the CLI:   python pipeline.py run workflow/briefs/<slug>.md --product-repo \"{root}\" "
        "[--coding-mode auto]\n"
        f"  - existing run: python pipeline.py set-product <run-id> --repo \"{root}\" --branch main\n"
        "  - from Chat:    ask Lantern to start a run and name this path as the product repo\n"
        "  - in Mission Control: /run/<run-id>/repo (the picker offers repos under LANTERN_WORKSPACE_ROOTS)"
    )


def install(path: str | Path, force: bool = False, dry_run: bool = False,
            template_path: Path = TEMPLATE, today: datetime | None = None) -> dict:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"{root} is not a directory")
    stacks = detect(root)
    commands = quality_commands(stacks)
    toml_path = root / "lantern.toml"
    agents_path = root / "AGENTS.md"
    result = {"root": str(root), "stacks": stacks, "commands": commands,
              "toml": str(toml_path), "toml_action": "unchanged",
              "agents": str(agents_path), "agents_action": "unchanged",
              "notes": [n for s in stacks for n in s.get("notes", [])], "dry_run": dry_run}
    if not stacks:
        result["notes"].append("no known stack detected (package.json, pyproject.toml/setup.py, "
                               "go.mod, Cargo.toml) — lantern.toml carries a TODO test command")

    toml_text = render_lantern_toml(commands, _read(template_path) if template_path.exists() else "")
    if toml_path.exists() and not force:
        result["toml_action"] = "kept (exists; --force overwrites)"
    else:
        result["toml_action"] = "overwritten" if toml_path.exists() else "created"
        if not dry_run:
            toml_path.write_text(toml_text, encoding="utf-8", newline="\n")
    result["toml_text"] = toml_text

    existing = _read(agents_path) if agents_path.exists() else None
    block = agents_block(commands, today)
    if existing is not None and START in existing:
        result["agents_action"] = "unchanged (block present)"
    elif existing is not None:
        result["agents_action"] = "appended"
        if not dry_run:
            sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
            agents_path.write_text(existing + sep + block, encoding="utf-8", newline="\n")
    else:
        result["agents_action"] = "created"
        if not dry_run:
            agents_path.write_text(f"# {root.name}\n\n" + block, encoding="utf-8", newline="\n")
    result["how_to_point"] = how_to_point(root)
    return result


def report(res: dict) -> str:
    lines = [f"Lantern software factory -> {res['root']}" + ("  (dry run)" if res["dry_run"] else "")]
    if res["stacks"]:
        for s in res["stacks"]:
            cmds = ", ".join(f"{k}={s[k]}" for k in QUALITY_KEYS if s.get(k))
            lines.append(f"  stack {s['name']:<7} ({s['evidence']}): {cmds}")
    else:
        lines.append("  stack: none detected")
    lines.append(f"  lantern.toml: {res['toml_action']}")
    lines.append(f"  AGENTS.md:    {res['agents_action']}")
    for n in res["notes"]:
        lines.append(f"  note: {n}")
    lines.append("")
    lines.append(res["how_to_point"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lantern init-product",
                                 description="install the factory's quality gate into a product repo")
    ap.add_argument("path")
    ap.add_argument("--force", action="store_true", help="overwrite an existing lantern.toml")
    ap.add_argument("--dry-run", action="store_true", help="show what would be written, write nothing")
    a = ap.parse_args(argv)
    try:
        res = install(a.path, force=a.force, dry_run=a.dry_run)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(report(res))
    if a.dry_run:
        print("\n--- lantern.toml ---\n" + res["toml_text"])
    return 0 if res["stacks"] else 1


if __name__ == "__main__":
    sys.exit(main())
