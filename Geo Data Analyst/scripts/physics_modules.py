"""Stage 2: physics modules of the local-weather model (Python reference implementation).

The dashboard (work/dashboard_src/body.html) carries the same formulas in JavaScript for the live map; this module
is the reference used by compute_stage2.py for verification against AWS observations and for figures.

Modules
  magnus_td(t, rh)                 dew point (degC) from air temperature and relative humidity (Magnus, a=17.62 b=243.12)
  rh_from(t, td)                   relative humidity (%) back from T and Td
  lcl_height(t, td)                lifting condensation level above the parcel start (m), 125 m per degC of (T - Td)
  moist_lapse(t_c, p_hpa)          saturated-adiabatic lapse rate (degC/m) at T, p
  cell_state(...)                  cell temperature / dew point by lapse rates (6.5 and 2 degC/km) from the 5 km point
  foehn(...)                       parcel lifted from the upstream point over the ridge and brought down dry to the cell
"""
import math

G, CP, L, RD, RV, EPS = 9.81, 1004.0, 2.5e6, 287.0, 461.5, 0.622
LAPSE_T, LAPSE_TD, DRY = 0.0065, 0.002, 0.0098        # degC/m
TD_DESCENT = 0.0018                                    # dew point rises ~1.8 degC/km on dry descent (mixing ratio conserved)


def es(t):           # saturation vapour pressure hPa (Magnus)
    return 6.112 * math.exp(17.62 * t / (243.12 + t))


def magnus_td(t, rh):
    a, b = 17.62, 243.12
    g = math.log(max(rh, 1.0) / 100.0) + a * t / (b + t)
    return b * g / (a - g)


def rh_from(t, td):
    return max(0.0, min(100.0, 100.0 * es(td) / es(t)))


def lcl_height(t, td):
    return max(0.0, 125.0 * (t - td))


def pressure_at(z, p0=1013.25, t0=288.15):   # hypsometric, standard atmosphere, for the moist lapse only
    return p0 * math.exp(-G * z / (RD * t0))


def moist_lapse(t_c, p_hpa):
    tk = t_c + 273.15; r = EPS * es(t_c) / max(p_hpa - es(t_c), 1.0)
    return G * (1 + L * r / (RD * tk)) / (CP + L * L * r * EPS / (RD * tk * tk))


def cell_state(t_pt, rh_pt, z_pt, z_cell):
    """temperature and dew point of a cell from its 5 km point by fixed lapse rates (the stage-1 approximation)."""
    t = t_pt - LAPSE_T * (z_cell - z_pt); td = magnus_td(t_pt, rh_pt) - LAPSE_TD * (z_cell - z_pt)
    return {'t': t, 'td': min(td, t), 'rh': rh_from(t, min(td, t)), 'lcl_alt': z_pt + lcl_height(t_pt, magnus_td(t_pt, rh_pt))}


def foehn(t_up, rh_up, z_up, z_ridge, z_cell, wind_ms, lee_depth_m):
    """Parcel from the windward point (t_up, rh_up at z_up): dry ascent to the LCL, saturated ascent to the ridge,
    dry descent to the cell (condensate removed). Returns the foehn temperature/dew point at the cell and the index
    = foehn temperature minus the plain lapse estimate. 'active' needs a lee cell (ridge - cell >= 300 m), wind >= 5 m/s
    and an index >= 1 degC; the index alone is reported for every cell."""
    td_up = magnus_td(t_up, rh_up); lcl = z_up + lcl_height(t_up, td_up)
    if z_ridge <= z_up + 50:   # no barrier to cross
        return None
    if z_ridge > lcl:
        t_lcl = t_up - DRY * (lcl - z_up); t = t_lcl; z = lcl
        while z < z_ridge:   # saturated ascent in 50 m steps with the local moist lapse rate
            dz = min(50.0, z_ridge - z); t -= moist_lapse(t, pressure_at(z)) * dz; z += dz
        t_ridge = t; td_ridge = t_ridge; condensed = True
    else:
        t_ridge = t_up - DRY * (z_ridge - z_up); td_ridge = td_up - LAPSE_TD * (z_ridge - z_up); condensed = False
    t_cell = t_ridge + DRY * (z_ridge - z_cell); td_cell = min(td_ridge + TD_DESCENT * (z_ridge - z_cell), t_cell)
    t_lapse = t_up - LAPSE_T * (z_cell - z_up)
    index = t_cell - t_lapse
    active = bool(condensed and lee_depth_m >= 300 and (wind_ms or 0) >= 5 and index >= 1)
    return {'t': t_cell, 'td': td_cell, 'rh': rh_from(t_cell, td_cell), 'lcl_alt': lcl, 'ridge': z_ridge, 'condensed': condensed, 'index': index, 'active': active}


def station_pressure(ps_hpa, t_c, z_m, td_c=None):
    """Station (local) pressure from sea-level pressure by the hypsometric equation. The layer temperature is the
    mean of the surface air temperature and the temperature extrapolated to sea level (6.5 degC/km); virtual
    temperature uses the dew point when given. Validated against ASOS PA (verify_pressure_asos.py)."""
    t_layer = t_c + 0.0065 * z_m / 2.0
    tv = t_layer + 273.15
    if td_c is not None:
        e = es(min(td_c, t_c)); tv = tv / (1 - (e / ps_hpa) * (1 - EPS))
    return ps_hpa * math.exp(-G * z_m / (RD * tv))


# Stage-5 calibration (foehn_case_validation.py on 9,359 cross-island ASOS hours, 2023-01..2026-10): applying the full
# parcel temperature whenever the parcel condenses over the ridge over-warms the lee by +5 degC on average, because the
# coastal lee warming that the screening finds (303 h) is rare, daytime and mostly clear-sky (51 % vs 19 %). The best
# simple rule was a 30 % blend towards the parcel value during 11-16 KST (all-hour RMSE 2.08 -> 2.01 degC); the index
# itself stays a diagnostic for the highlight layer.
FOEHN_BLEND, FOEHN_HOURS = 0.3, (11, 16)


def foehn_applied(lapse_t, lapse_td, fo, hour_kst):
    """temperature / dew point actually used for a cell: lapse values moved FOEHN_BLEND of the way to the parcel values
    when the foehn condition is active during FOEHN_HOURS, else the lapse values."""
    if fo and fo.get('active') and FOEHN_HOURS[0] <= hour_kst <= FOEHN_HOURS[1]:
        return lapse_t + FOEHN_BLEND * (fo['t'] - lapse_t), min(lapse_td + FOEHN_BLEND * (fo['td'] - lapse_td), lapse_t + FOEHN_BLEND * (fo['t'] - lapse_t))
    return lapse_t, lapse_td


DIRS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']


def dir_index(deg):
    return int(round((deg % 360) / 22.5)) % 16


def wind_from_uv(u, v):
    spd = math.hypot(u, v); d = (math.degrees(math.atan2(-u, -v)) + 360) % 360   # direction the wind comes from
    return d, spd
