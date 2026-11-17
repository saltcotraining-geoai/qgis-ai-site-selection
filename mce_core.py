"""Multi-Criteria Evaluation maths - pure Python, no QGIS needed.

Used by phase2b_mce.py. Kept separate so it can be read, tested and taught
on its own (every function is short and works on plain dicts and lists).

    active_factors()     the three core factors + any optional factor switched on in config
    ahp_weights()        AHP: weights + consistency ratio from pairwise judgements
    resolve_weights()    choose AHP or direct weights from config
    weighted_score()     weighted linear combination of 0-1 factor scores
    sensitivity()        how stable is the selection when the weights change?
    boolean_fail_reasons()  which Boolean rule(s) would reject this building?
    compare_with_boolean()  label every site: both / mce_only / boolean_only
"""

from __future__ import annotations

FACTORS = ("school", "highway", "river")          # always used (the class baseline)
OPTIONAL_FACTORS = ("restaurant",)                # used only when mce.factors.<name>.enabled is true

# Saaty's Random Index (RI) for matrices of size n
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------
def ahp_weights(names: list[str], pairwise: dict) -> dict:
    """Analytic Hierarchy Process.

    pairwise = {"school/highway": 3, ...} means "school is 3x as important as
    highway" (Saaty 1-9 scale; use 1/3 for the reverse). Missing pairs = 1 (equal).

    Steps (same as the hand calculation taught in class):
      1. Build the reciprocal matrix  M[i][j] = judgement, M[j][i] = 1 / judgement
      2. Weights = principal eigenvector (power iteration), normalised to sum 1
      3. lambda_max = average of (M·w)_i / w_i
      4. CI = (lambda_max - n) / (n - 1);  CR = CI / RI   ->  CR <= 0.10 is acceptable
    """
    n = len(names)
    matrix = [[1.0] * n for _ in range(n)]
    warnings = []
    seen = set()
    for key, value in pairwise.items():
        if key.startswith("_"):
            continue
        parts = [p.strip() for p in key.split("/")]
        if len(parts) != 2 or parts[0] not in names or parts[1] not in names or parts[0] == parts[1]:
            raise ValueError(f"AHP pair '{key}' must look like 'a/b' with a, b in {names}.")
        value = float(value)
        if value <= 0:
            raise ValueError(f"AHP judgement for '{key}' must be > 0 (use 1/3, not -3).")
        i, j = names.index(parts[0]), names.index(parts[1])
        matrix[i][j], matrix[j][i] = value, 1.0 / value
        seen.add(frozenset((i, j)))
    for i in range(n):
        for j in range(i + 1, n):
            if frozenset((i, j)) not in seen:
                warnings.append(f"No judgement for {names[i]}/{names[j]} - treated as equal (1).")

    # Power iteration for the principal eigenvector
    w = [1.0 / n] * n
    for _ in range(200):
        v = [sum(matrix[i][j] * w[j] for j in range(n)) for i in range(n)]
        total = sum(v)
        v = [x / total for x in v]
        converged = max(abs(a - b) for a, b in zip(v, w)) < 1e-12
        w = v
        if converged:
            break

    mw = [sum(matrix[i][j] * w[j] for j in range(n)) for i in range(n)]
    lambda_max = sum(mw[i] / w[i] for i in range(n)) / n
    ci = (lambda_max - n) / (n - 1) if n > 2 else 0.0
    ri = RANDOM_INDEX.get(n, 1.49)
    cr = ci / ri if ri else 0.0
    if cr > 0.10:
        warnings.append(f"Consistency ratio {cr:.3f} > 0.10 - the pairwise judgements contradict each other; revise them.")
    return {
        "weights": {name: w[i] for i, name in enumerate(names)},
        "matrix": matrix,
        "lambda_max": lambda_max,
        "ci": ci,
        "ri": ri,
        "cr": cr,
        "warnings": warnings,
    }


def active_factors(mce_cfg: dict) -> list[str]:
    """Core factors, then each optional factor whose config block has "enabled": true."""
    factors_cfg = mce_cfg.get("factors", {})
    extra = [f for f in OPTIONAL_FACTORS if (factors_cfg.get(f) or {}).get("enabled", False)]
    return list(FACTORS) + extra


