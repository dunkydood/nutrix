"""NUTRIX API: the trained models and the user's food log behind the React app.

    .venv/Scripts/python -m uvicorn api.main:app --reload --port 8000

Run from the project root after ``src/build.py``. When ``frontend/dist``
exists (``npm run build`` in ``frontend/``) the same process also serves the
app, so the whole thing runs on http://localhost:8000.

There is one local profile and no login. The profile, liked recipes and the
meal log live in ``data/user/nutrix.db``.
"""

import json
import os
import sqlite3
import sys
from contextlib import closing
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build import BUNDLE, CATALOG, METRICS  # noqa: E402
from energy import ACTIVITY_LEVELS, GOAL_ADJUST, MACRO_SPLIT, PAL, daily_target, intake_features  # noqa: E402
from photos import attach_photos  # noqa: E402
from planner import SLOTS, SODIUM_LIMIT_MG, SUGAR_ENERGY_LIMIT, plan_meals  # noqa: E402
from recipes import COURSES, DIETS  # noqa: E402
from recommender import history_matrix  # noqa: E402

USER_DIR = ROOT / "data" / "user"
# NUTRIX_DB points the API at another database, e.g. a demo or test log.
DB = Path(os.environ.get("NUTRIX_DB", USER_DIR / "nutrix.db"))
DIST = ROOT / "frontend" / "dist"

Slot = Literal["breakfast", "lunch", "dinner", "snack"]
Status = Literal["planned", "eaten"]

ACTIVITY_LABELS = {
    "sedentary": "Sedentary",
    "light": "Lightly Active",
    "moderate": "Moderately Active",
    "active": "Very Active",
}
ACTIVITY_HELP = {
    "sedentary": "Desk job, little exercise",
    "light": "On your feet some of the day, or exercise 1-3 days a week",
    "moderate": "Exercise 3-5 days a week",
    "active": "Hard exercise most days or a physical job",
}
GOAL_LABELS = {"lose": "Weight Loss", "maintain": "Maintain Weight", "gain": "Muscle Gain"}
DIET_LABELS = {d: d.replace("-", " ").title().replace("Free", "free") for d in DIETS}

DEFAULT_PROFILE = {
    "name": "",
    "sex": "female",
    "age": 25,
    "height_cm": 170,
    "weight_kg": 70,
    "activity": "light",
    "goal": "maintain",
    "diets": [],
    "excluded": [],
    "max_minutes": 120,
}

# A logged day counts toward the weekly goal when eaten calories land within
# this share of the target.
ON_TARGET = 0.10

NUTRIENT_KEYS = {
    "kcal": "calories",
    "protein": "protein_g",
    "carbs": "carbs_g",
    "fat": "fat_g",
    "sugar": "sugar_g",
    "sodium": "sodium_mg",
}

# ------------------------------------------------------------------ models

bundle = joblib.load(BUNDLE)
rec = bundle["recommender"]
archetypes = bundle["archetypes"]
with open(METRICS) as f:
    metrics = json.load(f)

catalog = pd.read_parquet(CATALOG)
if "card_url" not in catalog.columns:
    catalog = attach_photos(catalog)
for col in ("tags", "ingredients", "steps"):
    catalog[col] = catalog[col].map(list)
if not np.array_equal(catalog["recipe_id"].to_numpy(), rec.index.ids):
    raise RuntimeError("catalog.parquet does not match the recommender; rerun src/build.py")
by_id = catalog.set_index("recipe_id", drop=False)


# ------------------------------------------------------------------ storage

def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS likes (recipe_id INTEGER PRIMARY KEY, added_at TEXT NOT NULL)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            slot TEXT NOT NULL,
            recipe_id INTEGER NOT NULL,
            servings REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    return conn


def get_profile():
    with closing(db()) as conn:
        row = conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()
    return {**DEFAULT_PROFILE, **(json.loads(row["data"]) if row else {})}


def liked_ids():
    with closing(db()) as conn:
        return [r["recipe_id"] for r in conn.execute("SELECT recipe_id FROM likes ORDER BY added_at")]


def require_recipe(recipe_id):
    if recipe_id not in by_id.index:
        raise HTTPException(404, f"Recipe {recipe_id} not found")


# ------------------------------------------------------------------ helpers

