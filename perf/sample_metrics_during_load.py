from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from perf.collect_metrics_snapshot import build_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description='Sample structured metrics during load test execution')
    parser.add_argument('--metrics-url', default='http://localhost:8000/metrics')
    parser.add_argument('--output', required=True)
    parser.add_argument('--interval-seconds', type=int, default=10)
    parser.add_argument('--duration-seconds', type=int, default=250)
    args = parser.parse_args()

    started = time.time()
    samples = []

    while True:
        elapsed = time.time() - started
        if elapsed > args.duration_seconds:
            break

        samples.append(
            {
                'elapsed_seconds': round(elapsed, 2),
                'snapshot': build_snapshot(args.metrics_url),
            }
        )
        time.sleep(max(1, args.interval_seconds))

    payload = {
        'metrics_url': args.metrics_url,
        'interval_seconds': args.interval_seconds,
        'duration_seconds': args.duration_seconds,
        'sample_count': len(samples),
        'samples': samples,
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'metrics series written to {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
