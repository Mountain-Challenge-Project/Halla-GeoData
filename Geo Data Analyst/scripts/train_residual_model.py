"""Stage 4b: residual-learning models (run with a Python that has scikit-learn, e.g. anaconda).

Learns obs - physics (the residual of the stage-2 physics estimate) for air temperature and dew point from the
feature archive runtime/kma/verification/features.csv, following the reference paper's set-up:
  controls   physics only (stage 2, 'lapse'), physics + ridge regression (the LM of the paper)
  learners   random forest (RF), histogram gradient boosting (GBM); a small MLP is skipped below MLP_MIN rows
  validation leave-one-station-out (GroupKFold over stations, every station held out once) and a time split
             (the last TIME_SPLIT share of forecast issues held out), metrics bias / RMSE of the final estimate
Outputs: Geo Data Analyst/data/residual_model_report.json (metrics, importances, data status) and, when the
archive is large enough (MIN_ROWS rows and MIN_STATIONS stations), runtime/kma/models/residual_{t,td}.joblib.
Below the thresholds the script still runs the cross-validation as a smoke test and reports status
'insufficient_data'; apply_residual_model.py then refuses to correct the cells.
"""
import json, math, sys, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
import joblib

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; GDA = HERE.parent
ARCH = ROOT / 'runtime/kma/verification/features.csv'; MODELS = ROOT / 'runtime/kma/models'
MIN_ROWS, MIN_STATIONS, MIN_ISSUES, TIME_SPLIT, MLP_MIN = 2000, 20, 48, 0.2, 5000
FEATURES = ['hour_kst', 'doy_sin', 'doy_cos', 'stn_ht_m', 'cell_elev_m', 'pt_elev_m', 'dz_cell_pt', 'mean_deg', 'asp_sin', 'asp_cos', 'asp_r', 'tpi_1km_m', 'svf', 'coast_km', 'ridge_m', 'lee_m', 'lc_tree', 'lc_grass', 'lc_crop', 'lc_builtup', 'lc_water', 'canopy_mean_m', 'forest_share', 'conifer_pct', 'age_class_mean', 'density_mode',
            't1h', 'reh', 'wsd', 'vec_sin', 'vec_cos', 'rn1_mm', 'sky', 'pty', 't850', 'rh850', 'u850', 'v850', 't925', 'rh925', 'u925', 'v925', 'lapse_t', 'lapse_td', 'lcl_rel_m', 'foehn_index', 'foehn_active']
TARGETS = {'t': ('obs_ta', 'lapse_t'), 'td': ('obs_td', 'lapse_td')}


def rmse(e): return float(np.sqrt(np.mean(np.square(e)))) if len(e) else None


def models():
    return {'ridge': make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), Ridge(alpha=1.0)),
            'rf': make_pipeline(SimpleImputer(strategy='median'), RandomForestRegressor(n_estimators=200, min_samples_leaf=20, max_features='sqrt', n_jobs=-1, random_state=0)),
            'gbm': make_pipeline(SimpleImputer(strategy='median'), HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, min_samples_leaf=20, random_state=0))}


def evaluate(df, target, phys):
    y = df[target].values; base = df[phys].values; resid = y - base; X = df[FEATURES].astype(float).values; groups = df['stn'].values
    out = {'physics_only': {'bias': float(np.mean(base - y)), 'rmse': rmse(base - y)}, 'loso': {}, 'time_split': {}}
    n_groups = len(np.unique(groups)); k = min(n_groups, 10)
    if n_groups >= 3:
        for name in models():
            pred = np.full(len(y), np.nan)
            for tr, te in GroupKFold(n_splits=k).split(X, resid, groups):
                m = models()[name]; m.fit(X[tr], resid[tr]); pred[te] = m.predict(X[te])
            est = base + pred; out['loso'][name] = {'bias': float(np.mean(est - y)), 'rmse': rmse(est - y)}
    tkey = df['hour'].astype(str); issues = sorted(tkey.unique()); n_hold = max(1, int(len(issues) * TIME_SPLIT))
    if len(issues) >= 5:
        hold = set(issues[-n_hold:]); te = tkey.isin(hold).values; tr = ~te
        for name in models():
            m = models()[name]; m.fit(X[tr], resid[tr]); est = base[te] + m.predict(X[te]); out['time_split'][name] = {'bias': float(np.mean(est - y[te])), 'rmse': rmse(est - y[te]), 'n_test': int(te.sum())}
        out['time_split']['physics_only'] = {'bias': float(np.mean(base[te] - y[te])), 'rmse': rmse(base[te] - y[te]), 'n_test': int(te.sum())}
    return out