def _pair_is_active(key: str, names: list[str]) -> bool:
    """True if an 'a/b' AHP key only mentions active factors (or is malformed - let ahp_weights report it)."""
    parts = [p.strip() for p in key.split("/")]
    if len(parts) != 2:
        return True
    known = set(FACTORS) | set(OPTIONAL_FACTORS)
    # A pair naming a switched-off optional factor is simply skipped, so the
    # restaurant judgements can stay in config.json while the factor is off.
    return not any(p in known and p not in names for p in parts)


def resolve_weights(mce_cfg: dict) -> tuple[dict, dict]:
    """Return (weights summing to 1, info for the summary) from config['mce']['weights']."""
    wcfg = mce_cfg["weights"]
    names = active_factors(mce_cfg)
    method = str(wcfg.get("method", "ahp")).lower()
    if method == "ahp":
        pairwise = {k: v for k, v in wcfg.get("ahp_pairwise", {}).items()
                    if not k.startswith("_") and _pair_is_active(k, names)}
        result = ahp_weights(names, pairwise)
        info = {"method": "ahp", **{k: result[k] for k in ("lambda_max", "ci", "ri", "cr", "warnings", "matrix")},
                "factors": names, "pairwise": pairwise}
        return result["weights"], info
    if method == "direct":
        missing = [f for f in names if f not in wcfg.get("direct", {})]
        if missing:
            raise ValueError(f"mce.weights.direct has no weight for {missing}.")
        raw = {f: float(wcfg["direct"][f]) for f in names}
        total = sum(raw.values())
        if total <= 0:
            raise ValueError("Direct weights must add up to more than 0.")
        return {f: v / total for f, v in raw.items()}, {"method": "direct", "raw": raw}
    raise ValueError("mce.weights.method must be 'ahp' or 'direct'.")


def weighted_score(factor_scores: dict, weights: dict) -> float:
    """Weighted linear combination: sum of weight_i x factor_i (all 0-1)."""
    return sum(weights[f] * float(factor_scores[f]) for f in weights)


# ---------------------------------------------------------------------------
# Sensitivity analysis
# ---------------------------------------------------------------------------
def top_ids(rows: list[dict], weights: dict, n: int) -> list:
    """IDs of the n best rows for these weights (ties: larger area first)."""
    # Rounded to 3 decimals and tie-broken exactly like the ranking in Phase 2b,
    # so the base scenario reproduces the real selection.
    ranked = sorted(rows, key=lambda r: (-round(weighted_score(r["factors"], weights), 3), -r.get("area", 0), str(r["id"])))
    return [r["id"] for r in ranked[:n]]


def sensitivity(rows: list[dict], weights: dict, n: int, change: float) -> dict:
    """Raise and lower each weight by `change` (e.g. 0.2 = 20 %), re-normalise, re-select.

    rows: [{"id":..., "factors": {"school":0.7, ...}, "area": 950.0}, ...]
    Returns stability per id (0-1) for the base selection and one line per scenario.
    """
    base = set(top_ids(rows, weights, n))
    scenarios = []
    hits = {i: 0 for i in base}
    for factor in weights:
        for sign, mult in (("+", 1 + change), ("-", 1 - change)):
            w = dict(weights)
            w[factor] *= mult
            total = sum(w.values())
            w = {k: v / total for k, v in w.items()}
            chosen = set(top_ids(rows, w, n))
            for i in base & chosen:
                hits[i] += 1
            scenarios.append({
                "scenario": f"{factor} {sign}{change:.0%}",
                "weights": {k: round(v, 3) for k, v in w.items()},
                "kept_of_base": len(base & chosen),
                "new_sites": len(chosen - base),
            })
    count = len(scenarios) or 1
    return {"stability": {i: hits[i] / count for i in base}, "scenarios": scenarios}