def targets_for(p):
    t = daily_target(p["weight_kg"], p["height_cm"], p["age"], p["sex"] == "male", p["activity"], p["goal"])
    t["sugar_limit"] = SUGAR_ENERGY_LIMIT * t["kcal"] / 4
    t["sodium_limit"] = SODIUM_LIMIT_MG
    t["split"] = MACRO_SPLIT[p["goal"]]
    t["pal"] = PAL[p["activity"]]
    t["adjust"] = GOAL_ADJUST[p["goal"]]
    return t


@lru_cache(maxsize=64)
def _allowed(diets, excluded, max_minutes):
    mask = catalog["minutes"].le(max_minutes).to_numpy(dtype=bool)
    for diet in diets:
        mask = mask & catalog[diet].to_numpy(dtype=bool)
    if excluded:
        hit = catalog["ingredients"].map(lambda ings: any(term in ing for ing in ings for term in excluded))
        mask = mask & ~hit.to_numpy(dtype=bool)
    mask.setflags(write=False)
    return mask


def mask_for(p):
    excluded = tuple(sorted({t.strip().lower() for t in p["excluded"] if t.strip()}))
    return _allowed(tuple(sorted(p["diets"])), excluded, int(p["max_minutes"]))


def _num(value, digits=1):
    return None if pd.isna(value) else round(float(value), digits)


def highlight_tags(r):
    tags = []
    if r["vegan"]:
        tags.append("Vegan")
    elif r["vegetarian"]:
        tags.append("Vegetarian")
    if r["protein_pct"] >= 0.30:
        tags.append("High Protein")
    if r["carbs_pct"] <= 0.15:
        tags.append("Low Carb")
    if r["minutes"] <= 30:
        tags.append("Quick Meal")
    if r["gluten-free"]:
        tags.append("Gluten-free")
    return tags[:2] or [r["archetype"]]


def card(recipe_id, servings=1.0):
    r = by_id.loc[recipe_id]
    return {
        "id": int(recipe_id),
        "name": str(r["display_name"]),
        "course": None if pd.isna(r["course_final"]) else str(r["course_final"]),
        "archetype": str(r["archetype"]),
        "minutes": int(r["minutes"]),
        "image": None if pd.isna(r["card_url"]) else str(r["card_url"]),
        "servings": servings,
        "kcal": round(float(r["calories"]) * servings),
        "protein": round(float(r["protein_g"]) * servings, 1),
        "carbs": round(float(r["carbs_g"]) * servings, 1),
        "fat": round(float(r["fat_g"]) * servings, 1),
        "sugar": round(float(r["sugar_g"]) * servings, 1),
        "sodium": round(float(r["sodium_mg"]) * servings),
        "rating": _num(r["rating"], 2),
        "reviews": int(r["n_reviews"]),
        "tags": highlight_tags(r),
    }


def meal_kcal(t):
    return t["kcal"] / 3


def nutrition_fit(recipe_ids, t):
    """0-1: how close each recipe is to a main meal's calories and the target macro balance."""
    r = by_id.loc[recipe_ids]
    kcal_fit = np.exp(-1.5 * np.abs(np.log(r["calories"].to_numpy() / meal_kcal(t))))
    goal = np.array([4 * t["protein"], 4 * t["carbs"], 9 * t["fat"]]) / t["kcal"]
    shares = r[["protein_pct", "carbs_pct", "fat_pct"]].to_numpy()
    macro_fit = 1 - np.abs(shares - goal).sum(axis=1) / 2
    return 0.5 * kcal_fit + 0.5 * macro_fit


def reasons(recipe_id, t, p, because):
    r = by_id.loc[recipe_id]
    meal = meal_kcal(t)
    out = [
        {"text": "Fits your calorie target", "ok": bool(0.65 * meal <= r["calories"] <= 1.35 * meal)},
        {"text": "Supports your protein goal", "ok": bool(r["protein_pct"] >= t["split"]["protein"] - 0.05)},
        {
            "text": "Matches your dietary preferences" if (p["diets"] or p["excluded"]) else "No food restrictions set",
            "ok": True,
        },
        {"text": f"Ready in {int(r['minutes'])} minutes", "ok": bool(r["minutes"] <= p["max_minutes"])},
    ]
    if because:
        out.append({"text": f"Similar to {because}, which you liked", "ok": True})
    return out


_rec_cache = {}


