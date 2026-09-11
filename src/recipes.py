"""Loading and cleaning the Food.com recipes and reviews.

Two files from the Food.com Recipes and Interactions dataset (Majumder et al.,
EMNLP 2019), in the 2008-2018 cut distributed by UCSD's data science courses:

    RAW_recipes.csv       one row per recipe: tags, ingredients, nutrition
    RAW_interactions.csv  one row per review: user, recipe, date, rating 0-5

Food.com stores nutrition per serving as a list

    [calories, total fat, sugar, sodium, protein, saturated fat, carbohydrates]

where calories are kcal and the rest are percent of a daily value. The daily
values below were recovered from the data itself: with them, 4 kcal/g for
protein and carbohydrate plus 9 kcal/g for fat reproduce the stated calories
(median ratio 0.98), and sugar almost never exceeds total carbohydrate.

A rating of 0 means the user wrote a review without choosing stars. It is not
a bad rating, so it is kept as an interaction and dropped only where a star
value is needed.
"""

import ast
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

NUTRITION_FIELDS = [
    "calories", "fat_g", "sugar_g", "sodium_mg", "protein_g", "sat_fat_g", "carbs_g",
]
DAILY_VALUE = {
    "fat_g": 65, "sugar_g": 25, "sodium_mg": 2400,
    "protein_g": 50, "sat_fat_g": 20, "carbs_g": 300,
}

# Features that describe what a recipe is like nutritionally, independent of
# portion size except for log_kcal. Energy shares sum to one.
NUTRIENT_FEATURES = [
    "protein_pct", "carbs_pct", "fat_pct", "sugar_pct", "sat_fat_pct",
    "log_sodium_density", "log_kcal",
]

# Food.com attaches several course tags to many recipes (brownies are tagged
# desserts, lunch and snacks). The first matching tag in this order wins.
COURSE_TAGS = [
    ("beverages", "beverage"),
    ("desserts", "dessert"),
    ("frozen-desserts", "dessert"),
    ("breakfast", "breakfast"),
    ("brunch", "breakfast"),
    ("main-dish", "main"),
    ("lunch", "main"),
    ("side-dishes", "side"),
    ("salads", "side"),
    ("soups-stews", "side"),
    ("appetizers", "snack"),
    ("snacks", "snack"),
    ("condiments-etc", "condiment"),
    ("sauces", "condiment"),
    ("salad-dressings", "condiment"),
]
COURSES = ["breakfast", "main", "side", "snack", "dessert", "beverage", "condiment"]

# Diet filters offered to the user, each satisfied by any of its tags.
DIETS = {
    "vegetarian": {"vegetarian", "vegan"},
    "vegan": {"vegan"},
    "gluten-free": {"gluten-free"},
    "low-carb": {"low-carb", "very-low-carbs"},
    "low-sodium": {"low-sodium"},
    "egg-free": {"egg-free", "vegan"},
    "nut-free": {"nut-free"},
    "diabetic-friendly": {"diabetic"},
}

# Cleaning limits, per serving.
KCAL_RANGE = (20, 2500)
ATWATER_RANGE = (0.7, 1.3)
MAX_MINUTES = 24 * 60


def _parse_list(series):
    return series.map(ast.literal_eval)


def identity(doc):
    """Text analyzer for documents that are already lists of tokens.

    Defined at module level, not as a lambda, so fitted vectorizers pickle.
    """
    return doc


def course_from_tags(tags):
    """The course a recipe belongs to, or None if it has no course tag."""
    present = set(tags)
    for tag, course in COURSE_TAGS:
        if tag in present:
            return course
    return None


def display_name(name):
    """Food.com names arrive lower-case with punctuation stripped."""
    return " ".join(str(name).split()).title()