# ---------------------------------------------------------------------------
# Boolean vs MCE comparison
# ---------------------------------------------------------------------------
def boolean_fail_reasons(props: dict, crit: dict) -> list[str]:
    """Which Boolean (Phase 2) rules would reject this building, judged from its distances.

    Area and urban are MCE constraints too, so a building scored by MCE already
    passes them (unless the two configs use different values - noted separately).
    """
    reasons = []
    area = props.get("area_sqm")
    if area is not None and not (float(crit["min_area_sqm"]) <= float(area) <= float(crit["max_area_sqm"])):
        reasons.append(f"area {float(area):,.0f} m² outside {crit['min_area_sqm']:g}–{crit['max_area_sqm']:g}")
    d = props.get("dist_school_m")
    if d is not None and float(d) > float(crit["school_distance_m"]):
        reasons.append(f"school {float(d):,.0f} m > {crit['school_distance_m']:g} m")
    d = props.get("dist_highway_m")
    if d is not None and float(d) <= float(crit["highway_exclusion_m"]):
        reasons.append(f"highway {float(d):,.0f} m ≤ {crit['highway_exclusion_m']:g} m")
    d = props.get("dist_river_m")
    if d is not None and float(d) <= float(crit["river_exclusion_m"]):
        reasons.append(f"river {float(d):,.0f} m ≤ {crit['river_exclusion_m']:g} m")
    return reasons


def compare_with_boolean(mce_selected: dict, mce_scored: dict, boolean_fc: dict, crit: dict) -> dict:
    """Label sites and build one comparison FeatureCollection.

    agreement:
      both          selected by the Boolean screen AND by MCE  -> strongest candidates
      mce_only      MCE selected it; reason = the Boolean rule(s) it narrowly failed
      boolean_only  Boolean kept it; reason = its MCE rank/score (or failed MCE constraint)
    Matching uses source_id (osm_id / full_id / fid), written by both phases.
    """
    boolean_by_id = {str((f.get("properties") or {}).get("source_id")): f for f in boolean_fc.get("features", [])}
    scored_by_id = {str((f.get("properties") or {}).get("source_id")): f for f in mce_scored.get("features", [])}
    mce_ids = set()
    union = []

    for feature in mce_selected.get("features", []):
        p = feature["properties"]
        sid = str(p.get("source_id"))
        mce_ids.add(sid)
        in_boolean = sid in boolean_by_id
        p["boolean_selected"] = int(in_boolean)
        if in_boolean:
            p["agreement"], p["reason"] = "both", "passes every Boolean rule and ranks high in MCE"
        else:
            reasons = boolean_fail_reasons(p, crit)
            p["agreement"] = "mce_only"
            p["reason"] = "Boolean rejects: " + "; ".join(reasons) if reasons else \
                "Boolean rejects it (buffer/predicate edge case)"
        union.append(feature)

    for sid, feature in boolean_by_id.items():
        if sid in mce_ids:
            continue
        bp = feature.get("properties") or {}
        scored = scored_by_id.get(sid)
        if scored:
            sp = scored["properties"]
            reason = f"MCE rank {sp.get('mce_rank')} (score {float(sp.get('mce_score') or 0):.2f}) - below the selection cut"
            mce_rank, mce_score = sp.get("mce_rank"), sp.get("mce_score")
        else:
            reason = "fails an MCE constraint (see mce.constraints)"
            mce_rank = mce_score = None
        props = {
            "source_id": sid, "name": bp.get("name"), "area_sqm": bp.get("area_sqm"),
            "pop_estimate": bp.get("pop_estimate"), "lat": bp.get("lat"), "lon": bp.get("lon"),
            "mce_rank": mce_rank, "mce_score": mce_score, "boolean_selected": 1,
            "agreement": "boolean_only", "reason": reason,
        }
        union.append({"type": "Feature", "geometry": feature.get("geometry"), "properties": props})

    both = sum(1 for f in union if f["properties"]["agreement"] == "both")
    mce_only = sum(1 for f in union if f["properties"]["agreement"] == "mce_only")
    boolean_only = sum(1 for f in union if f["properties"]["agreement"] == "boolean_only")
    total = both + mce_only + boolean_only
    return {
        "collection": {"type": "FeatureCollection", "features": union},
        "counts": {"both": both, "mce_only": mce_only, "boolean_only": boolean_only,
                   "jaccard": round(both / total, 3) if total else 1.0},
    }
