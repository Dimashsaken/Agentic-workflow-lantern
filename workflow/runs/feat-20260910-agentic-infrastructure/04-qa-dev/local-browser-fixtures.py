"""Serve disposable renderer fixtures. No DB, Azure, auth, or pipeline execution.

QA_BASE_URL supplies a loopback URL. Production renderer/CSS/JS are imported;
all envelopes are synthetic and remain outside the repository.
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/mission-control"))
import app
import traceability as tr
import ui


def main():
    target = urlsplit(os.environ["QA_BASE_URL"])
    if target.hostname not in {"127.0.0.1", "localhost"} or target.scheme != "http":
        raise SystemExit("Fixture server requires an HTTP loopback QA_BASE_URL")
    with tempfile.TemporaryDirectory(prefix="lantern-qa-renderer-") as temp:
        root = Path(temp)
        fixture = root / "fixtures"
        criterion = {"id": "AC-4", "text": "Evidence stays readable: café 🧪", "edge_cases": []}
        refs = [{"path": "product/app.py", "line": 12},
                {"path": "04-qa-dev/<result>&'\".txt", "line": 2},
                {"path": "04-qa-dev/café-🧪.txt", "line": 7},
                {"path": "04-qa-dev/" + "long-reference-" * 24 + ".txt", "line": 1}]
        envelopes = {
            "00-story/story.json": {"acceptance_criteria": [criterion]},
            "02-pre-coding/plan.json": {"tasks": [{"id": "T4", "title": "Render evidence", "criteria": ["AC-4"]}]},
            "03-coding/handoff.json": {"commits": [{"sha": "abcd1234", "subject": "AC-4 synthetic fixture"}]},
            "05-post-coding/validation.json": {"verdict": "pass", "criteria": [{"id": "AC-4", "status": "covered", "evidence": refs}]},
        }
        for name, value in envelopes.items():
            path = fixture / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        charter = fixture / "04-qa-dev/test-charter.md"
        charter.parent.mkdir(parents=True)
        charter.write_text("## AC-4 local renderer checks\n", encoding="utf-8")
        matrix = tr.build_matrix("synthetic-renderer-fixture", fixture)
        legacy = copy.deepcopy(matrix)
        legacy["rows"][0]["verdict"]["evidence"] = "Legacy prose: <result> remains literal."
        empty = tr.build_matrix("synthetic-empty-fixture", root / "absent")
        for name, content in {
            "structured": tr.render_matrix(matrix),
            "legacy": tr.render_matrix(legacy),
            "empty": tr.render_matrix(empty),
            "validation": app.validation_table(envelopes["05-post-coding/validation.json"]),
        }.items():
            nav = " · ".join(f"<a href='/{n}.html'>{n}</a>" for n in ("structured", "legacy", "empty", "validation"))
            body = ("<main style='padding:24px;max-width:100%'><h1>Local renderer fixture</h1>"
                    "<p>Component regression only. No live service, database, authentication or gate.</p>"
                    f"<nav>{nav}</nav>{content}</main>")
            rendered = ui.page("Local renderer fixture", body, user="fixture", auto_reload=False)
            # Omit remote font requests; deterministic fallback fonts are intentional.
            rendered = rendered.replace(ui.FONTS, "")
            rendered = rendered.replace("<b>Live</b>", "<b>Fixture</b>")
            (root / f"{name}.html").write_text(rendered, encoding="utf-8")

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=root, **kwargs)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer((target.hostname, target.port), Handler)
        print("local renderer fixture ready", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
