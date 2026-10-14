"""Prepare a portable public delivery; never includes local credentials or runtime."""
from pathlib import Path
import csv
import hashlib
import json
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = {
    'hallasan_slope': 'hallasan_slope_QGIS_SHP.zip',
    'hallasan_course_slope_v2': 'hallasan_course_slope_QGIS_v2.zip',
    'hallasan_radar_layers_v1': 'hallasan_radar_3ways.zip',
}
TEXT_EXTENSIONS = {'.py', '.json', '.html', '.js', '.css', '.qgs', '.qml', '.md', '.csv', '.txt', '.cmd', '.yml', '.xml', '.example'}
PATTERNS = [
    re.compile(r'gh[pousr]_[A-Za-z0-9_]{30,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{40,}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]


def public_files():
    result = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                            cwd=ROOT, check=True, capture_output=True)
    return sorted({p.decode('utf-8') for p in result.stdout.split(b'\0') if p})


def portable_projects():
    for folder in BUNDLES:
        for path in (ROOT/'outputs'/folder).rglob('*.qgs'):
            text = path.read_text('utf-8')
            text = re.sub(r'\bsaveUser(?:Full)?="[^"]*"', lambda m: m.group().split('=')[0]+'=""', text)
            text = re.sub(r'<author>[^<]*</author>', '<author>Mountain Challenge Project</author>', text)
            # Layouts sometimes retain absolute fallback paths even when map layers are relative.
            def local_source(match):
                suffix = match.group(1).replace('\\', '/')
                return 'source="./' + suffix + '"'
            text = re.sub(r'source="[A-Za-z]:[^"\n]*[/\\]outputs[/\\]'+re.escape(folder)+r'[/\\]([^"]+)"', local_source, text)
            path.write_text(text, encoding='utf-8')
    region = ROOT/'work/slope_region.json'
    record = json.loads(region.read_text('utf-8'))
    record['source_file'] = 'inputs/reference/hallasan_course_cells.gpkg'
    region.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def scan_text(name, data):
    text = data.decode('utf-8-sig', errors='replace')
    if any(p.search(text) for p in PATTERNS):
        raise ValueError('Possible credential in ' + name + '; inspect locally without printing its value.')
    for value in re.findall(r'(?:authKey|serviceKey)=([^&\s\x22\x27<>]+)', text, re.I):
        if not any(x in value for x in ['{', '}', '인증', 'YOUR_', '%7B', '+', '"']):
            raise ValueError('Review possible URL credential in ' + name)


def main():
    portable_projects()
    names = public_files()
    for name in names:
        path = ROOT/name
        if name.startswith(('outputs/', 'inputs/', 'work/public_sources/')) or not path.is_file():
            continue
        if path.suffix in {'.py', '.md', '.json', '.html', '.js', '.css', '.cmd', '.yml', '.example'}:
            data = path.read_bytes().replace(b'\r\n', b'\n')
            if path.suffix == '.cmd':
                data = data.replace(b'\n', b'\r\n')
            path.write_bytes(data)
    for folder, archive in BUNDLES.items():
        prefix = 'outputs/' + folder + '/'
        members = [name for name in names if name.startswith(prefix)]
        with zipfile.ZipFile(ROOT/'outputs'/archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name in members:
                z.write(ROOT/name, Path(folder)/Path(name).relative_to(prefix))
        with zipfile.ZipFile(ROOT/'outputs'/archive) as z:
            assert z.testzip() is None
            for entry in z.infolist():
                if Path(entry.filename).suffix in TEXT_EXTENSIONS:
                    scan_text(archive+'!'+entry.filename, z.read(entry))
    # Reject files that should never be in a public commit, including accidentally tracked ones.
    names = public_files()
    rows = []
    for name in names:
        path = ROOT/name
        if name == 'FILE_MANIFEST.csv' or not path.is_file():
            continue
        if any(part in ['runtime', '__pycache__', '.tmp'] for part in Path(name).parts):
            raise ValueError('Private/runtime file listed by Git: '+name)
        if path.name.startswith('.env') and path.name != '.env.example':
            raise ValueError('Credential file listed by Git: '+name)
        data = path.read_bytes()
        if len(data) >= 100 * 1024 * 1024:
            raise ValueError('File exceeds regular GitHub per-file limit: '+name)
        if path.suffix in TEXT_EXTENSIONS or path.name in ['.gitignore', '.gitattributes']:
            scan_text(name, data)
        kind = 'source_code' if path.suffix in {'.py', '.js', '.cmd', '.yml'} else 'data_or_document'
        if path.suffix == '.zip':
            kind = 'delivery_archive'
        rows.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'kind': kind})
    with (ROOT/'FILE_MANIFEST.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['path', 'bytes', 'sha256', 'kind'])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'files_except_manifest': len(rows), 'total_bytes': sum(r['bytes'] for r in rows),
                      'largest_file_bytes': max(r['bytes'] for r in rows),
                      'zip_crc': 'passed', 'pattern_scan': 'passed', 'api_called': False}))


if __name__ == '__main__':
    main()
