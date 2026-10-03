"""Exercise the existing FastAPI endpoint; save actual responses, never fixtures."""
import argparse
import datetime as dt
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

QUERIES = ['machine learning', 'computer vision', 'cybersecurity', 'quantum computing', 'natural language processing', 'robotics', 'graph neural networks', 'zzzxqvpl nonexistent purple teapot faculty topic 94721']

def get_json(url, payload=None, timeout=180):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    # Requests go only to the configured backend. Never to OpenAlex here.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://localhost:8000')
    parser.add_argument('--output', type=Path, default=Path('datasets/openalex'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    health = get_json(args.base_url.rstrip('/') + '/health')
    if health.get('corpus_source') == 'fixture' or health.get('mode') == 'fixture':
        raise SystemExit('Refusing fixture mode: live test requires real data.')
    rows, works = [], {}
    for index, query in enumerate(QUERIES):
        started = time.monotonic()
        filename = f'{index + 1:02d}-' + ('unrelated-query' if index == 7 else query.replace(' ', '-')) + '.json'
        try:
            body = get_json(args.base_url.rstrip('/') + '/api/faculty/search', {'query': query, 'top_k': 10})
            assert body.get('corpus_source') in ('live-openalex', 'datalake'), 'Unexpected corpus source'
            assert body.get('status') in ('ok', 'insufficient_evidence'), 'Unexpected status'
            matches = body.get('matches', [])
            if body['status'] == 'insufficient_evidence':
                assert matches == [], 'Insufficient evidence must not return faculty'
            assert len(matches) <= 10
            for match in matches:
                assert isinstance(match.get('faculty_name'), str) and match['faculty_name']
                for work in match.get('supporting_publications', []):
                    key = work.get('work_id') or work.get('doi') or work.get('title')
                    if key:
                        works[key] = work
            (args.output / filename).write_text(json.dumps(body, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            row = {'query': query, 'status': body['status'], 'faculty_count': len(matches), 'works_retrieved': body.get('discovery', {}).get('works_retrieved'), 'verified': body.get('verified'), 'file': filename, 'elapsed_seconds': round(time.monotonic() - started, 2)}
        except Exception as error:
            # Do not export exception details that could contain credentials or private URLs.
            row = {'query': query, 'status': 'request_failed', 'error_type': type(error).__name__, 'elapsed_seconds': round(time.monotonic() - started, 2)}
        rows.append(row)
        print(json.dumps(row), flush=True)
    report = {'captured_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'upstream_commit': '6ba86142c78f85ff48453bb3645040f6392b376e', 'health': health, 'note': 'Actual API response snapshots, not frontend fallback data. An insufficient_evidence response alone cannot distinguish an upstream service error from genuine lack of evidence.', 'queries': rows, 'unique_supporting_publications': len(works)}
    (args.output / 'test-report.json').write_text(json.dumps(report, indent=2) + '\n')
    (args.output / 'publications.json').write_text(json.dumps({'provenance': report['note'], 'captured_at_utc': report['captured_at_utc'], 'records': list(works.values())}, indent=2, ensure_ascii=False) + '\n')

if __name__ == '__main__':
    main()
