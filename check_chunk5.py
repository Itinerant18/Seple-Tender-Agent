import json
from pathlib import Path
p = Path('graphify-out/.graphify_chunk_005.json')
if p.exists():
    d = json.loads(p.read_text(encoding='utf-8'))
    print(f'Nodes: {len(d.get("nodes", []))}')
    print(f'Edges: {len(d.get("edges", []))}')
    print(f'Hyperedges: {len(d.get("hyperedges", []))}')
else:
    print('File not found')