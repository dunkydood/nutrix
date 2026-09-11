"""Predicting a recipe's course from its ingredients and nutrition.

About one recipe in nine has no course tag, and the meal planner cannot put
a recipe in the breakfast, lunch, dinner or snack slot without one. A linear
SVM trained on the tagged recipes fills the gap. Tags are deliberately not
used as features: the course tags are the labels, and the other tags often
restate them.

Features are TF-IDF weights over ingredient names plus the standardised
nutrient profile, preparation time and recipe size. The SVM is wrapped in a
calibrator so each prediction comes with a probability, and only confident
predictions are used.
"""

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from recipes import NUTRIENT_FEATURES, identity

NUMERIC_FEATURES = NUTRIENT_FEATURES + ["log_minutes", "n_steps", "n_ingredients"]

# Below this calibrated probability a predicted course is not trusted.
MIN_CONFIDENCE = 0.5


def course_frame(recipes):
    """The columns the course model reads."""
    frame = recipes[["ingredients"] + NUTRIENT_FEATURES + ["n_steps", "n_ingredients"]].copy()
    frame["log_minutes"] = np.log1p(recipes["minutes"])
    return frame


def build_course_model(C=0.3, random_state=42):
    features = ColumnTransformer(
        [
            (
                "ingredients",
                TfidfVectorizer(analyzer=identity, min_df=3, sublinear_tf=True),
                "ingredients",
            ),
            ("nutrition", StandardScaler(), NUMERIC_FEATURES),
        ]
    )
    svm = LinearSVC(C=C, class_weight="balanced", random_state=random_state)
    return make_pipeline(features, CalibratedClassifierCV(svm, cv=3))


def fit_course_model(recipes, **kwargs):
    """Fit on every recipe that has a course tag."""
    tagged = recipes[recipes["course"].notna()]
    model = build_course_model(**kwargs)
    model.fit(course_frame(tagged), tagged["course"])
    return model


def fill_courses(recipes, model, min_confidence=MIN_CONFIDENCE):
    """Add ``course_final``, ``course_source`` and ``course_confidence``.

    Tagged recipes keep their tag. Untagged recipes take the model's course
    when its probability clears ``min_confidence`` and stay unassigned
    otherwise, which keeps them out of the meal planner.
    """
    df = recipes.copy()
    df["course_final"] = df["course"]
    df["course_source"] = np.where(df["course"].notna(), "tag", None)
    df["course_confidence"] = np.where(df["course"].notna(), 1.0, np.nan)

    missing = df["course"].isna()
    if missing.any():
        proba = model.predict_proba(course_frame(df[missing]))
        best = proba.argmax(axis=1)
        confidence = proba.max(axis=1)
        predicted = pd.Series(model.classes_[best], index=df.index[missing])
        sure = confidence >= min_confidence
        df.loc[missing, "course_confidence"] = confidence
        df.loc[predicted.index[sure], "course_final"] = predicted[sure]
        df.loc[predicted.index[sure], "course_source"] = "model"
    return df
