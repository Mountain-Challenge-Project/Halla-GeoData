"""Shared reader for the repository-root .env (UTF-8, KEY=VALUE lines, # comments). Never prints values.

    from env_config import env_value
    token = env_value('EARTHDATA_TOKEN')          # '' when absent

Keys used by the project (see .env.example for where each one comes from):
  KMA_API_KEY            기상청 API허브                      CDS_API_KEY             Copernicus Climate Data Store (ERA5 originals)
  EARTHDATA_USER/_PASS   NASA Earthdata (AppEEARS, LAADS)  CDSE_CLIENT_ID/_SECRET  Copernicus Data Space (Sentinel-3)
  DATA_GO_KR_KEY         공공데이터포털 serviceKey           NMSC_API_KEY            국가기상위성센터 (천리안 과거 자료)
  ME_LANDCOVER_SHP       환경부 토지피복도 SHP 로컬 경로        FGIS_FOREST_SHP         산림청 임상도 SHP 로컬 경로
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
_cache = None


def env_values():
    global _cache
    if _cache is None:
        _cache = {}
        p = ROOT / '.env'
        if p.exists():
            for line in p.read_text('utf-8-sig').splitlines():
                s = line.strip()
                if not s or s.startswith('#') or '=' not in s: continue
                k, v = s.split('=', 1); _cache[k.strip()] = v.strip().strip('"').strip("'")
    return _cache


def env_value(name, default=''):
    return env_values().get(name, default)
