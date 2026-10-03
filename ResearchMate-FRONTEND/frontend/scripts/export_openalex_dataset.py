"""Export 150 real publication metadata records from the backend discovery cache."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'backend/data/cache/discovery'
OUT = ROOT / 'datasets/openalex'
records = {}
for path in sorted(CACHE.glob('*/*.json')):
    cached = json.loads(path.read_text(encoding='utf-8'))
    for work in cached.get('payload', {}).get('works', []):
        work_id = work.get('id')
        if not work_id or work_id in records:
            continue
        records[work_id] = {
            'openalex_id': work_id,
            'title': work.get('title'),
            'publication_year': work.get('publication_year'),
            'publication_date': work.get('publication_date'),
            'type': work.get('type'),
            'doi': work.get('doi'),
            'cited_by_count': work.get('cited_by_count'),
            'is_retracted': work.get('is_retracted'),
            'authors': [{
                'openalex_id': a.get('author', {}).get('id'),
                'name': a.get('author', {}).get('display_name'),
                'orcid': a.get('author', {}).get('orcid'),
                'institutions': [{
                    'openalex_id': i.get('id'), 'name': i.get('display_name'),
                    'country_code': i.get('country_code'),
                } for i in a.get('institutions', [])],
            } for a in work.get('authorships', [])],
            'topics': [{'id': t.get('id'), 'name': t.get('display_name'), 'score': t.get('score')}
                       for t in work.get('topics', [])],
            'source_links': sorted({loc.get('landing_page_url') for loc in work.get('locations', [])
                                    if loc.get('landing_page_url')}),
            'source': 'OpenAlex via existing FastAPI discovery backend',
            'captured_at_utc': cached.get('fetched_at'),
            'synthetic': False,
        }
if len(records) < 150:
    raise SystemExit(f'Need at least 150 cached real works; found {len(records)}. Run live API tests first.')
selected = [records[k] for k in sorted(records)[:150]]
OUT.mkdir(parents=True, exist_ok=True)
metadata = {
    'description': '150 real publication metadata records; not generated faculty or frontend fallback data.',
    'source': 'OpenAlex via the unchanged faculty-radar backend',
    'upstream_commit': '6ba86142c78f85ff48453bb3645040f6392b376e',
    'record_count': len(selected), 'unique_cached_works_available': len(records),
    'selection': 'Unique OpenAlex work IDs sorted lexicographically; first 150. Not a relevance benchmark.',
    'records': selected,
}
(OUT / 'openalex-publications-150.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
(OUT / 'openalex-publications-150.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in selected), encoding='utf-8')
print(f'Exported {len(selected)} real records from {len(records)} unique cached works.')
