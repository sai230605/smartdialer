"""Basic allocation throughput test; this is not a production benchmark."""
import argparse, tempfile, os, time, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import Database
from app.dialer import SmartDialer
from app.providers import ProviderA

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--agents', type=int, default=1000)
    p.add_argument('--borrowers', type=int, default=5000)
    args = p.parse_args()
    with tempfile.TemporaryDirectory() as td:
        d = SmartDialer(Database(os.path.join(td, 'load.db')), ProviderA())
        d.add_agents(args.agents)
        d.add_borrowers([f'load-{i}' for i in range(args.borrowers)])
        start = time.perf_counter()
        result = d.progressive_tick()
        elapsed = time.perf_counter() - start
        print(f'agents={args.agents} borrowers={args.borrowers}')
        print(f'calls_attempted={len(result["outcomes"])} elapsed_seconds={elapsed:.4f} calls_per_second={len(result["outcomes"])/max(elapsed,1e-9):.1f}')
        print('Note: local SQLite/mock-provider result; not a production capacity claim.')
if __name__ == '__main__': main()
