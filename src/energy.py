"""Daily energy targets, and the NHANES survey data used to test them.

The app needs a calorie target before it can plan a day of meals. The
standard answer is the Mifflin-St Jeor equation for resting energy, scaled by
a physical activity level (PAL). This module implements that equation and
also loads NHANES 2017-2018, a nationally representative US survey that
measured real people's body size, activity and two days of food intake, so
the notebook can check the formula against what people actually eat.

NHANES files (SAS transport, from the CDC):

    DEMO_J    age, sex, pregnancy status
    BMX_J     measured weight and height
    DR1TOT_J  day 1 24-hour dietary recall totals
    DR2TOT_J  day 2 24-hour dietary recall totals
    PAQ_J     physical activity questionnaire
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"

# Multipliers on resting energy for each activity band.
PAL = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725}
ACTIVITY_LEVELS = list(PAL)

# Weekly MET-minute cut points between the bands above, following the WHO
# GPAQ convention of 600 MET-min/week as the minimum recommended activity.
MET_BINS = [-np.inf, 600, 1500, 3000, np.inf]

# kcal/day change applied for each goal. About 500 kcal/day is roughly
# 0.5 kg/week, the usual safe rate of change.
GOAL_ADJUST = {"lose": -500, "maintain": 0, "gain": 300}

# Share of energy from each macronutrient for each goal, and kcal per gram.
MACRO_SPLIT = {
    "lose": {"protein": 0.30, "carbs": 0.40, "fat": 0.30},
    "maintain": {"protein": 0.20, "carbs": 0.50, "fat": 0.30},
    "gain": {"protein": 0.25, "carbs": 0.50, "fat": 0.25},
}
KCAL_PER_GRAM = {"protein": 4, "carbs": 4, "fat": 9}

# Plausible reported intake per day. Recalls outside these ranges are almost
# always recording errors (Willett, Nutritional Epidemiology).
INTAKE_RANGE = {"male": (800, 4200), "female": (500, 3500)}

FEATURES = ["age", "male", "weight", "height", "met_minutes"]


def intake_features(df):
    """Regressors for reported intake. Activity is log-scaled because a few
    manual workers report tens of thousands of MET-minutes a week."""
    X = df[["age", "male", "weight", "height"]].astype(float).copy()
    X["log_met"] = np.log1p(df["met_minutes"].astype(float))
    return X


def fit_intake_model(df):
    """Linear regression of reported daily intake on age, sex, body size and
    activity, fitted on the NHANES adults."""
    return LinearRegression().fit(intake_features(df), df["intake"])


def mifflin_st_jeor(weight, height, age, male):
    """Resting energy in kcal/day from kg, cm, years and sex (1 = male)."""
    return 10 * weight + 6.25 * height - 5 * age + np.where(male, 5, -161)


def daily_target(weight, height, age, male, activity="moderate", goal="maintain"):
    """Calorie and macronutrient targets for one person.

    Returns a dict with ``kcal`` and grams of ``protein``, ``carbs`` and
    ``fat``. The calorie floor stops an aggressive goal from pushing the
    target below a level that is unsafe without supervision.
    """
    bmr = float(mifflin_st_jeor(weight, height, age, male))
    floor = 1500 if male else 1200
    kcal = max(bmr * PAL[activity] + GOAL_ADJUST[goal], floor)
    target = {"bmr": bmr, "kcal": kcal}
    for macro, share in MACRO_SPLIT[goal].items():
        target[macro] = kcal * share / KCAL_PER_GRAM[macro]
    return target


def _read(name, data_dir):
    return pd.read_sas(Path(data_dir) / f"{name}.xpt", format="xport")


def _met_minutes(paq):
    """Weekly MET-minutes from the five GPAQ activity domains.

    Vigorous activity counts 8 METs, moderate activity and active travel 4.
    Answers of "refused" or "don't know" (7/9 codes) are treated as missing
    and a domain the respondent said "no" to contributes zero.
    """
    domains = [
        ("PAQ605", "PAQ610", "PAD615", 8),  # vigorous work
        ("PAQ620", "PAQ625", "PAD630", 4),  # moderate work
        ("PAQ635", "PAQ640", "PAD645", 4),  # walk or bicycle for travel
        ("PAQ650", "PAQ655", "PAD660", 8),  # vigorous recreation
        ("PAQ665", "PAQ670", "PAD675", 4),  # moderate recreation
    ]
    total = pd.Series(0.0, index=paq.index)
    for does, days, minutes, met in domains:
        yes = paq[does] == 1
        d = paq[days].where(paq[days] <= 7)
        m = paq[minutes].where(paq[minutes] <= 960)
        part = (d * m * met).where(yes, 0.0)
        part[(paq[does] > 2)] = np.nan
        total = total + part
    return total


def activity_band(met_minutes):
    """Map weekly MET-minutes onto the PAL activity bands."""
    return pd.cut(met_minutes, bins=MET_BINS, labels=ACTIVITY_LEVELS)


def load_nhanes(data_dir=DATA_DIR, cache=True):
    """Adults with measured body size, activity and reliable dietary recalls.

    ``intake`` is the mean of the reliable recall days. A recall is kept only
    when NHANES flags it as complete and the respondent said the day was a
    usual day of eating, so one-off feasts and fasts do not become targets.

    Parsing the SAS transport files takes a few minutes, so the result is
    cached as parquet.
    """
    path = PROCESSED_DIR / "nhanes.parquet"
    if cache and path.exists():
        return pd.read_parquet(path)
    df = _build_nhanes(data_dir)
    if cache:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
    return df


def _build_nhanes(data_dir):
    demo =_read("DEMO_J", data_dir)[["SEQN", "RIAGENDR", "RIDAGEYR", "RIDEXPRG"]]
    body = _read("BMX_J", data_dir)[["SEQN", "BMXWT", "BMXHT", "BMXBMI"]]
    day1 = _read("DR1TOT_J", data_dir)
    day2 = _read("DR2TOT_J", data_dir)
    paq = _read("PAQ_J", data_dir)

    days = []
    for day, d in (("1", day1), ("2", day2)):
        ok = (d[f"DR{day}DRSTZ"] == 1) & (d[f"DR{day}_300"] == 2)
        days.append(d.loc[ok, ["SEQN", f"DR{day}TKCAL"]].rename(columns={f"DR{day}TKCAL": "kcal"}))
    recalls = pd.concat(days)
    intake = recalls.groupby("SEQN")["kcal"].agg(intake="mean", recall_days="size")

    macros = day1.loc[
        day1["DR1DRSTZ"] == 1, ["SEQN", "DR1TPROT", "DR1TCARB", "DR1TTFAT"]
    ].rename(columns={"DR1TPROT": "protein_g", "DR1TCARB": "carbs_g", "DR1TTFAT": "fat_g"})

    activity = pd.DataFrame({"SEQN": paq["SEQN"], "met_minutes": _met_minutes(paq)})

    df = (
        demo.merge(body, on="SEQN")
        .merge(activity, on="SEQN")
        .merge(intake.reset_index(), on="SEQN")
        .merge(macros, on="SEQN", how="left")
    )
    df = df.rename(
        columns={
            "RIDAGEYR": "age",
            "BMXWT": "weight",
            "BMXHT": "height",
            "BMXBMI": "bmi",
        }
    )
    df["male"] = (df["RIAGENDR"] == 1).astype(int)
    df["sex"] = np.where(df["male"] == 1, "male", "female")

    # Adults only; 80 is top-coded ("80 and over") so its age is not exact.
    # Pregnancy changes energy needs, so pregnant respondents are excluded.
    keep = (df["age"].between(18, 79)) & (df["RIDEXPRG"] != 1)
    keep &= df[["weight", "height", "met_minutes"]].notna().all(axis=1)
    lo = np.where(df["male"] == 1, INTAKE_RANGE["male"][0], INTAKE_RANGE["female"][0])
    hi = np.where(df["male"] == 1, INTAKE_RANGE["male"][1], INTAKE_RANGE["female"][1])
    keep &= df["intake"].between(lo, hi)
    df = df.loc[keep].copy()

    df["activity"] = activity_band(df["met_minutes"])
    df["bmr"] = mifflin_st_jeor(df["weight"], df["height"], df["age"], df["male"])
    df["formula_tdee"] = df["bmr"] * df["activity"].map(PAL).astype(float)
    cols = [
        "SEQN", "age", "sex", "male", "weight", "height", "bmi", "met_minutes",
        "activity", "bmr", "formula_tdee", "intake", "recall_days",
        "protein_g", "carbs_g", "fat_g",
    ]
    return df[cols].reset_index(drop=True)
