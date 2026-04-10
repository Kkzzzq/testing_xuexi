from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SCENARIOS: dict[str, dict[str, object]] = {
    'hot_read': {
        'locust_file': 'perf/locust_hot_read.py',
        'threshold_profile': 'hot_read',
        'users': 120,
        'rate': 20,
        'duration': '6m',
        'dashboard_count': 20,
        'subscriptions_per_dashboard': 20,
        'extra_env': {
            'LOCUST_WAIT_MIN_SECONDS': '0.01',
            'LOCUST_WAIT_MAX_SECONDS': '0.05',
            'CACHE_TTL_SECONDS': '120',
            'DASHBOARD_EXISTS_CACHE_TTL_SECONDS': '30',
            'LOCUST_WARMUP_REQUESTS': '2',
        },
    },
    'write_conflict': {
        'locust_file': 'perf/locust_write_conflict.py',
        'threshold_profile': 'write_conflict',
        'users': 80,
        'rate': 12,
        'duration': '5m',
        'dashboard_count': 10,
        'subscriptions_per_dashboard': 5,
        'extra_env': {
            'LOCUST_WAIT_MIN_SECONDS': '0.01',
            'LOCUST_WAIT_MAX_SECONDS': '0.04',
            'CACHE_TTL_SECONDS': '120',
            'DASHBOARD_EXISTS_CACHE_TTL_SECONDS': '30',
        },
    },
    'cache_penetration': {
        'locust_file': 'perf/locust_cache_penetration.py',
        'threshold_profile': 'cache_penetration',
        'users': 100,
        'rate': 20,
        'duration': '4m',
        'dashboard_count': 5,
        'subscriptions_per_dashboard': 3,
        'extra_env': {
            'LOCUST_WAIT_MIN_SECONDS': '0.0',
            'LOCUST_WAIT_MAX_SECONDS': '0.02',
            'CACHE_TTL_SECONDS': '120',
            'DASHBOARD_EXISTS_CACHE_TTL_SECONDS': '30',
        },
    },
    'cache_breakdown': {
        'locust_file': 'perf/locust_cache_breakdown.py',
        'threshold_profile': 'cache_breakdown',
        'users': 120,
        'rate': 25,
        'duration': '4m',
        'dashboard_count': 5,
        'subscriptions_per_dashboard': 20,
        'extra_env': {
            'LOCUST_WAIT_MIN_SECONDS': '0.0',
            'LOCUST_WAIT_MAX_SECONDS': '0.01',
            'CACHE_TTL_SECONDS': '120',
            'DASHBOARD_EXISTS_CACHE_TTL_SECONDS': '30',
            'LOCUST_BREAKDOWN_WARMUP_REQUESTS': '2',
            'LOCUST_BREAKDOWN_INVALIDATE_INTERVAL_SECONDS': '2.5',
        },
    },
    'cache_avalanche': {
        'locust_file': 'perf/locust_cache_avalanche.py',
        'threshold_profile': 'cache_avalanche',
        'users': 140,
        'rate': 24,
        'duration': '5m',
        'dashboard_count': 12,
        'subscriptions_per_dashboard': 20,
        'extra_env': {
            'LOCUST_WAIT_MIN_SECONDS': '0.0',
            'LOCUST_WAIT_MAX_SECONDS': '0.02',
            'CACHE_TTL_SECONDS': '45',
            'DASHBOARD_EXISTS_CACHE_TTL_SECONDS': '15',
            'LOCUST_AVALANCHE_HOTSET_SIZE': '6',
            'LOCUST_AVALANCHE_WAVE_INTERVAL_SECONDS': '12',
        },
    },
}


def _run(cmd: list[str], *, env: dict[str, str], cwd: Path, tee_path: Path | None = None) -> int:
    stdout = subprocess.PIPE if tee_path else None
    stderr = subprocess.STDOUT if tee_path else None
    process = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=stdout, stderr=stderr, text=True)
    if tee_path is None:
        return process.wait()

    assert process.stdout is not None
    with tee_path.open('w', encoding='utf-8') as fh:
        for line in process.stdout:
            print(line, end='')
            fh.write(line)
    return process.wait()


def _write_env_dump(path: Path, env: dict[str, str], keys: list[str]) -> None:
    lines = [f'{key}={env.get(key, "")}' for key in keys]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or '=' not in line:
            continue
        key, value = line.split('=', 1)
        data[key] = value
    return data


