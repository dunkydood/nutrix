"""Check the meal planner on contrasting profiles.

    .venv/Scripts/python tests/check_planner.py

For each profile the planner builds a multi-day plan, and the largest daily
gap from the calorie target and from any macronutrient target is recorded,
with the solve time and whether any dish repeats. Results go to
outputs/app/planner_checks.json, which the project report reads.
"""

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build import BUNDLE, CATALOG  # noqa: E402
from energy import daily_target  # noqa: E402
from planner import plan_meals  # noqa: E402
from recommender import history_matrix  # noqa: E402

KCAL_LIMIT = 0.05
MACRO_LIMIT = 0.20

catalog = pd.read_parquet(CATALOG)
rec = joblib.load(BUNDLE)["recommender"]
quality = (catalog["rating"].fillna(catalog["rating"].median()) + 0.1 * np.log1p(catalog["n_ratings"])).rank(pct=True)
quality = pd.Series(quality.to_numpy(), index=catalog["recipe_id"])

liked = catalog.loc[catalog["title"].str.contains("Butter Chicken|Chicken Tikka Masala", regex=True), "recipe_id"].head(3)
H = history_matrix([rec.index.known_positions(liked)], len(rec.index))
curry = pd.Series(rec.content.score(H)[0], index=catalog["recipe_id"])

vegetarian = catalog[catalog["vegetarian"] & catalog["minutes"].le(120)]
vegan = catalog[catalog["vegan"] & catalog["minutes"].le(60)]

profiles = [
    ("Vegetarian woman, 25, maintain", vegetarian, quality, daily_target(70, 170, 25, False, "light", "maintain"), 7),
    ("Man who likes curries, 25, maintain", catalog, curry, daily_target(70, 175, 25, True, "light", "maintain"), 7),
    ("Vegan woman, 45, weight loss", vegan, None, daily_target(60, 160, 45, False, "sedentary", "lose"), 3),
    ("Active man, 22, muscle gain, no preference", catalog, None, daily_target(85, 185, 22, True, "active", "gain"), 7),
    ("Active man, 22, muscle gain, rating preference", catalog, quality, daily_target(85, 185, 22, True, "active", "gain"), 7),
]

cols = ["calories", "protein_g", "carbs_g", "fat_g"]
results = []
for name, recipes, preference, target, days in profiles:
    start = time.perf_counter()
    plan, totals = plan_meals(recipes, target, preference, days=days, course_col="course_final")
    seconds = time.perf_counter() - start
    gaps = np.abs(totals[cols].to_numpy() / totals[[f"{c}_target" for c in cols]].to_numpy() - 1)
    row = {
        "profile": name,
        "days": days,
        "target_kcal": round(target["kcal"]),
        "seconds": round(seconds, 1),
        "kcal_gap": float(gaps[:, 0].max()),
        "macro_gap": float(gaps[:, 1:].max()),
        "unique_recipes": int(plan["recipe_id"].nunique()),
        "meals": len(plan),
    }
    row["ok"] = row["kcal_gap"] <= KCAL_LIMIT and row["macro_gap"] <= MACRO_LIMIT and row["unique_recipes"] == row["meals"]
    results.append(row)
    print(f"{'PASS' if row['ok'] else 'FAIL'}  {name:48s} {days}d {seconds:5.1f}s  kcal {row['kcal_gap']:.1%}  macro {row['macro_gap']:.1%}")

out = ROOT / "outputs" / "app" / "planner_checks.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"kcal_limit": KCAL_LIMIT, "macro_limit": MACRO_LIMIT, "profiles": results}, indent=2))
sys.exit(0 if all(r["ok"] for r in results) else 1)
