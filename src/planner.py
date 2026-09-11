"""Meal plans that hit a day's calorie and macronutrient targets.

Each day is a small mixed-integer program solved by HiGHS through
``scipy.optimize.milp``. For every meal slot the solver picks exactly one
recipe and a portion size. It minimises

    the relative gap between the day's calories, protein, carbohydrate and
    fat and the person's targets,
  + any sugar above 10% of energy and any sodium above 2300 mg,
  + a small penalty for portions other than one serving,
  + a penalty for recipes the recommender ranked low.

Each slot keeps a sensible share of the day because a portion is only
offered when its calories are near the slot's share. An explicit penalty on
each slot's calories was tried and removed: it made the program so much
harder that plans cut off by the time limit missed their calorie target by
up to 21%.

Multi-day plans are solved one day at a time, removing recipes already used,
so a week never repeats a dish. Solving the week as one program was tried
first; it is far slower to find any feasible plan and no better in practice.
"""

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import Bounds, LinearConstraint, milp

SLOTS = {
    "breakfast": {"share": 0.25, "courses": ("breakfast",)},
    "lunch": {"share": 0.35, "courses": ("main",)},
    "dinner": {"share": 0.30, "courses": ("main",)},
    "snack": {"share": 0.10, "courses": ("snack", "dessert", "beverage")},
}
PORTIONS = (0.5, 1.0, 1.5, 2.0)

# Nutrient column -> key in the target dict from energy.daily_target.
TARGETS = {"calories": "kcal", "protein_g": "protein", "carbs_g": "carbs", "fat_g": "fat"}
WEIGHTS = {"calories": 3.0, "protein_g": 1.5, "carbs_g": 1.0, "fat_g": 1.0}
# Penalty on each slot's calories against its share of the day. Off by
# default; see the module docstring.
SLOT_WEIGHT = 0.0
# A day further than this from its calorie target is solved again with a
# longer time limit.
KCAL_RETRY_GAP = 0.03
RETRY_TIME_FACTOR = 5
LIMIT_WEIGHT = 1.0
PORTION_PENALTY = 0.05

SUGAR_ENERGY_LIMIT = 0.10
SODIUM_LIMIT_MG = 2300

# A portion is offered only if its calories fall in this multiple of the
# slot's calorie share, so the solver is never tempted by two servings of a
# 1200 kcal casserole for a snack.
PORTION_KCAL_RANGE = (0.5, 1.6)

NUTRIENTS = ["calories", "protein_g", "carbs_g", "fat_g", "sugar_g", "sodium_mg"]


def _slot_options(recipes, preference, slot, target, n, course_col, rng, exploration):
    """(recipe_id, portion) pairs the solver may choose for one slot.

    Half the candidates are the most preferred recipes. The other half are
    recipes whose protein/carbohydrate/fat balance is close to the target's,
    favouring preferred ones among them. Without these, a strong taste for,
    say, rich curries leaves the solver nothing to fix a day short of
    carbohydrate with.
    """
    spec = SLOTS[slot]
    lo, hi = PORTION_KCAL_RANGE
    slot_kcal = spec["share"] * target["kcal"]
    eligible = recipes[
        recipes[course_col].isin(spec["courses"])
        & recipes["calories"].between(lo * slot_kcal / max(PORTIONS), hi * slot_kcal / min(PORTIONS))
    ]
    if eligible.empty:
        raise ValueError(f"No recipes fit the {slot} slot with the current filters.")
    ranking = preference.reindex(eligible.index).fillna(0).to_numpy()
    if exploration:
        ranking = ranking + exploration * rng.gumbel(size=len(ranking))
    goal = np.array([4 * target["protein"], 4 * target["carbs"], 9 * target["fat"]]) / target["kcal"]
    balance = np.abs(eligible[["protein_pct", "carbs_pct", "fat_pct"]].to_numpy() - goal).sum(axis=1)
    if np.ptp(ranking) == 0:
        # No preference to rank by; every candidate is chosen for balance.
        top = eligible.index[np.argsort(balance)[: 2 * n]]
    else:
        by_preference = eligible.index[np.argsort(-ranking)[:n]]
        by_balance = eligible.index[np.argsort(balance - 0.3 * ranking)[:n]]
        top = by_preference.union(by_balance)
    options = []
    for rid in top:
        for p in PORTIONS:
            if lo * slot_kcal <= recipes.at[rid, "calories"] * p <= hi * slot_kcal:
                options.append((slot, rid, p))
    return options