def recommend_cards(p, n, course=None, exclude=(), courses=None):
    """Recommendations with a match score and the reasons behind it.

    The ranker orders candidates by taste. ``match`` blends that taste rank
    (among the candidates) with nutrition fit for this person's targets, and
    is scaled to 60-99 so it reads as a strength rather than a probability.
    Condiments are never recommended; ``courses`` narrows further.
    """
    liked = liked_ids()
    key = json.dumps([p, liked, n, course, sorted(exclude), courses], sort_keys=True, default=str)
    if key not in _rec_cache:
        if len(_rec_cache) > 64:
            _rec_cache.clear()
        _rec_cache[key] = _recommend_cards(p, n, course, exclude, courses, liked)
    return _rec_cache[key]


def _recommend_cards(p, n, course, exclude, courses, liked):
    t = targets_for(p)
    mask = mask_for(p).copy()
    mask &= (catalog["course_final"] != "condiment").to_numpy()
    if course:
        mask &= (catalog["course_final"] == course).to_numpy()
    if courses:
        mask &= catalog["course_final"].isin(courses).to_numpy()
    if exclude:
        mask[rec.index.known_positions(list(exclude))] = False
    found = rec.recommend(liked, n=max(4 * n, 40), allowed=mask)
    if found.empty:
        return []
    ids = found["recipe_id"].to_numpy()
    taste = found["score"].rank(pct=True).to_numpy()
    match = 60 + 39 * (0.5 * taste + 0.5 * nutrition_fit(ids, t))
    order = np.argsort(-match)[:n]
    chosen = [int(ids[i]) for i in order]
    explained = rec.explain(chosen, liked) if liked else None
    cards = []
    for k, i in enumerate(order):
        rid = chosen[k]
        because = None
        if explained is not None and pd.notna(explained.at[k, "because"]) and explained.at[k, "similarity"] > 0.05:
            because = str(by_id.at[int(explained.at[k, "because"]), "display_name"])
        cards.append({**card(rid), "match": int(round(match[i])), "because": because, "reasons": reasons(rid, t, p, because)})
    return cards


def planner_preference(p, use_likes):
    """Planner preference: well-rated recipes, pulled toward the liked ones."""
    quality = (catalog["rating"].fillna(catalog["rating"].median()) + 0.1 * np.log1p(catalog["n_ratings"])).rank(pct=True)
    score = quality.to_numpy()
    positions = rec.index.known_positions(liked_ids()) if use_likes else []
    if len(positions):
        H = history_matrix([positions], len(rec.index))
        score = 0.4 * score + 0.6 * pd.Series(rec.content.score(H)[0]).rank(pct=True).to_numpy()
    mask = mask_for(p)
    return pd.Series(score[mask], index=catalog["recipe_id"].to_numpy()[mask])


def entries_between(start, end):
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM log WHERE day BETWEEN ? AND ? ORDER BY day, CASE slot "
            "WHEN 'breakfast' THEN 0 WHEN 'lunch' THEN 1 WHEN 'dinner' THEN 2 ELSE 3 END, id",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    return [
        {**card(r["recipe_id"], r["servings"]), "entry_id": r["id"], "day": r["day"], "slot": r["slot"], "status": r["status"]}
        for r in rows
        if r["recipe_id"] in by_id.index
    ]


def totals(entries):
    out = {k: 0.0 for k in NUTRIENT_KEYS}
    for e in entries:
        for k in out:
            out[k] += e[k]
    return {k: round(v, 1) for k, v in out.items()}


def day_totals(entries, day, status="eaten"):
    return totals([e for e in entries if e["day"] == day and e["status"] == status])


MEAL_COURSES = ["breakfast", "main", "side"]

# By these hours a meal is usually eaten, so its share of the day's target
# is expected to be in the log.
MEAL_HOURS = [(10, "breakfast"), (15, "lunch"), (21, "dinner")]


def expected_share(hour):
    return sum(SLOTS[slot]["share"] for h, slot in MEAL_HOURS if hour >= h)


def suggest_meal(p, macro, max_kcal):
    """A recommended meal rich in ``macro`` that fits the calories left."""
    share = {"protein": "protein_pct", "carbs": "carbs_pct", "fat": "fat_pct"}[macro]
    fitting = [c for c in recommend_cards(p, 16, courses=MEAL_COURSES) if c["kcal"] <= max(max_kcal, 300)]
    return max(fitting, key=lambda c: by_id.at[c["id"], share], default=None)


