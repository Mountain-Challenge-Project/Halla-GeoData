"""Read-only QGIS, relative-path and documentation checks; no network."""
from pathlib import Path
import json
import os
import re
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from qgis.core import QgsApplication, QgsProject

ROOT = Path(__file__).resolve().parents[1]
app = QgsApplication([], False)
app.initQgis()
result = {}
for relative, expected in [
    ('outputs/hallasan_slope/hallasan_slope.qgs', None),
    ('outputs/hallasan_course_slope_v2/hallasan_course_slope.qgs', 25),
    ('outputs/hallasan_radar_layers_v1/qgis/hallasan_live.qgs', 6),
]:
    path = ROOT/relative
    project = QgsProject()
    assert project.read(str(path)), relative
    layers = project.mapLayers()
    assert layers and all(layer.isValid() for layer in layers.values()), relative
    if expected:
        assert len(layers) == expected, relative
    assert not re.search(r'source="[A-Za-z]:', path.read_text('utf-8')), relative
    result[relative] = {'valid_layers': len(layers), 'layouts': len(project.layoutManager().layouts())}
    project.clear()

for relative in ['README.md', 'DATA_SOURCES.md']:
    for target in re.findall(r'\]\(([^)]+)\)', (ROOT/relative).read_text('utf-8')):
        if not target.startswith(('http:', 'https:', '#')):
            assert (ROOT/target).exists(), (relative, target)
assert json.loads((ROOT/'outputs/hallasan_radar_layers_v1/dist/state/latest.json').read_text('utf-8'))['status'] == 'waiting'
assert json.loads((ROOT/'outputs/hallasan_radar_layers_v1/dist/state/history.json').read_text('utf-8'))['frames'] == []
print(json.dumps({'qgis': result, 'local_document_links': 'passed', 'initial_radar_state': 'waiting', 'api_called': False}))
