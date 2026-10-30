"""Verify prepared source/artifact consistency; does not attest hosted execution."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
m=json.loads((ROOT/'release.json').read_text())
identity='sha256:'+hashlib.sha256(json.dumps(m['files'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
assert identity==m['release_id']
for name,expected in m['files'].items():
    p=ROOT/name
    assert not p.is_symlink() and p.resolve().is_relative_to(ROOT)
    assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,name
html=(ROOT/'public/index.html').read_text()
for asset in re.findall(r'(?:src|href)="(/[^"#]*)"',html):
    if asset=='/':continue
    assert (ROOT/'public'/asset.lstrip('/')).is_file(),asset
assert not re.search(r'<script(?![^>]*\bsrc=)',html)
assert 'innerHTML' not in (ROOT/'public/workspace.js').read_text()
config=json.loads((ROOT/'vercel.json').read_text())
assert config['outputDirectory']=='public' and config['framework'] is None
assert config['functions']['api/review.py']['maxDuration']==10
print(json.dumps({'release_id':identity,'files':len(m['files']),'file_bindings':'PASS','asset_links':'PASS','scope':'Local prepared source only; Vercel build, browser and hosted acceptance not established.'}))