def importance(df, target, phys):
    y = df[target].values - df[phys].values; X = df[FEATURES].astype(float).values
    m = models()['rf']; m.fit(X, y); imp = m.named_steps['randomforestregressor'].feature_importances_
    return sorted([(f, round(float(v), 4)) for f, v in zip(FEATURES, imp)], key=lambda t: -t[1])[:12]


def main():
    frames = []
    if ARCH.exists(): frames.append(pd.read_csv(ARCH).assign(source='live'))
    era = ROOT / 'runtime/kma/verification/features_era5.csv'      # reanalysis-paired history (build_training_set_era5.py)
    if '--with-era5' in sys.argv and era.exists(): frames.append(pd.read_csv(era))
    if not frames: raise SystemExit('no feature archive yet: run the pipeline first')
    df = pd.concat(frames, ignore_index=True); df = df.replace('', np.nan)
    for c in FEATURES + ['obs_ta', 'obs_td']: df[c] = pd.to_numeric(df[c], errors='coerce')
    report = {'trained_at': dt.datetime.now().isoformat(timespec='minutes'), 'rows': int(len(df)), 'stations': int(df['stn'].nunique()), 'issues': int(df['issue_kst'].nunique()),
              'first_issue': str(df['issue_kst'].min()), 'last_issue': str(df['issue_kst'].max()), 'rows_by_source': df['source'].value_counts().to_dict() if 'source' in df else {'live': int(len(df))}, 'features': FEATURES, 'thresholds': {'min_rows': MIN_ROWS, 'min_stations': MIN_STATIONS, 'min_issues': MIN_ISSUES},
              'status': 'ok', 'targets': {}}
    n_issues = df.loc[df['issue_kst'] != 'reanalysis', 'issue_kst'].nunique() + (df['hour'].nunique() if (df['issue_kst'] == 'reanalysis').any() else 0)
    enough = len(df) >= MIN_ROWS and df['stn'].nunique() >= MIN_STATIONS and n_issues >= MIN_ISSUES
    if not enough: report['status'] = 'insufficient_data'; report['message'] = f'{len(df)} rows / {df["stn"].nunique()} stations / {n_issues} issues; need {MIN_ROWS} / {MIN_STATIONS} / {MIN_ISSUES}. Cross-validation below is a smoke test only.'
    MODELS.mkdir(parents=True, exist_ok=True)
    for key, (target, phys) in TARGETS.items():
        d = df.dropna(subset=[target, phys]).copy()
        if len(d) < 30 or d['stn'].nunique() < 3: report['targets'][key] = {'skipped': f'{len(d)} rows'}; continue
        r = evaluate(d, target, phys); r['n'] = int(len(d)); r['importance_rf'] = importance(d, target, phys); report['targets'][key] = r
        if enough:
            best = min(r['loso'], key=lambda n: r['loso'][n]['rmse']); m = models()[best]; m.fit(d[FEATURES].astype(float).values, (d[target] - d[phys]).values)
            src = d['source'].value_counts().to_dict() if 'source' in d else {'live': int(len(d))}
            joblib.dump({'model': m, 'features': FEATURES, 'phys': phys, 'target': target, 'name': best, 'trained_at': report['trained_at'], 'rows': int(len(d)), 'basis': {'rows_by_source': {k: int(v) for k, v in src.items()}, 'live_rows': int(src.get('live', 0)), 'stations': int(d['stn'].nunique()), 'loso_rmse': r['loso'][best]['rmse'], 'physics_rmse': r['physics_only']['rmse']}}, MODELS / f'residual_{key}.joblib')
            r['saved_model'] = best
    (GDA / 'data/residual_model_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    brief = {k: {'n': v.get('n'), 'physics_rmse': v.get('physics_only', {}).get('rmse'), 'loso_rmse': {n: round(s['rmse'], 2) for n, s in v.get('loso', {}).items()}} for k, v in report['targets'].items() if 'n' in v}
    print('RESIDUAL_MODEL', json.dumps({'status': report['status'], 'rows': report['rows'], 'stations': report['stations'], 'issues': report['issues'], 'targets': brief}, ensure_ascii=False))


if __name__ == '__main__':
    main()