def insight(p, t, eaten, planned):
    """One actionable sentence about today, from the log against the targets.

    With meals planned for the rest of the day the whole day is judged;
    otherwise what has been eaten is compared with what is normally eaten by
    this time, so the morning is not reported as a shortfall.
    """
    combined = {k: eaten[k] + planned[k] for k in eaten}
    if planned["kcal"]:
        expected, scope = 1.0, "with what you've eaten and planned today"
    else:
        expected, scope = expected_share(datetime.now().hour), "for this point in the day"
    if combined["kcal"] == 0:
        breakfast = SLOTS["breakfast"]["share"] * t["kcal"]
        return {
            "text": f"Nothing logged yet today. Your target is {t['kcal']:,.0f} kcal; a breakfast of about "
                    f"{breakfast:,.0f} kcal is a good start, or plan the whole day.",
            "action": "meal-plan",
        }
    if expected == 0:
        return {"text": "Breakfast is logged. Plan the rest of your day to stay on target.", "action": "meal-plan"}
    if combined["kcal"] > 1.1 * expected * t["kcal"]:
        over = combined["kcal"] / (expected * t["kcal"]) - 1
        return {"text": f"You're {over:.0%} over your calorie target {scope}. Keep the next meal light.", "action": "meal-plan"}
    gaps = {m: 1 - combined[m] / (expected * t[m]) for m in ("protein", "carbs", "fat")}
    macro = max(gaps, key=gaps.get)
    if gaps[macro] <= 0.15:
        return {"text": "You're on track with your targets today. Nice work.", "action": "meal-plan"}
    label = {"protein": "protein", "carbs": "carbohydrate", "fat": "fat"}[macro]
    text = f"You're {gaps[macro]:.0%} below your {label} target {scope}."
    pick = suggest_meal(p, macro, t["kcal"] - combined["kcal"])
    if pick:
        text += f" {pick['name']} ({pick[macro]:.0f} g {label}, {pick['kcal']} kcal) would help."
    return {"text": text, "action": "recommendations"}


# ------------------------------------------------------------------ app

