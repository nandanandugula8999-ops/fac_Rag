"""Verify byte-for-byte preservation of the vendored backend and example files."""
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'backend/UPSTREAM_MANIFEST.json').read_text())
failures = []
for entry in manifest['files']:
    path = root / entry['project_path']
    if not path.is_file():
        failures.append(entry['project_path'])
        continue
    data = path.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if actual != entry['git_blob_sha']:
        failures.append(entry['project_path'])
if failures:
    raise SystemExit('Upstream files differ: ' + ', '.join(failures))
print(f"Verified {len(manifest['files'])} unchanged upstream files at {manifest['commit']}")