def _solve_day(x, target, preference, preference_weight, time_limit, mip_gap, slot_weight=SLOT_WEIGHT):
    """Solve one day's program over the candidate rows ``x``.

    With ``slot_weight`` 0 the per-slot calorie deviations are left out and
    each slot is held only by the portion calorie band.
    """
    n_x = len(x)
    dev_names = [f"{c}_{s}" for c in TARGETS for s in ("under", "over")]
    dev_names += ["sugar_over", "sodium_over"]
    if slot_weight > 0:
        dev_names += [f"{slot}_{s}" for slot in SLOTS for s in ("under", "over")]
    dev = {name: n_x + i for i, name in enumerate(dev_names)}
    n_vars = n_x + len(dev_names)
    sugar_limit = SUGAR_ENERGY_LIMIT * target["kcal"] / 4

    c = np.zeros(n_vars)
    # Exactly one recipe fills each slot, so penalising (1 - preference) ranks
    # plans the same as rewarding preference. It keeps the objective positive,
    # which lets the solver's relative optimality gap stop the search early.
    c[:n_x] = preference_weight * (1 - preference.reindex(x["recipe_id"]).fillna(0).to_numpy())
    c[:n_x] += PORTION_PENALTY * np.abs(x["portion"].to_numpy() - 1)
    for col, key in TARGETS.items():
        for side in ("under", "over"):
            c[dev[f"{col}_{side}"]] = WEIGHTS[col] / target[key]
    c[dev["sugar_over"]] = LIMIT_WEIGHT / sugar_limit
    c[dev["sodium_over"]] = LIMIT_WEIGHT / SODIUM_LIMIT_MG
    if slot_weight > 0:
        for slot, spec in SLOTS.items():
            for side in ("under", "over"):
                c[dev[f"{slot}_{side}"]] = slot_weight / (spec["share"] * target["kcal"])

    A_rows, A_cols, A_vals, lb, ub = [], [], [], [], []

    def add(cols, vals, low, high):
        r = len(lb)
        A_rows.extend([r] * len(cols))
        A_cols.extend(cols)
        A_vals.extend(vals)
        lb.append(low)
        ub.append(high)

    everything = list(range(n_x))
    slot_arr = x["slot"].to_numpy()
    for slot, spec in SLOTS.items():
        idx = list(np.flatnonzero(slot_arr == slot))
        add(idx, [1.0] * len(idx), 1, 1)
        if slot_weight > 0:
            slot_kcal = spec["share"] * target["kcal"]
            add(
                idx + [dev[f"{slot}_under"], dev[f"{slot}_over"]],
                list(x["calories"].to_numpy()[idx]) + [1, -1],
                slot_kcal,
                slot_kcal,
            )
    for col, key in TARGETS.items():
        add(
            everything + [dev[f"{col}_under"], dev[f"{col}_over"]],
            list(x[col].to_numpy()) + [1, -1],
            target[key],
            target[key],
        )
    add(everything + [dev["sugar_over"]], list(x["sugar_g"].to_numpy()) + [-1], -np.inf, sugar_limit)
    add(everything + [dev["sodium_over"]], list(x["sodium_mg"].to_numpy()) + [-1], -np.inf, SODIUM_LIMIT_MG)
    # Lunch and dinner draw from the same mains; do not serve one twice.
    for idx in x.groupby("recipe_id").indices.values():
        if len(set(slot_arr[idx])) > 1:
            add(list(idx), [1.0] * len(idx), 0, 1)

    A = sp.csr_array((A_vals, (A_rows, A_cols)), shape=(len(lb), n_vars))
    integrality = np.zeros(n_vars)
    integrality[:n_x] = 1
    upper = np.full(n_vars, np.inf)
    upper[:n_x] = 1
    result = milp(
        c,
        constraints=LinearConstraint(A, lb, ub),
        integrality=integrality,
        bounds=Bounds(np.zeros(n_vars), upper),
        options={"time_limit": time_limit, "mip_rel_gap": mip_gap},
    )
    if result.x is None:
        raise RuntimeError(f"Meal planning failed: {result.message}")
    return x[result.x[:n_x] > 0.5].copy()