def _locust_command(locust_file: str, host: str, users: int, rate: int, duration: str, output_prefix: Path) -> list[str]:
    locust_bin = shutil.which('locust')
    if locust_bin:
        base = [locust_bin]
    else:
        base = [sys.executable, '-m', 'locust']
    return [
        *base,
        '-f',
        locust_file,
        '--host',
        host,
        '--headless',
        '-u',
        str(users),
        '-r',
        str(rate),
        '-t',
        duration,
        '--csv',
        str(output_prefix),
        '--html',
        str(output_prefix.parent / 'locust-report.html'),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description='Run one local Locust performance scenario with seed/bootstrap, metrics, and assertions')
    parser.add_argument('--scenario', choices=sorted(SCENARIOS), required=True)
    parser.add_argument('--host', default='http://localhost:8000')
    parser.add_argument('--grafana-base-url', default=os.getenv('GRAFANA_BASE_URL', 'http://localhost:3000'))
    parser.add_argument('--dashboard-hub-base-url', default=os.getenv('DASHBOARD_HUB_BASE_URL', 'http://localhost:8000'))
    parser.add_argument('--metrics-url', default='http://localhost:8000/metrics')
    parser.add_argument('--users', type=int)
    parser.add_argument('--rate', type=int)
    parser.add_argument('--duration')
    parser.add_argument('--output-dir')
    parser.add_argument('--skip-bootstrap', action='store_true')
    parser.add_argument('--skip-metrics', action='store_true')
    parser.add_argument('--skip-assert', action='store_true')
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    profile = SCENARIOS[args.scenario]
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    result_dir = Path(args.output_dir) if args.output_dir else root / 'perf-results' / f'local-{args.scenario}-{timestamp}'
    result_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update({
        'GRAFANA_BASE_URL': args.grafana_base_url,
        'DASHBOARD_HUB_BASE_URL': args.dashboard_hub_base_url,
        'LOCUST_DASHBOARD_COUNT': str(profile['dashboard_count']),
        'LOCUST_SUBSCRIPTIONS_PER_DASHBOARD': str(profile['subscriptions_per_dashboard']),
    })
    env.update(profile['extra_env'])

    users = args.users or int(profile['users'])
    rate = args.rate or int(profile['rate'])
    duration = args.duration or str(profile['duration'])
    locust_file = str(profile['locust_file'])
    threshold_profile = str(profile['threshold_profile'])

    selected_keys = [
        'GRAFANA_BASE_URL',
        'DASHBOARD_HUB_BASE_URL',
        'LOCUST_DASHBOARD_COUNT',
        'LOCUST_SUBSCRIPTIONS_PER_DASHBOARD',
        'LOCUST_WAIT_MIN_SECONDS',
        'LOCUST_WAIT_MAX_SECONDS',
        'CACHE_TTL_SECONDS',
        'DASHBOARD_EXISTS_CACHE_TTL_SECONDS',
        'LOCUST_BREAKDOWN_WARMUP_REQUESTS',
        'LOCUST_BREAKDOWN_INVALIDATE_INTERVAL_SECONDS',
        'LOCUST_AVALANCHE_HOTSET_SIZE',
        'LOCUST_AVALANCHE_WAVE_INTERVAL_SECONDS',
    ]
    _write_env_dump(result_dir / 'selected-profile.txt', env, selected_keys)
    (result_dir / 'run-command.txt').write_text(
        ' '.join(shlex.quote(part) for part in _locust_command(locust_file, args.host, users, rate, duration, result_dir / 'locust')) + '\n',
        encoding='utf-8',
    )

    if not args.skip_bootstrap:
        bootstrap_env_file = result_dir / 'generated-seed.env'
        env['GITHUB_ENV'] = str(bootstrap_env_file)
        bootstrap_cmd = [
            sys.executable,
            'perf/bootstrap_perf_data.py',
            '--grafana-base-url',
            args.grafana_base_url,
            '--dashboard-hub-base-url',
            args.dashboard_hub_base_url,
            '--dashboard-count',
            env['LOCUST_DASHBOARD_COUNT'],
            '--subscriptions-per-dashboard',
            env['LOCUST_SUBSCRIPTIONS_PER_DASHBOARD'],
            '--github-env',
            str(bootstrap_env_file),
        ]
        rc = _run(bootstrap_cmd, env=env, cwd=root, tee_path=result_dir / 'bootstrap.log')
        if rc != 0:
            return rc
        env.update(_load_env_file(bootstrap_env_file))

    if not args.skip_metrics:
        before_cmd = [
            sys.executable,
            'perf/collect_metrics_snapshot.py',
            '--metrics-url',
            args.metrics_url,
            '--output',
            str(result_dir / 'metrics-before.json'),
        ]
        rc = _run(before_cmd, env=env, cwd=root, tee_path=result_dir / 'metrics-before.log')
        if rc != 0:
            return rc

    locust_cmd = _locust_command(locust_file, args.host, users, rate, duration, result_dir / 'locust')
    rc = _run(locust_cmd, env=env, cwd=root, tee_path=result_dir / 'locust-console.log')
    if rc != 0:
        return rc

    if not args.skip_metrics:
        after_cmd = [
            sys.executable,
            'perf/collect_metrics_snapshot.py',
            '--metrics-url',
            args.metrics_url,
            '--output',
            str(result_dir / 'metrics-after.json'),
        ]
        rc = _run(after_cmd, env=env, cwd=root, tee_path=result_dir / 'metrics-after.log')
        if rc != 0:
            return rc

    if not args.skip_assert:
        threshold_cmd = [
            sys.executable,
            'perf/assert_locust_thresholds.py',
            '--csv',
            str(result_dir / 'locust_stats.csv'),
            '--profile',
            threshold_profile,
        ]
        rc = _run(threshold_cmd, env=env, cwd=root, tee_path=result_dir / 'threshold-check.log')
        if rc != 0:
            return rc

        if not args.skip_metrics:
            business_cmd = [
                sys.executable,
                'perf/assert_business_signals.py',
                '--before',
                str(result_dir / 'metrics-before.json'),
                '--after',
                str(result_dir / 'metrics-after.json'),
                '--profile',
                threshold_profile,
                '--summary-output',
                str(result_dir / 'business-signals-summary.json'),
            ]
            rc = _run(business_cmd, env=env, cwd=root, tee_path=result_dir / 'business-signals-check.log')
            if rc != 0:
                return rc

    print(f'Completed scenario={args.scenario}; results_dir={result_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
