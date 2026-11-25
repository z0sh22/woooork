"""Extract user-supplied PDFs for a traceable literature review (optional pypdf)."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path('.research_tools').resolve()))
from pypdf import PdfReader

destination = Path('.research_cache/papers')
destination.mkdir(parents=True, exist_ok=True)
manifest = []
for path in sorted(Path('изученные статьи').glob('*.pdf')):
    reader = PdfReader(path)
    pages = [f'\n--- PAGE {i} ---\n' + (page.extract_text() or '') for i, page in enumerate(reader.pages, 1)]
    target = destination / (path.stem + '.txt')
    target.write_text('\n'.join(pages), encoding='utf-8')
    manifest.append({'file': path.name, 'pages': len(pages), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'text_file': str(target)})
(destination / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(manifest, indent=2, ensure_ascii=True))
