"""Run small deterministic scenarios and print pacing/safety outcomes."""
import argparse, tempfile, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import Database
from app.dialer import SmartDialer
from app.providers import ProviderA, ProviderB
from app.models import CallState

def run_scenario(name, agents, borrowers, answer_rate, talk_time, provider_b=False, health=1.0):
    with tempfile.TemporaryDirectory() as td:
        db = Database(os.path.join(td, 'sim.db'))
        provider = ProviderB(fail_every=5) if provider_b else ProviderA()
        d = SmartDialer(db, provider)
        d.add_agents(agents)
        d.add_borrowers([f'{name}-borrower-{i}' for i in range(borrowers)])
        result = d.predictive_tick(answer_rate, talk_time, provider_health=health)
        counts = d.counts()['calls']
        initiated = sum(1 for o in result['outcomes'] if o['status'] == 'INITIATED')
        failed = sum(1 for o in result['outcomes'] if o['status'] == 'FAILED')
        print(f"{name}: answer_rate={answer_rate:.0%}, talk_time={talk_time}s, provider_health={health:.0%}")
        print(f"  safety requested={result['decision']['requested']} approved={result['decision']['approved']} reason={result['decision']['reason']}")
        print(f"  initiated={initiated}, failed={failed}, queued={counts.get(CallState.QUEUED.value,0)}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--agents', type=int, default=20)
    parser.add_argument('--borrowers', type=int, default=100)
    args = parser.parse_args()
    run_scenario('A', args.agents, args.borrowers, .20, 120)
    run_scenario('B', args.agents, args.borrowers, .50, 90)
    run_scenario('C', args.agents, args.borrowers, .70, 180, provider_b=True)
    run_scenario('D', args.agents, args.borrowers, .10, 240, provider_b=True, health=.4)
if __name__ == '__main__': main()