def add_nutrient_features(df):
    """Energy shares and densities computed from the gram columns."""
    df = df.copy()
    energy = 4 * df["protein_g"] + 4 * df["carbs_g"] + 9 * df["fat_g"]
    safe = energy.where(energy > 0)
    df["atwater_kcal"] = energy
    df["protein_pct"] = 4 * df["protein_g"] / safe
    df["carbs_pct"] = 4 * df["carbs_g"] / safe
    df["fat_pct"] = 9 * df["fat_g"] / safe
    df["sugar_pct"] = (4 * df["sugar_g"] / safe).clip(upper=1)
    df["sat_fat_pct"] = (9 * df["sat_fat_g"] / safe).clip(upper=1)
    kcal = df["calories"].where(df["calories"] > 0)
    # Sodium density is extremely skewed (brines and spice rubs carry
    # thousands of mg per 100 kcal), so it is modelled on a log scale.
    df["log_sodium_density"] = np.log1p(100 * df["sodium_mg"] / kcal)
    df["log_kcal"] = np.log(kcal)
    return df


def clean_recipes(raw):
    """Parse the raw recipe table and remove rows that cannot be trusted.

    Three rules, each reported in the notebook with how many rows it drops:

    - calories per serving outside ``KCAL_RANGE``: zero-calorie rows and rows
      where the whole recipe was entered as one serving;
    - stated calories that disagree with the macronutrients by more than
      30%, so the nutrition panel is internally inconsistent;
    - preparation time of zero or longer than a day.
    """
    df = raw.copy()
    df["tags"] = _parse_list(df["tags"])
    df["ingredients"] = _parse_list(df["ingredients"])
    df["steps"] = _parse_list(df["steps"])

    nutrition = pd.DataFrame(
        _parse_list(df["nutrition"]).tolist(), columns=NUTRITION_FIELDS, index=df.index
    )
    for col, dv in DAILY_VALUE.items():
        nutrition[col] = nutrition[col] / 100 * dv
    df = pd.concat([df.drop(columns=["nutrition"]), nutrition], axis=1)
    df = add_nutrient_features(df)

    ratio = df["atwater_kcal"] / df["calories"].where(df["calories"] > 0)
    keep = df["calories"].between(*KCAL_RANGE)
    keep &= ratio.between(*ATWATER_RANGE)
    keep &= df["minutes"].between(1, MAX_MINUTES)
    df = df.loc[keep].copy()

    df["title"] = df["name"].map(display_name)
    df["course"] = df["tags"].map(course_from_tags)
    for diet, tags in DIETS.items():
        df[diet] = df["tags"].map(lambda t, tags=tags: bool(tags & set(t)))
    df["submitted"] = pd.to_datetime(df["submitted"])
    df = df.rename(columns={"id": "recipe_id"})
    return df.reset_index(drop=True)


def load_recipes(data_dir=DATA_DIR, cache=True):
    """Cleaned recipes, read from the parquet cache when it exists."""
    path = PROCESSED_DIR / "recipes.parquet"
    if cache and path.exists():
        df = pd.read_parquet(path)
        for col in ("tags", "ingredients", "steps"):
            df[col] = df[col].map(list)
        return df
    df = clean_recipes(pd.read_csv(Path(data_dir) / "RAW_recipes.csv"))
    if cache:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
    return df


def load_interactions(recipe_ids=None, data_dir=DATA_DIR, cache=True):
    """Reviews restricted to recipes that survived cleaning.

    Review text is not used by any model and is dropped to keep memory low.
    """
    path = PROCESSED_DIR / "interactions.parquet"
    if cache and path.exists():
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(
            Path(data_dir) / "RAW_interactions.csv",
            usecols=["user_id", "recipe_id", "date", "rating"],
        )
        df["date"] = pd.to_datetime(df["date"])
        if cache:
            PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=False)
    if recipe_ids is not None:
        df = df[df["recipe_id"].isin(set(recipe_ids))]
    return df.sort_values(["date", "user_id"], kind="stable").reset_index(drop=True)


def recipe_stats(interactions):
    """Review count and a shrunk mean star rating for every reviewed recipe.

    The mean is pulled toward the global mean by ``m`` pseudo-reviews, so a
    single five-star review does not outrank a recipe with a hundred 4.8s.
    """
    rated = interactions[interactions["rating"] > 0]
    m = 5
    global_mean = rated["rating"].mean()
    agg = rated.groupby("recipe_id")["rating"].agg(["sum", "count"])
    stats = pd.DataFrame(
        {
            "n_ratings": agg["count"],
            "rating": (agg["sum"] + m * global_mean) / (agg["count"] + m),
        }
    )
    stats["n_reviews"] = interactions.groupby("recipe_id").size()
    return stats
