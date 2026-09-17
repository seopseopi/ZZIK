#!/usr/bin/env python3
"""Local persisted-message model tests, NOT a GitHub transport or AI runner.

The model checks protocol invariants with synthetic identities and receipts.
It does not prove that an AI follows instructions or that a remote review exists.
"""
import json
from pathlib import Path
import tempfile
import unittest


class Mailbox:
    def __init__(self, path):
        self.path = path
        self.events = json.loads(path.read_text()) if path.exists() else []

    def state(self, request):
        events = [e for e in self.events if e['request'] == request]
        return events[-1]['state'] if events else None

    def send(self, **event):
        if event['repo'] != 'local/fixture' or event['run'] != 'rehearsal':
            raise ValueError('wrong scope')
        if event['sender'] not in range(1, 6) or event['receiver'] not in range(1, 6):
            raise ValueError('unknown role')
        duplicate = [e for e in self.events if e['id'] == event['id']]
        if duplicate:
            if duplicate[0] != event:
                raise ValueError('event identity reused for different content')
            return False
        history = [e for e in self.events if e['request'] == event['request']]
        if not history:
            if event['state'] != 'REQUESTED':
                raise ValueError('missing request')
        else:
            first, last = history[0], history[-1]
            expected = {'REQUESTED': 'ACK', 'ACK': 'READY', 'READY': 'APPLIED'}
            superseding = event['state'] == 'SUPERSEDED' and last['state'] in expected
            if not superseding and event['state'] != expected.get(last['state']):
                raise ValueError('out-of-order or closed request')
            response = event['state'] in ('ACK', 'READY')
            pair = (first['receiver'], first['sender']) if response else (first['sender'], first['receiver'])
            if (event['sender'], event['receiver']) != pair:
                raise ValueError('wrong state owner')
            if event['head'] != first['head']:
                raise ValueError('stale request head')
            if event['state'] == 'READY' and not event.get('result_sha'):
                raise ValueError('missing result revision')
            if event['state'] == 'APPLIED':
                if not event.get('checks_passed') or event.get('result_sha') != last['result_sha']:
                    raise ValueError('result not verified')
        updated = self.events + [event]
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(updated))
        temporary.replace(self.path)
        self.events = updated
        return True


def has_cycle(edges):
    def visit(node, path):
        return node in path or any(visit(child, path | {node}) for child in edges.get(node, []))
    return any(visit(node, set()) for node in edges)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'messages.json'
        self.box = Mailbox(self.path)

    def event(self, state='REQUESTED', **changes):
        response = state in ('ACK', 'READY')
        data = dict(id=state, request='request-2-3', repo='local/fixture', run='rehearsal',
                    sender=3 if response else 2, receiver=2 if response else 3,
                    state=state, head='a' * 40)
        data.update(changes)
        return data

    def ready(self):
        for state in ('REQUESTED', 'ACK', 'READY'):
            self.box.send(**self.event(state, **({'result_sha': 'b' * 40} if state == 'READY' else {})))

    def test_five_roles_roundtrip_with_restart(self):
        for sender in range(1, 6):
            receiver = sender % 5 + 1
            for state in ('REQUESTED', 'ACK', 'READY', 'APPLIED'):
                response = state in ('ACK', 'READY')
                box = Mailbox(self.path)
                box.send(**self.event(state, id=f'{sender}-{state}', request=f'r{sender}',
                         sender=receiver if response else sender, receiver=sender if response else receiver,
                         result_sha='b' * 40, checks_passed=True))
            self.assertEqual(Mailbox(self.path).state(f'r{sender}'), 'APPLIED')

    def test_duplicate_after_lost_response_and_restart(self):
        self.box.send(**self.event())
        resumed = Mailbox(self.path)
        self.assertFalse(resumed.send(**self.event()))
        self.assertEqual(len(resumed.events), 1)

    def test_duplicate_id_changed_content_rejected(self):
        self.box.send(**self.event())
        with self.assertRaises(ValueError):
            self.box.send(**self.event(receiver=4))

    def test_scope_and_unknown_role_rejected(self):
        for changes in ({'repo': 'other/repo'}, {'run': 'old'}, {'sender': 6}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.box.send(**self.event(**changes))
        self.assertEqual(self.box.events, [])

    def test_ack_and_ready_are_not_completion(self):
        self.ready()
        self.assertEqual(self.box.state('request-2-3'), 'READY')

    def test_provider_cannot_confirm_own_delivery(self):
        self.ready()
        with self.assertRaises(ValueError):
            self.box.send(**self.event('APPLIED', sender=3, receiver=2,
                                      checks_passed=True, result_sha='b' * 40))

    def test_failed_checks_or_wrong_result_keep_request_open(self):
        self.ready()
        for passed, sha in ((False, 'b' * 40), (True, 'c' * 40)):
            with self.subTest(passed=passed), self.assertRaises(ValueError):
                self.box.send(**self.event('APPLIED', checks_passed=passed, result_sha=sha))
        self.assertEqual(Mailbox(self.path).state('request-2-3'), 'READY')

    def test_stale_head_rejected(self):
        self.box.send(**self.event())
        with self.assertRaises(ValueError):
            self.box.send(**self.event('ACK', head='c' * 40))

    def test_missing_ack_or_result_rejected(self):
        self.box.send(**self.event())
        with self.assertRaises(ValueError):
            self.box.send(**self.event('READY', result_sha='b' * 40))
        self.box.send(**self.event('ACK'))
        with self.assertRaises(ValueError):
            self.box.send(**self.event('READY'))

    def test_offline_receiver_preserves_pending_request(self):
        self.box.send(**self.event())
        self.assertEqual(Mailbox(self.path).state('request-2-3'), 'REQUESTED')
        Mailbox(self.path).send(**self.event('ACK'))
        self.assertEqual(Mailbox(self.path).state('request-2-3'), 'ACK')

    def test_old_reply_does_not_complete_new_request(self):
        self.ready()
        self.box.send(**self.event('SUPERSEDED'))
        self.box.send(**self.event(id='new', request='new-request', head='c' * 40))
        with self.assertRaises(ValueError):
            self.box.send(**self.event('APPLIED', checks_passed=True, result_sha='b' * 40))
        self.assertEqual(self.box.state('new-request'), 'REQUESTED')

    def test_dependency_cycle_detected_and_split(self):
        self.assertTrue(has_cycle({'role2': ['role3'], 'role3': ['role2']}))
        self.assertFalse(has_cycle({'role2': ['contract'], 'role3': ['contract'], 'contract': []}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
