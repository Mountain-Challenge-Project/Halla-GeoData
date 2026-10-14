"""Region configuration shared by the slope pipeline (prepare -> fetch -> build -> render -> verify).

Select a region with the SLOPE_REGION environment variable (default: hallasan).
Each work/regions/<name>.json keeps the paths, grid layer and map texts for one study area,
so the same scripts reproduce the original Hallasan bundle and the Jeju-wide bundle.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name=None):
    name = name or os.environ.get('SLOPE_REGION', 'hallasan')
    path = ROOT / 'work' / 'regions' / (name + '.json')
    if not path.exists():
        raise SystemExit('unknown SLOPE_REGION: ' + name)
    cfg = json.loads(path.read_text(encoding='utf-8'))
    cfg['name'] = name
    return cfg
