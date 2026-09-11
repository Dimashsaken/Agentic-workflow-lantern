"""Cleanup must continue after partial native-host failures without widening ownership."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock

from qa_native_acceptance import Resources
from qa_transport import digest


class NativeCleanup(unittest.TestCase):
    def resources(self):
        owned = object.__new__(Resources)
        owned.key, owned.root = 'test:cleanup', Path('/tmp/lantern-external-qa-test')
        owned.processes, owned.containers, owned.networks = [], ['first', 'second'], ['network']
        owned.inspect = Mock(return_value={'Config': {'Labels': {'lantern.qa.owner': digest(owned.key)}}})
        owned.docker = Mock(return_value=json.dumps([{'Labels': {'lantern.qa.execution': digest(owned.key)},
                                                       'Containers': {}}]))
        return owned

    def test_signal_failure_does_not_skip_container_or_network_cleanup(self):
        owned = self.resources()
        process = Mock(pid=123)
        process.poll.return_value = None
        process.terminate.side_effect = PermissionError('signal refused')
        owned.processes = [process]
        result = owned.cleanup()
        self.assertFalse(result['complete'])
        self.assertEqual(result['containers_removed'], ['second', 'first'])
        self.assertEqual(result['networks_removed'], ['network'])
        self.assertEqual(result['errors'][0]['resource'], 'observer')

    def test_wrong_owner_refuses_only_that_resource_and_continues(self):
        owned = self.resources()
        owned.inspect.side_effect = [
            {'Config': {'Labels': {'lantern.qa.owner': 'someone-else'}}},
            {'Config': {'Labels': {'lantern.qa.owner': digest(owned.key)}}}]
        result = owned.cleanup()
        self.assertFalse(result['complete'])
        self.assertEqual(result['containers_removed'], ['first'])
        self.assertEqual(result['networks_removed'], ['network'])
        self.assertNotIn(unittest.mock.call('rm', '-f', 'second'), owned.docker.call_args_list)

    def test_container_remove_failure_continues_and_timeout_escalates_owned_process(self):
        owned = self.resources()
        process = Mock(pid=123)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('observer', 3), 0]
        owned.processes = [process]
        original = owned.docker.return_value
        owned.docker.side_effect = lambda *args: (_ for _ in ()).throw(
            RuntimeError('remove failed')) if args == ('rm', '-f', 'second') else original
        result = owned.cleanup()
        self.assertFalse(result['complete'])
        process.kill.assert_called_once()
        self.assertEqual(result['observers_stopped'], [123])
        self.assertEqual(result['containers_removed'], ['first'])
        self.assertEqual(result['networks_removed'], ['network'])


if __name__ == '__main__':
    unittest.main()
