"""Train every model the app uses and record how well each one does.

    .venv/Scripts/python src/build.py

Writes

    models/bundle.joblib            fitted models loaded by the app
    models/metrics.json             offline evaluation results
    data/processed/catalog.parquet  recipes with course, archetype, map
                                    position and rating

It takes several minutes. The notebook walks through the same steps in lab
program order with plots; this script is the reproducible pipeline behind
the app.
"""

import json
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import accuracy_score, f1_score, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit, KFold, cross_val_predict, train_test_split

from archetypes import Archetypes
from course import build_course_model, course_frame, fill_courses, fit_course_model
from energy import fit_intake_model, intake_features, load_nhanes
from photos import attach_photos
from recipes import PROCESSED_DIR, ROOT, load_interactions, load_recipes, recipe_stats
from recommender import (
    FEATURES,
    Evaluation,
    HybridRecommender,
    pool_ranks,
    ranker_models,
    ranking_metrics,
    sample_negatives,
)

MODELS_DIR = ROOT / "models"
BUNDLE = MODELS_DIR / "bundle.joblib"
METRICS = MODELS_DIR / "metrics.json"
CATALOG = PROCESSED_DIR / "catalog.parquet"

_START = time.time()


def log(message):
    print(f"[{time.time() - _START:5.0f}s] {message}", flush=True)


def evaluate_course_model(recipes, random_state=42):
    tagged = recipes[recipes["course"].notna()]
    train, test = train_test_split(
        tagged, test_size=0.2, stratify=tagged["course"], random_state=random_state
    )
    model = build_course_model().fit(course_frame(train), train["course"])
    pred = model.predict(course_frame(test))
    return {
        "accuracy": accuracy_score(test["course"], pred),
        "macro_f1": f1_score(test["course"], pred, average="macro"),
        "n_train": len(train),
        "n_test": len(test),
    }


def evaluate_intake_model(nhanes):
    X, y = intake_features(nhanes), nhanes["intake"]
    pred = cross_val_predict(LinearRegression(), X, y, cv=KFold(5, shuffle=True, random_state=42))
    return {
        "n": len(nhanes),
        "cv_r2": r2_score(y, pred),
        "cv_rmse": mean_squared_error(y, pred) ** 0.5,
        "formula_r2": r2_score(y, nhanes["formula_tdee"]),
        "formula_rmse": mean_squared_error(y, nhanes["formula_tdee"]) ** 0.5,
        "mean_intake": y.mean(),
        "mean_formula": nhanes["formula_tdee"].mean(),
    }


def select_ranker(val, random_state=42):
    """Compare ranker models on validation users held out from their training.

    The choice is made here, never on the test targets.
    """
    split = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=random_state)
    fit_idx, hold_idx = next(split.split(val, groups=val["user"]))
    fit_rows = sample_negatives(val.iloc[fit_idx])
    hold = val.iloc[hold_idx].copy()
    hold["user"] = pd.factorize(hold["user"])[0]
    n_hold = hold["user"].nunique()
    results = {}
    for name, model in ranker_models(random_state).items():
        model.fit(fit_rows[FEATURES], fit_rows["label"])
        p = model.predict_proba(hold[FEATURES])[:, 1]
        results[name] = ranking_metrics(pool_ranks(p, hold, n_hold))
    return results


def retrieval_recall(cand):
    return float(cand.groupby("user")["label"].max().mean())


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    metrics = {}

    recipes = load_recipes()
    interactions = load_interactions(recipes["recipe_id"])
    nhanes = load_nhanes()
    metrics["data"] = {
        "recipes": len(recipes),
        "interactions": len(interactions),
        "users": int(interactions["user_id"].nunique()),
        "nhanes_adults": len(nhanes),
    }
    log(f"data: {metrics['data']}")

    metrics["course"] = evaluate_course_model(recipes)
    course_model = fit_course_model(recipes)
    recipes = fill_courses(recipes, course_model)
    metrics["course"]["filled_by_model"] = int((recipes["course_source"] == "model").sum())
    metrics["course"]["unassigned"] = int(recipes["course_final"].isna().sum())
    log(f"course model: {metrics['course']}")

    archetypes = Archetypes().fit(recipes)
    recipes["archetype"] = archetypes.label(recipes)
    xy = archetypes.coordinates(recipes)
    recipes["map_x"], recipes["map_y"] = xy[:, 0], xy[:, 1]
    metrics["archetypes"] = {
        "k": int(archetypes.k_),
        "silhouette": {str(k): v for k, v in archetypes.silhouette_.items()},
        "tree_fidelity": archetypes.tree_fidelity_,
        "summary": archetypes.summary().to_dict(orient="records"),
    }
    log(f"archetypes: k={archetypes.k_}, names={archetypes.names_}")

    ev = Evaluation(recipes, interactions)
    rec_eval = ev.fit_recommender(course_col="course_final")
    metrics["evaluation_users"] = len(ev.users)
    metrics["generators"] = ev.evaluate_generators(rec_eval)
    log(f"generators: {metrics['generators']}")

    val = ev.candidate_frame(rec_eval, "val")
    test = ev.candidate_frame(rec_eval, "test")
    metrics["retrieval_recall"] = {"val": retrieval_recall(val), "test": retrieval_recall(test)}
    log(f"retrieval recall: {metrics['retrieval_recall']}")

    metrics["ranker_selection"] = select_ranker(val)
    best = max(metrics["ranker_selection"], key=lambda n: metrics["ranker_selection"][n]["HR@10"])
    log(f"ranker selection: {metrics['ranker_selection']} -> {best}")

    train_rows = sample_negatives(val)
    metrics["ranker_train_rows"] = len(train_rows)
    metrics["ranker_test"] = {}
    fitted = {}
    for name, model in ranker_models().items():
        model.fit(train_rows[FEATURES], train_rows["label"])
        p = model.predict_proba(test[FEATURES])[:, 1]
        metrics["ranker_test"][name] = ranking_metrics(pool_ranks(p, test, len(ev.users)))
        fitted[name] = model
    metrics["ranker_choice"] = best
    log(f"ranker test: {metrics['ranker_test']}")
    del val, test, rec_eval

    recommender = HybridRecommender(recipes, course_col="course_final").fit(interactions)
    recommender.ranker = fitted[best]

    stats = recipe_stats(interactions).reindex(recipes["recipe_id"])
    recipes["rating"] = stats["rating"].to_numpy()
    recipes["n_ratings"] = stats["n_ratings"].fillna(0).astype(int).to_numpy()
    recipes["n_reviews"] = stats["n_reviews"].fillna(0).astype(int).to_numpy()
    recipes = attach_photos(recipes)
    metrics["photos"] = {"with_photo": int(recipes["photo_url"].notna().sum())}

    intake_model = fit_intake_model(nhanes)
    metrics["intake"] = evaluate_intake_model(nhanes)
    typical_met = nhanes.groupby("activity", observed=True)["met_minutes"].median()
    log(f"intake model: {metrics['intake']}")

    recipes.to_parquet(CATALOG, index=False)
    joblib.dump(
        {
            "recommender": recommender,
            "course_model": course_model,
            "archetypes": archetypes,
            "intake_model": intake_model,
            "typical_met": {str(k): float(v) for k, v in typical_met.items()},
        },
        BUNDLE,
        compress=3,
    )
    with open(METRICS, "w") as f:
        json.dump(metrics, f, indent=2, default=float)
    log(f"wrote {BUNDLE.name}, {METRICS.name} and {CATALOG.name}")


if __name__ == "__main__":
    main()
