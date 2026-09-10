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
import drawer
from fakes import NOW, exec_row, run_row


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
        drawer_run = "synthetic-provenance-fixture"
        drawer_key = drawer_run + ":03-coding:2"
        receipt = {"status": "verified", "identity": {
            "run_id": drawer_run, "execution_key": drawer_key,
            "product": {"head_sha": "a" * 40, "tree_sha": "b" * 40},
            "image_digest": "sha256:" + "c" * 64},
            "manifest": {"sha256": "d" * 64},
            "test_links": {"AC-10": ["quality:test", "café-🧪-<probe>"]}}
        stage = fixture / "03-coding"
        (stage / "gate.json").write_text(json.dumps({"execution_key": drawer_key,
            "passed": True, "results": [], "provenance": receipt}), encoding="utf-8")
        drawer_pages = {}
        for name in ("verified", "forged-mirror", "stale", "cross-run"):
            recorded = copy.deepcopy(receipt)
            if name == "stale":
                recorded["identity"]["execution_key"] = drawer_run + ":03-coding:1"
            if name == "cross-run":
                recorded["identity"]["run_id"] = "different-fixture-run"
            execution = exec_row(900, drawer_run, "03-coding", 2, "succeeded", NOW, 5, key=drawer_key)
            execution["output"] = {} if name == "forged-mirror" else {"provenance": recorded}
            model = drawer.load_execution(run_row(id=drawer_run, status="executing",
                current_stage="03-coding"), execution, fixture, [], NOW, validate=lambda *_: [])
            drawer_pages[name] = drawer.render_drawer(model, app.render_markdown, app.STAGE_META, fragment=False)
        for name, content in {
            "structured": tr.render_matrix(matrix),
            "legacy": tr.render_matrix(legacy),
            "empty": tr.render_matrix(empty),
            "validation": app.validation_table(envelopes["05-post-coding/validation.json"]),
            **drawer_pages,
        }.items():
            nav = " · ".join(f"<a href='/{n}.html'>{n}</a>" for n in ("structured", "legacy", "empty", "validation", *drawer_pages))
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
