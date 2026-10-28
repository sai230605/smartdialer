from contextlib import closing
from .models import AgentState, CallState, TERMINAL_CALL_STATES
from .safety_controller import SafetyController

class SmartDialer:
    def __init__(self, db, provider, safety=None):
        self.db = db
        self.provider = provider
        self.safety = safety or SafetyController()
        self.decisions = []

    def add_agents(self, count, prefix='agent'):
        with self.db.transaction() as c:
            for i in range(count):
                aid = f'{prefix}-{i+1}'
                c.execute('INSERT OR IGNORE INTO agents(id,state) VALUES (?,?)', (aid, AgentState.AVAILABLE.value))

    def add_borrowers(self, borrower_ids):
        with self.db.transaction() as c:
            for bid in borrower_ids:
                cid = f'call-{bid}'
                c.execute('INSERT OR IGNORE INTO calls(id,borrower_id,state) VALUES (?,?,?)', (cid, str(bid), CallState.QUEUED.value))

    def set_agent_state(self, agent_id, state):
        with self.db.transaction() as c:
            row = c.execute('SELECT current_call_id FROM agents WHERE id=?', (agent_id,)).fetchone()
            if not row: raise KeyError(f'Unknown agent: {agent_id}')
            # An agent with an active call cannot be made available by a stale heartbeat.
            if state == AgentState.AVAILABLE.value and row['current_call_id']:
                raise ValueError('Cannot mark an agent AVAILABLE while it owns a call')
            c.execute('UPDATE agents SET state=? WHERE id=?', (state, agent_id))

    def counts(self):
        # Connection context managers do not close SQLite connections; use closing
        # so temporary simulation databases can be removed reliably on Windows.
        with closing(self.db.connect()) as c:
            agents = {r['state']: r['n'] for r in c.execute('SELECT state,COUNT(*) n FROM agents GROUP BY state')}
            calls = {r['state']: r['n'] for r in c.execute('SELECT state,COUNT(*) n FROM calls GROUP BY state')}
        return {'agents': agents, 'calls': calls}

    def _reserve(self, limit, progressive=False):
        """Atomic allocation: BEGIN IMMEDIATE + conditional updates prevent double reservation."""
        reserved = []
        with self.db.transaction() as c:
            available = c.execute('SELECT COUNT(*) n FROM agents WHERE state=? AND current_call_id IS NULL', (AgentState.AVAILABLE.value,)).fetchone()['n']
            connected = c.execute('SELECT COUNT(*) n FROM calls WHERE state=?', (CallState.CONNECTED.value,)).fetchone()['n']
            ringing = c.execute("SELECT COUNT(*) n FROM calls WHERE state IN (?, ?, ?)", (CallState.INITIATED.value, CallState.RINGING.value, CallState.ANSWERED.value)).fetchone()['n']
            held = c.execute('SELECT COUNT(*) n FROM calls WHERE state=?', (CallState.RESERVED.value,)).fetchone()['n']
            decision = self.safety.approve(limit, available, connected, ringing, held, progressive)
            self.decisions.append(decision)
            for _ in range(decision.approved):
                agent = c.execute('SELECT id FROM agents WHERE state=? AND current_call_id IS NULL ORDER BY id LIMIT 1', (AgentState.AVAILABLE.value,)).fetchone()
                call = c.execute('SELECT id,borrower_id FROM calls WHERE state=? ORDER BY created_at,id LIMIT 1', (CallState.QUEUED.value,)).fetchone()
                if not agent or not call: break
                # Both writes occur in one serialized transaction.
                c.execute('UPDATE agents SET state=?,current_call_id=? WHERE id=? AND state=? AND current_call_id IS NULL', (AgentState.RESERVED.value, call['id'], agent['id'], AgentState.AVAILABLE.value))
                if c.execute('SELECT changes()').fetchone()[0] != 1: continue
                c.execute('UPDATE calls SET state=?,agent_id=?,version=version+1 WHERE id=? AND state=?', (CallState.RESERVED.value, agent['id'], call['id'], CallState.QUEUED.value))
                if c.execute('SELECT changes()').fetchone()[0] == 1:
                    reserved.append((call['id'], call['borrower_id'], agent['id']))
                else:
                    c.execute('UPDATE agents SET state=?,current_call_id=NULL WHERE id=?', (AgentState.AVAILABLE.value, agent['id']))
        return reserved, decision

    def progressive_tick(self, max_calls=None):
        available = self.counts()['agents'].get(AgentState.AVAILABLE.value, 0)
        requested = available if max_calls is None else min(available, max(0, max_calls))
        return self._initiate_reserved(*self._reserve(requested, progressive=True))

    def predictive_tick(self, answer_rate, avg_talk_seconds, setup_seconds=5, provider_health=1.0):
        """Estimate dial-ahead count, then pass request through SafetyController."""
        answer_rate = min(1.0, max(0.01, float(answer_rate)))
        avg_talk_seconds = max(1.0, float(avg_talk_seconds))
        setup_seconds = max(0.1, float(setup_seconds))
        health = min(1.0, max(0.0, float(provider_health)))
        counts = self.counts()
        available = counts['agents'].get(AgentState.AVAILABLE.value, 0)
        connected = counts['calls'].get(CallState.CONNECTED.value, 0)
        ringing = sum(counts['calls'].get(s.value, 0) for s in (CallState.INITIATED, CallState.RINGING, CallState.ANSWERED))
        # Expected demand during setup interval; capped at available agent count.
        requested = int((available * setup_seconds / avg_talk_seconds) / answer_rate + 0.999)
        requested = int(requested * health)
        self.safety.provider_healthy = health >= 0.5
        return self._initiate_reserved(*self._reserve(requested, progressive=False))

    def _initiate_reserved(self, reserved, decision):
        outcomes = []
        for call_id, borrower_id, agent_id in reserved:
            with self.db.transaction() as c:
                c.execute('UPDATE calls SET state=?,version=version+1 WHERE id=? AND state=?', (CallState.INITIATED.value, call_id, CallState.RESERVED.value))
                c.execute('UPDATE agents SET state=? WHERE id=? AND current_call_id=?', (AgentState.DIALING.value, agent_id, call_id))
            result = self.provider.initiate_call(call_id, borrower_id)
            with self.db.transaction() as c:
                if result.accepted:
                    c.execute('UPDATE calls SET provider_call_id=? WHERE id=?', (result.provider_call_id, call_id))
                    outcomes.append({'call_id': call_id, 'agent_id': agent_id, 'status': 'INITIATED'})
                else:
                    c.execute('UPDATE calls SET state=?,failure_reason=?,version=version+1 WHERE id=?', (CallState.FAILED.value, result.error, call_id))
                    c.execute('UPDATE agents SET state=?,current_call_id=NULL WHERE id=? AND current_call_id=?', (AgentState.AVAILABLE.value, agent_id, call_id))
                    outcomes.append({'call_id': call_id, 'agent_id': agent_id, 'status': 'FAILED', 'error': result.error})
        return {'decision': decision.__dict__, 'outcomes': outcomes}

    def handle_event(self, event_id, call_id, event_type, provider_call_id=None):
        """Idempotent event ingestion and monotonic transitions for out-of-order events."""
        event_type = event_type.upper()
        mapping = {'RINGING': CallState.RINGING, 'ANSWERED': CallState.ANSWERED,
                   'CONNECTED': CallState.CONNECTED, 'COMPLETED': CallState.COMPLETED,
                   'FAILED': CallState.FAILED, 'CANCELLED': CallState.CANCELLED}
        if event_type not in mapping: raise ValueError(f'Unsupported event type: {event_type}')
        with self.db.transaction() as c:
            inserted = c.execute('INSERT OR IGNORE INTO processed_events(event_id,call_id,event_type) VALUES (?,?,?)', (event_id, call_id, event_type)).rowcount
            if not inserted: return {'applied': False, 'reason': 'duplicate event'}
            row = c.execute('SELECT * FROM calls WHERE id=?', (call_id,)).fetchone()
            if not row: return {'applied': False, 'reason': 'unknown call'}
            current = CallState(row['state'])
            target = mapping[event_type]
            if current in TERMINAL_CALL_STATES:
                return {'applied': False, 'reason': 'call already terminal'}
            # Terminal completion can arrive after ANSWERED; late nonterminal events never regress state.
            rank = {CallState.QUEUED:0, CallState.RESERVED:1, CallState.INITIATED:2, CallState.RINGING:3, CallState.ANSWERED:4, CallState.CONNECTED:5, CallState.COMPLETED:6, CallState.FAILED:6, CallState.CANCELLED:6}
            if target not in TERMINAL_CALL_STATES and rank[target] <= rank[current]:
                return {'applied': False, 'reason': 'stale or out-of-order event'}
            if target == CallState.COMPLETED and current in (CallState.INITIATED, CallState.RINGING, CallState.ANSWERED):
                # Provider can omit intermediate events; completion is still accepted.
                pass
            c.execute('UPDATE calls SET state=?,provider_call_id=COALESCE(?,provider_call_id),version=version+1 WHERE id=?', (target.value, provider_call_id, call_id))
            agent_id = row['agent_id']
            if target == CallState.CONNECTED and agent_id:
                c.execute('UPDATE agents SET state=? WHERE id=? AND current_call_id=?', (AgentState.CONNECTED.value, agent_id, call_id))
            elif target in TERMINAL_CALL_STATES and agent_id:
                c.execute('UPDATE agents SET state=?,current_call_id=NULL WHERE id=? AND current_call_id=?', (AgentState.WRAP_UP.value, agent_id, call_id))
            return {'applied': True, 'state': target.value}

    def finish_wrap_up(self, agent_id):
        with self.db.transaction() as c:
            c.execute('UPDATE agents SET state=?,current_call_id=NULL WHERE id=? AND state=?', (AgentState.AVAILABLE.value, agent_id, AgentState.WRAP_UP.value))
            return c.execute('SELECT changes()').fetchone()[0] == 1

    def recover_stale_calls(self):
        """Conservative recovery: ambiguous initiated calls are not blindly redialed."""
        with self.db.transaction() as c:
            # Reserved calls never submitted to provider are safely returned to queue.
            rows = c.execute('SELECT id,agent_id FROM calls WHERE state=?', (CallState.RESERVED.value,)).fetchall()
            for r in rows:
                c.execute('UPDATE calls SET state=?,agent_id=NULL,version=version+1 WHERE id=?', (CallState.QUEUED.value, r['id']))
                if r['agent_id']:
                    c.execute('UPDATE agents SET state=?,current_call_id=NULL WHERE id=? AND current_call_id=?', (AgentState.AVAILABLE.value, r['agent_id'], r['id']))
            return len(rows)
