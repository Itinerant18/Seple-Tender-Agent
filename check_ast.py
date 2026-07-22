import json
from pathlib import Path
p = Path('graphify-out/.graphify_ast.json')
if p.exists():
    data = json.loads(p.read_text(encoding='utf-8'))
    print(f'Nodes: {len(data.get("nodes", []))}')
    print(f'Edges: {len(data.get("edges", []))}')
else:
    print('File not found')