def plan_meals(
    recipes,
    target,
    preference=None,
    days=1,
    pool_size=15,
    preference_weight=0.3,
    exploration=0.0,
    seed=None,
    course_col="course",
    time_limit=1.0,
    mip_gap=0.01,
    slot_weight=SLOT_WEIGHT,
):
    """Choose a recipe and portion for every slot of ``days`` days.

    ``recipes`` must already be filtered to what the person is willing to
    eat. ``preference`` maps recipe id to a score where higher is better; it
    is rescaled to 0-1. ``exploration`` adds Gumbel noise to the candidate
    ranking so that re-planning with a new ``seed`` gives a different plan.
    ``time_limit`` (seconds per day) and ``mip_gap`` (relative optimality
    gap) trade plan quality for speed; the best plan found so far is used
    when the time limit is reached. Proving a day optimal takes several
    seconds, so the default stops early; a day that ends more than
    ``KCAL_RETRY_GAP`` off its calorie target is solved again with three
    times the candidates and ``RETRY_TIME_FACTOR`` times the limit. Because the limit is in seconds,
    plans can differ slightly between runs.

    Returns ``(plan, totals)``: one row per meal, and one row per day with
    the nutrient totals next to the targets.
    """
    rng = np.random.default_rng(seed)
    recipes = recipes.set_index("recipe_id", drop=False)
    if preference is None:
        preference = pd.Series(0.0, index=recipes.index)
    preference = pd.Series(preference, dtype=float)
    span = preference.max() - preference.min()
    preference = (preference - preference.min()) / span if span > 0 else preference * 0

    def candidates(available, n):
        rows = []
        for slot in SLOTS:
            rows += _slot_options(available, preference, slot, target, n, course_col, rng, exploration)
        x = pd.DataFrame(rows, columns=["slot", "recipe_id", "portion"])
        for col in NUTRIENTS:
            x[col] = recipes.loc[x["recipe_id"], col].to_numpy() * x["portion"].to_numpy()
        return x

    used, meals = set(), []
    for d in range(days):
        available = recipes[~recipes.index.isin(used)]
        x = candidates(available, pool_size)
        day = _solve_day(x, target, preference, preference_weight, time_limit, mip_gap, slot_weight)
        if abs(day["calories"].sum() / target["kcal"] - 1) > KCAL_RETRY_GAP:
            # Retry with three times the candidates and a longer limit.
            x = candidates(available, 3 * pool_size)
            day = _solve_day(
                x, target, preference, preference_weight,
                RETRY_TIME_FACTOR * time_limit, mip_gap, slot_weight,
            )
        day.insert(0, "day", d)
        used.update(day["recipe_id"])
        meals.append(day)

    plan = pd.concat(meals, ignore_index=True)
    plan["title"] = recipes.loc[plan["recipe_id"], "title"].to_numpy()
    plan["course"] = recipes.loc[plan["recipe_id"], course_col].to_numpy()
    plan["slot"] = pd.Categorical(plan["slot"], categories=list(SLOTS), ordered=True)
    plan = plan.sort_values(["day", "slot"]).reset_index(drop=True)

    totals = plan.groupby("day")[NUTRIENTS].sum()
    for col, key in TARGETS.items():
        totals[f"{col}_target"] = target[key]
    totals["sugar_limit_g"] = SUGAR_ENERGY_LIMIT * target["kcal"] / 4
    totals["sodium_limit_mg"] = SODIUM_LIMIT_MG
    return plan, totals.reset_index()