app = FastAPI(title="NUTRIX API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProfileIn(BaseModel):
    name: str | None = Field(None, max_length=40)
    sex: Literal["female", "male"] | None = None
    age: int | None = Field(None, ge=18, le=79)
    height_cm: float | None = Field(None, ge=130, le=220)
    weight_kg: float | None = Field(None, ge=35, le=250)
    activity: Literal["sedentary", "light", "moderate", "active"] | None = None
    goal: Literal["lose", "maintain", "gain"] | None = None
    diets: list[str] | None = None
    excluded: list[str] | None = None
    max_minutes: int | None = Field(None, ge=10, le=1440)


class LogIn(BaseModel):
    day: date | None = None
    slot: Slot
    recipe_id: int
    servings: float = Field(1.0, gt=0, le=4)
    status: Status = "planned"


class LogPatch(BaseModel):
    slot: Slot | None = None
    servings: float | None = Field(None, gt=0, le=4)
    status: Status | None = None


class PlanIn(BaseModel):
    days: int = Field(1, ge=1, le=7)
    start: date | None = None
    shuffle: bool = False
    seed: int = 0
    use_likes: bool = True


class PlanMeal(BaseModel):
    day: date
    slot: Slot
    recipe_id: int
    servings: float = Field(1.0, gt=0, le=4)


class PlanSave(BaseModel):
    meals: list[PlanMeal]
    replace_planned: bool = True


@app.get("/api/meta")
def meta():
    return {
        "activity": [{"value": a, "label": ACTIVITY_LABELS[a], "help": ACTIVITY_HELP[a]} for a in ACTIVITY_LEVELS],
        "goals": [{"value": g, "label": GOAL_LABELS[g], "adjust": GOAL_ADJUST[g]} for g in GOAL_ADJUST],
        "diets": [{"value": d, "label": DIET_LABELS[d]} for d in DIETS],
        "courses": [c for c in COURSES if c != "condiment"],
        "archetypes": list(archetypes.names_),
        "slots": list(SLOTS),
        "recipes": len(catalog),
        "with_photo": int(catalog["card_url"].notna().sum()),
    }


@app.get("/api/profile")
def read_profile():
    p = get_profile()
    t = targets_for(p)
    person = pd.DataFrame(
        {
            "age": [p["age"]],
            "male": [int(p["sex"] == "male")],
            "weight": [p["weight_kg"]],
            "height": [p["height_cm"]],
            "met_minutes": [bundle["typical_met"][p["activity"]]],
        }
    )
    reported = float(bundle["intake_model"].predict(intake_features(person))[0])
    return {
        "profile": p,
        "targets": t,
        "labels": {
            "goal": GOAL_LABELS[p["goal"]],
            "activity": ACTIVITY_LABELS[p["activity"]],
            "diet": ", ".join(DIET_LABELS[d] for d in p["diets"]) or "No Diet Filter",
            "allergies": ("Avoids " + ", ".join(p["excluded"])) if p["excluded"] else "No Exclusions",
        },
        "nhanes": {
            "reported_kcal": round(reported),
            "cv_r2": metrics["intake"]["cv_r2"],
            "n": metrics["intake"]["n"],
            "mean_formula": metrics["intake"]["mean_formula"],
            "mean_intake": metrics["intake"]["mean_intake"],
        },
    }


@app.put("/api/profile")
def update_profile(body: ProfileIn):
    changes = body.model_dump(exclude_none=True)
    unknown = set(changes.get("diets", [])) - set(DIETS)
    if unknown:
        raise HTTPException(422, f"Unknown diets: {sorted(unknown)}")
    p = {**get_profile(), **changes}
    with closing(db()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO profile (id, data) VALUES (1, ?)", (json.dumps(p),))
    return read_profile()


@app.get("/api/recommendations")
def recommendations(n: int = Query(12, ge=1, le=48), course: str | None = None):
    return {"items": recommend_cards(get_profile(), n, course=course), "liked": len(liked_ids())}


@app.get("/api/recipes")
def list_recipes(
    q: str = "",
    course: str | None = None,
    archetype: str | None = None,
    personal: bool = True,
    photos_only: bool = False,
    sort: Literal["popular", "rating", "quick", "protein", "light"] = "popular",
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=60),
):
    keep = mask_for(get_profile()).copy() if personal else np.ones(len(catalog), dtype=bool)
    if q.strip():
        term = q.strip().lower()
        in_name = catalog["display_name"].str.contains(term, case=False, regex=False).fillna(False).to_numpy(dtype=bool)
        in_ingredients = catalog["ingredients"].map(lambda ings: any(term in i for i in ings)).to_numpy(dtype=bool)
        keep &= in_name | in_ingredients
    if course:
        keep &= (catalog["course_final"] == course).to_numpy()
    if archetype:
        keep &= (catalog["archetype"] == archetype).to_numpy()
    if photos_only:
        keep &= catalog["card_url"].notna().to_numpy()
    df = catalog.loc[keep, ["recipe_id", "n_reviews", "rating", "minutes", "protein_pct", "calories", "card_url"]].copy()
    df["has_photo"] = df["card_url"].notna()
    key, ascending = {
        "popular": ("n_reviews", False),
        "rating": ("rating", False),
        "quick": ("minutes", True),
        "protein": ("protein_pct", False),
        "light": ("calories", True),
    }[sort]
    df = df.sort_values(["has_photo", key], ascending=[False, ascending], na_position="last")
    start = (page - 1) * page_size
    ids = df["recipe_id"].iloc[start:start + page_size]
    liked = set(liked_ids())
    return {
        "total": len(df),
        "page": page,
        "page_size": page_size,
        "items": [{**card(rid), "liked": int(rid) in liked} for rid in ids],
    }


@app.get("/api/recipes/{recipe_id}")
def recipe_detail(recipe_id: int):
    require_recipe(recipe_id)
    r = by_id.loc[recipe_id]
    p = get_profile()
    pos = rec.index.positions([recipe_id])
    similarity = rec.content.similarity(pos, np.arange(len(rec.index)))[0]
    similarity[pos[0]] = -1
    similarity[~mask_for(p)] = -1
    similar = [int(rec.index.ids[i]) for i in np.argsort(-similarity)[:6] if similarity[i] > 0]
    return {
        **card(recipe_id),
        "photo": None if pd.isna(r["photo_url"]) else str(r["photo_url"]),
        "description": None if pd.isna(r["description"]) else str(r["description"]),
        "ingredients": list(r["ingredients"]),
        "steps": list(r["steps"]),
        "sat_fat": round(float(r["sat_fat_g"]), 1),
        "course_source": None if pd.isna(r["course_source"]) else str(r["course_source"]),
        "liked": recipe_id in set(liked_ids()),
        "similar": [card(s) for s in similar],
    }


@app.get("/api/likes")
def list_likes():
    return {"items": [card(rid) for rid in liked_ids() if rid in by_id.index]}


@app.post("/api/likes/{recipe_id}")
def like(recipe_id: int):
    require_recipe(recipe_id)
    with closing(db()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO likes (recipe_id, added_at) VALUES (?, ?)", (recipe_id, datetime.now().isoformat()))
    return {"liked": True}


@app.delete("/api/likes/{recipe_id}")
def unlike(recipe_id: int):
    with closing(db()) as conn, conn:
        conn.execute("DELETE FROM likes WHERE recipe_id = ?", (recipe_id,))
    return {"liked": False}


@app.get("/api/log")
def read_log(day: date | None = None):
    day = day or date.today()
    entries = entries_between(day, day)
    return {
        "day": day.isoformat(),
        "entries": entries,
        "eaten": day_totals(entries, day.isoformat(), "eaten"),
        "planned": day_totals(entries, day.isoformat(), "planned"),
        "targets": targets_for(get_profile()),
    }


@app.post("/api/log")
def add_log(body: LogIn):
    require_recipe(body.recipe_id)
    day = body.day or date.today()
    with closing(db()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO log (day, slot, recipe_id, servings, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (day.isoformat(), body.slot, body.recipe_id, body.servings, body.status, datetime.now().isoformat()),
        )
    return {"entry_id": cur.lastrowid, **read_log(day)}


@app.patch("/api/log/{entry_id}")
def edit_log(entry_id: int, body: LogPatch):
    changes = body.model_dump(exclude_none=True)
    with closing(db()) as conn, conn:
        row = conn.execute("SELECT day FROM log WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Log entry not found")
        for field, value in changes.items():
            conn.execute(f"UPDATE log SET {field} = ? WHERE id = ?", (value, entry_id))
    return read_log(date.fromisoformat(row["day"]))


@app.delete("/api/log/{entry_id}")
def delete_log(entry_id: int):
    with closing(db()) as conn, conn:
        row = conn.execute("SELECT day FROM log WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Log entry not found")
        conn.execute("DELETE FROM log WHERE id = ?", (entry_id,))
    return read_log(date.fromisoformat(row["day"]))


@app.delete("/api/log")
def clear_log():
    with closing(db()) as conn, conn:
        conn.execute("DELETE FROM log")
    return {"cleared": True}


@app.post("/api/plan")
def make_plan(body: PlanIn):
    p = get_profile()
    t = targets_for(p)
    start = body.start or date.today()
    allowed = catalog[mask_for(p)]
    try:
        plan, day_sums = plan_meals(
            allowed,
            t,
            planner_preference(p, body.use_likes),
            days=body.days,
            course_col="course_final",
            exploration=0.15 if body.shuffle else 0.0,
            seed=body.seed,
        )
    except (ValueError, RuntimeError) as err:
        raise HTTPException(422, str(err))
    days = []
    for d, meals in plan.groupby("day"):
        items = [{**card(int(m.recipe_id), float(m.portion)), "slot": str(m.slot)} for m in meals.itertuples()]
        days.append({"date": (start + timedelta(days=int(d))).isoformat(), "meals": items, "totals": totals(items)})
    return {"targets": t, "days": days}


@app.post("/api/plan/save")
def save_plan(body: PlanSave):
    for meal in body.meals:
        require_recipe(meal.recipe_id)
    days = sorted({m.day.isoformat() for m in body.meals})
    now = datetime.now().isoformat()
    with closing(db()) as conn, conn:
        if body.replace_planned and days:
            conn.execute(
                f"DELETE FROM log WHERE status = 'planned' AND day IN ({','.join('?' * len(days))})", days
            )
        conn.executemany(
            "INSERT INTO log (day, slot, recipe_id, servings, status, created_at) VALUES (?, ?, ?, ?, 'planned', ?)",
            [(m.day.isoformat(), m.slot, m.recipe_id, m.servings, now) for m in body.meals],
        )
    return {"saved": len(body.meals), "days": days}


def week_start(day):
    return day - timedelta(days=day.weekday())


@app.get("/api/progress")
def progress(days: int = Query(30, ge=7, le=180)):
    t = targets_for(get_profile())
    today = date.today()
    start = today - timedelta(days=days - 1)
    entries = [e for e in entries_between(start, today) if e["status"] == "eaten"]
    series = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        s = totals([e for e in entries if e["day"] == d])
        s["day"] = d
        s["logged"] = s["kcal"] > 0
        s["on_target"] = bool(s["logged"] and abs(s["kcal"] / t["kcal"] - 1) <= ON_TARGET)
        series.append(s)
    return {"targets": t, "days": series, "on_target_band": ON_TARGET}


@app.get("/api/dashboard")
def dashboard():
    p = get_profile()
    info = read_profile()
    t = info["targets"]
    today = date.today()
    entries = entries_between(week_start(today) - timedelta(days=7), today)
    iso = today.isoformat()
    eaten = day_totals(entries, iso, "eaten")
    planned = day_totals(entries, iso, "planned")

    todays_ids = tuple(e["id"] for e in entries if e["day"] == iso)
    recs = recommend_cards(p, 4, exclude=todays_ids, courses=MEAL_COURSES)

    def pct(value, limit):
        return round(100 * value / limit) if limit else 0

    balance = [
        {"axis": "Protein", "intake": pct(eaten["protein"], t["protein"]), "target": 100},
        {"axis": "Carbs", "intake": pct(eaten["carbs"], t["carbs"]), "target": 100},
        {"axis": "Fat", "intake": pct(eaten["fat"], t["fat"]), "target": 100},
        {"axis": "Sugar", "intake": pct(eaten["sugar"], t["sugar_limit"]), "target": 100},
        {"axis": "Sodium", "intake": pct(eaten["sodium"], t["sodium_limit"]), "target": 100},
    ]

    monday = week_start(today)
    week = []
    for i in range(7):
        d = monday + timedelta(days=i)
        s = day_totals(entries, d.isoformat(), "eaten")
        week.append({
            "day": d.strftime("%a"),
            "date": d.isoformat(),
            "protein": s["protein"],
            "kcal": s["kcal"],
            "future": d > today,
            "on_target": bool(s["kcal"] and abs(s["kcal"] / t["kcal"] - 1) <= ON_TARGET),
        })
    last_week = [day_totals(entries, (monday - timedelta(days=7 - i)).isoformat(), "eaten") for i in range(7)]
    this_avg = [w["protein"] for w in week if w["kcal"] > 0]
    last_avg = [s["protein"] for s in last_week if s["kcal"] > 0]
    change = None
    if this_avg and last_avg and np.mean(last_avg) > 0:
        change = round(100 * (np.mean(this_avg) / np.mean(last_avg) - 1))

    hero = next((c["image"] for c in recs if c["image"]), None)
    return {
        "profile": p,
        "labels": info["labels"],
        "targets": t,
        "today": {"date": iso, "eaten": eaten, "planned": planned},
        "balance": balance,
        "insight": insight(p, t, eaten, planned),
        "recommendations": recs,
        "week": week,
        "protein_change": change,
        "weekly_goal": {"days_on_target": sum(w["on_target"] for w in week), "of": 7, "band": ON_TARGET},
        "hero_image": hero,
        "liked": len(liked_ids()),
    }


@app.get("/api/analytics")
def analytics():
    sample = catalog.sample(3000, random_state=0)
    return {
        "data": metrics["data"],
        "evaluation_users": metrics["evaluation_users"],
        "generators": metrics["generators"],
        "rankers": metrics["ranker_test"],
        "ranker_choice": metrics["ranker_choice"],
        "retrieval_recall": metrics["retrieval_recall"],
        "course": metrics["course"],
        "intake": metrics["intake"],
        "archetypes": archetypes.summary().to_dict(orient="records"),
        "tree_fidelity": archetypes.tree_fidelity_,
        "k": int(archetypes.k_),
        "map": [
            {"x": round(float(r.map_x), 3), "y": round(float(r.map_y), 3), "archetype": r.archetype, "name": r.display_name, "id": int(r.recipe_id)}
            for r in sample.itertuples()
        ],
    }


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = DIST / path
        if path and file.is_file():
            return FileResponse(file)
        return FileResponse(DIST / "index.html")
