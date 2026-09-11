import os
import copy
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from qa_network import rule_plan, LinuxNamespaceFirewall, normalize_rules, local_container_cgroup
from qa_transport import Destination, Policy, TransportHeld

class Rules(unittest.TestCase):
    def setUp(self):
        self.policy = Policy('test:qa:1', [Destination('https://allowed.test', ('203.0.113.1',), 101)], created_at=100, test_only=True).document()

    def test_recorder_all_three_hooks_drop_before_nat(self):
        plan = rule_plan('recorder', '172.30.0.2', 8080, '172.30.0.3', self.policy)
        chains = [x['add']['chain'] for x in plan['nftables'] if 'chain' in x['add']]
        self.assertEqual({c['hook'] for c in chains}, {'input','output','forward'})
        self.assertTrue(all(c['policy']=='drop' and c['prio']==-150 for c in chains))
        rules = [x['add']['rule'] for x in plan['nftables'] if 'rule' in x['add']]
        self.assertEqual(len(rules),2)
        self.assertNotIn('udp',str(rules))
        self.assertNotIn('127.0.0.11',str(rules))

    def test_gateway_permits_only_recorder_and_pinned_endpoint(self):
        plan = rule_plan('gateway','172.30.0.2',8080,'172.30.0.3',self.policy)
        rules = [x['add']['rule'] for x in plan['nftables'] if 'rule' in x['add']]
        self.assertEqual(len(rules),4)
        self.assertTrue(all(x['chain'] != 'forward' for x in rules))
        self.assertIn('203.0.113.1', str(rules))
        self.assertNotIn('allowed.test', str(rules))

    def test_readback_must_match_rules_not_just_nonempty(self):
        plan = rule_plan('recorder','172.30.0.2',8080,'172.30.0.3',self.policy)
        observed = {'nftables': [x['add'] for x in plan['nftables']]}
        self.assertEqual(normalize_rules(observed),normalize_rules(plan,planned=True))
        observed['nftables'][-1]['rule']['expr'][-1] = {'drop':None}
        fresh = rule_plan('recorder','172.30.0.2',8080,'172.30.0.3',self.policy)
        self.assertNotEqual(normalize_rules(observed),normalize_rules(fresh,planned=True))

    def test_readback_groups_chains_but_preserves_order_within_chain(self):
        plan = rule_plan('gateway','172.30.0.2',8080,'172.30.0.3',self.policy)
        observed = {'nftables': sorted([copy.deepcopy(x['add']) for x in plan['nftables']],
                                    key=lambda x: x.get('rule',{}).get('chain',''))}
        self.assertEqual(normalize_rules(observed), normalize_rules(plan, planned=True))
        positions = [i for i,x in enumerate(observed['nftables']) if x.get('rule',{}).get('chain')=='output']
        a,b=positions
        observed['nftables'][a],observed['nftables'][b]=observed['nftables'][b],observed['nftables'][a]
        self.assertNotEqual(normalize_rules(observed), normalize_rules(plan, planned=True))

    def test_local_cgroup_requires_exact_container_component(self):
        container='a'*64
        self.assertTrue(local_container_cgroup(container,'0::/system.slice/docker-'+container+'.scope'))
        self.assertTrue(local_container_cgroup(container,'7:memory:/docker/'+container))
        for value in ('0::/', '0::/docker/'+container+'0', '0::/docker-'+container+'.scope.fake',
                      '0::/docker/'+'b'*64, 'bad:/docker/'+container):
            with self.subTest(value=value):
                self.assertFalse(local_container_cgroup(container,value))

    def test_docker_commands_pin_local_socket_despite_remote_environment(self):
        firewall=object.__new__(LinuxNamespaceFirewall)
        firewall.socket=Path('/var/run/docker.sock')
        firewall.socket_identity=(1,2)
        firewall.check_socket=Mock(return_value=(1,2))
        firewall.run=Mock(return_value=SimpleNamespace(stdout='[]'))
        with patch.dict(os.environ,{'DOCKER_HOST':'tcp://remote.invalid:2375','DOCKER_CONTEXT':'remote'}):
            firewall.command(['docker','inspect','a'*64])
        argv=firewall.run.call_args.args[0]
        self.assertEqual(argv,['docker','--host','unix://'+str(firewall.socket),'inspect','a'*64])
        firewall.check_socket.return_value=(1,3)
        with self.assertRaises(TransportHeld):
            firewall.command(['docker','inspect','a'*64])
        self.assertEqual(firewall.run.call_count,1)

    def test_remote_pid_collision_refuses_before_namespace_use(self):
        import json
        from qa_transport import digest
        container='a'*64
        row={'Id':container,'State':{'Running':True,'Pid':1234},
             'HostConfig':{'NetworkMode':'bridge','ReadonlyRootfs':True,'CapDrop':['ALL']},
             'Config':{'Labels':{'lantern.qa.execution':digest('test:qa:1')}}}
        firewall=object.__new__(LinuxNamespaceFirewall)
        firewall.command=Mock(return_value=json.dumps([row]))
        with patch.object(Path,'read_text',return_value='0::/docker/'+'b'*64), \
                patch.object(Path,'stat',side_effect=AssertionError('must not use unbound namespace')):
            with self.assertRaisesRegex(TransportHeld,'exact local QA container'):
                firewall.inspect(container,'test:qa:1')

    def test_desktop_refuses_before_commands(self):
        with patch('qa_network.os.name','nt'), self.assertRaises(TransportHeld):
            LinuxNamespaceFirewall(run=lambda *a,**k:self.fail('command ran'))

if __name__ == '__main__':
    unittest.main()
