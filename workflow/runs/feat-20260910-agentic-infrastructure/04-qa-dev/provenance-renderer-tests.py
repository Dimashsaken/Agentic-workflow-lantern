"""Independent drawer controls. Synthetic rows; no DB, model or approvals."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools/mission-control'))
from test_drawer import DrawerTests, RUN
from fakes import run_row
import app
import drawer


class ProvenanceIdentityTests(DrawerTests):
    def test_cross_run_receipt_never_shows_verified_label(self):
        execution = self.qa_exec()
        execution['output'] = {'provenance': {'status': 'verified', 'identity': {
            'execution_key': self.key, 'run_id': 'other-run'}}}
        model = self.load(run_row(id=RUN, status='waiting_gate', current_stage='04-qa-dev'), execution)
        html = drawer.render_drawer(model, app.render_markdown, app.STAGE_META)
        self.assertIn('No verified manifest recorded', html)
        self.assertNotIn('Controller verified at completion', html)

    def test_malformed_output_string_is_unverified(self):
        execution = self.qa_exec()
        execution['output'] = '{broken'
        model = self.load(run_row(id=RUN, status='waiting_gate', current_stage='04-qa-dev'), execution)
        html = drawer.render_drawer(model, app.render_markdown, app.STAGE_META)
        self.assertIn('No verified manifest recorded', html)

    def test_test_link_names_are_literal_text(self):
        execution = self.qa_exec()
        execution['output'] = json.dumps({'provenance': {'status':'verified',
            'identity': {'execution_key':self.key, 'run_id':RUN},
            'test_links': {'AC-10': ['café-🧪-<probe>']}}})
        model = self.load(run_row(id=RUN, status='waiting_gate', current_stage='04-qa-dev'), execution)
        html = drawer.render_drawer(model, app.render_markdown, app.STAGE_META)
        self.assertIn('café-🧪-&lt;probe&gt;', html)
        self.assertNotIn('<probe>', html)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProvenanceIdentityTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
