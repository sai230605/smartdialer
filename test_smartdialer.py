import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from app.database import Database
from app.dialer import SmartDialer
from app.models import AgentState, CallState
from app.providers import ProviderA, ProviderB
from app.safety_controller import SafetyController

class SmartDialerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tmp.name) / 'test.db'))
        self.dialer = SmartDialer(self.db, ProviderA(), SafetyController())
        self.dialer.add_agents(2)
        self.dialer.add_borrowers(['b1', 'b2', 'b3'])
    def tearDown(self): self.tmp.cleanup()

    def test_progressive_never_exceeds_available_agents(self):
        result = self.dialer.progressive_tick()
        self.assertEqual(len(result['outcomes']), 2)
        self.assertEqual(sum(x['status'] == 'INITIATED' for x in result['outcomes']), 2)
        self.assertEqual(self.dialer.counts()['calls'][CallState.INITIATED.value], 2)

    def test_duplicate_event_is_idempotent(self):
        result = self.dialer.progressive_tick()
        cid = result['outcomes'][0]['call_id']
        first = self.dialer.handle_event('evt-1', cid, 'CONNECTED')
        second = self.dialer.handle_event('evt-1', cid, 'CONNECTED')
        self.assertTrue(first['applied'])
        self.assertFalse(second['applied'])

    def test_out_of_order_event_does_not_regress(self):
        result = self.dialer.progressive_tick()
        cid = result['outcomes'][0]['call_id']
        self.dialer.handle_event('evt-connected', cid, 'CONNECTED')
        stale = self.dialer.handle_event('evt-ringing', cid, 'RINGING')
        self.assertFalse(stale['applied'])
        with closing(self.db.connect()) as c:
            state = c.execute('SELECT state FROM calls WHERE id=?', (cid,)).fetchone()['state']
        self.assertEqual(state, CallState.CONNECTED.value)

    def test_completion_releases_agent_to_wrap_up(self):
        result = self.dialer.progressive_tick()
        item = result['outcomes'][0]
        self.dialer.handle_event('evt-done', item['call_id'], 'COMPLETED')
        with closing(self.db.connect()) as c:
            agent = c.execute('SELECT state,current_call_id FROM agents WHERE id=?', (item['agent_id'],)).fetchone()
        self.assertEqual(agent['state'], AgentState.WRAP_UP.value)
        self.assertIsNone(agent['current_call_id'])
        self.assertTrue(self.dialer.finish_wrap_up(item['agent_id']))

    def test_provider_outage_stops_new_calls(self):
        self.dialer.safety.provider_healthy = False
        result = self.dialer.progressive_tick()
        self.assertEqual(result['decision']['approved'], 0)

    def test_recovery_requeues_unsubmitted_reservations(self):
        # Exercise recovery using a controlled RESERVED row.
        with self.db.transaction() as c:
            c.execute("UPDATE agents SET state='RESERVED',current_call_id='call-b1' WHERE id='agent-1'")
            c.execute("UPDATE calls SET state='RESERVED',agent_id='agent-1' WHERE id='call-b1'")
        self.assertEqual(self.dialer.recover_stale_calls(), 1)
        with closing(self.db.connect()) as c:
            state = c.execute("SELECT state FROM calls WHERE id='call-b1'").fetchone()['state']
        self.assertEqual(state, CallState.QUEUED.value)

    def test_provider_b_simulates_failures(self):
        db = Database(str(Path(self.tmp.name) / 'providerb.db'))
        d = SmartDialer(db, ProviderB(fail_every=1))
        d.add_agents(1)
        d.add_borrowers(['x'])
        result = d.progressive_tick()
        self.assertEqual(result['outcomes'][0]['status'], 'FAILED')
        self.assertEqual(d.counts()['agents'][AgentState.AVAILABLE.value], 1)

if __name__ == '__main__': unittest.main()
