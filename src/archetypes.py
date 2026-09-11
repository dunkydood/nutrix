"""Nutrition archetypes: groups of recipes with a similar nutrient profile.

A recipe's archetype is what it is like to eat, independent of what it is
called: a lean high-protein main, a sugary bake, a rich fatty side. Three lab
methods produce and explain the archetypes:

- K-means (program 5.1) finds the groups in the standardised nutrient space,
  with the number of groups chosen by silhouette score;
- a shallow CART tree (program 8) is fitted to the cluster labels so each
  archetype can be read as a few threshold rules, with its agreement with
  K-means reported as fidelity;
- PCA (program 6) projects the nutrient space to two dimensions for the
  recipe map in the app.

Clusters are named from their centroids by fixed nutrition thresholds, so the
names follow the data rather than being assigned by hand.
"""

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

from recipes import NUTRIENT_FEATURES


def archetype_name(c):
    """Up to two words for a centroid row of ``Archetypes.centroids``.

    Words are checked in priority order and each family (sugar, fat, energy,
    salt) contributes at most one.
    """
    words = []

    def add(word):
        if len(words) < 2:
            words.append(word)

    if c["sugar %"] >= 40:
        add("Sugary")
    elif c["sugar %"] >= 20:
        add("Sweet")
    if c["protein %"] >= 35:
        add("High-protein")
    if c["sat fat %"] >= 30:
        add("Buttery")
    elif c["fat %"] >= 55:
        add("Rich")
    if c["carbs %"] >= 55 and c["sugar %"] < 20:
        add("Starchy")
    if c["sodium mg/100kcal"] <= 15:
        add("Unsalted")
    elif c["sodium mg/100kcal"] >= 250:
        add("Salty")
    if c["kcal"] >= 450:
        add("Hearty")
    elif c["kcal"] <= 180:
        add("Light")
    return " & ".join(words) if words else "Balanced"


class Archetypes:
    def __init__(self, k=None, k_range=range(4, 11), random_state=42):
        self.k = k
        self.k_range = k_range
        self.random_state = random_state

    def _kmeans(self, k):
        return KMeans(n_clusters=k, n_init=10, random_state=self.random_state)

    def fit(self, recipes):
        X = recipes[NUTRIENT_FEATURES].to_numpy()
        self.scaler_ = StandardScaler().fit(X)
        Z = self.scaler_.transform(X)

        self.silhouette_ = {}
        if self.k is None:
            for k in self.k_range:
                labels = self._kmeans(k).fit_predict(Z)
                self.silhouette_[k] = silhouette_score(
                    Z, labels, sample_size=5000, random_state=self.random_state
                )
            self.k_ = max(self.silhouette_, key=self.silhouette_.get)
        else:
            self.k_ = self.k

        self.kmeans_ = self._kmeans(self.k_).fit(Z)
        labels = self.kmeans_.labels_
        self.shares_ = np.bincount(labels, minlength=self.k_) / len(labels)
        centroids = self.centroids()
        names = [archetype_name(row) for _, row in centroids.iterrows()]
        # Two clusters can earn the same words; number them.
        counts, seen = pd.Series(names).value_counts(), {}
        for i, name in enumerate(names):
            if counts[name] > 1:
                seen[name] = seen.get(name, 0) + 1
                names[i] = f"{name} {seen[name]}"
        self.names_ = names

        self.tree_ = DecisionTreeClassifier(
            max_depth=4, min_samples_leaf=200, random_state=self.random_state
        ).fit(X, labels)
        self.tree_fidelity_ = float((self.tree_.predict(X) == labels).mean())

        self.pca_ = PCA(n_components=2, random_state=self.random_state).fit(Z)
        return self

    def predict(self, recipes):
        Z = self.scaler_.transform(recipes[NUTRIENT_FEATURES].to_numpy())
        return self.kmeans_.predict(Z)

    def label(self, recipes):
        return np.asarray(self.names_, dtype=object)[self.predict(recipes)]

    def coordinates(self, recipes):
        Z = self.scaler_.transform(recipes[NUTRIENT_FEATURES].to_numpy())
        return self.pca_.transform(Z)

    def rules(self):
        return export_text(
            self.tree_,
            feature_names=NUTRIENT_FEATURES,
            class_names=list(self.names_),
            decimals=2,
        )

    def centroids(self):
        """Cluster centres in readable units, one row per cluster."""
        c = pd.DataFrame(
            self.scaler_.inverse_transform(self.kmeans_.cluster_centers_),
            columns=NUTRIENT_FEATURES,
        )
        return pd.DataFrame(
            {
                "share": self.shares_.round(3),
                "kcal": np.exp(c["log_kcal"]).round(0),
                "protein %": (100 * c["protein_pct"]).round(0),
                "carbs %": (100 * c["carbs_pct"]).round(0),
                "fat %": (100 * c["fat_pct"]).round(0),
                "sugar %": (100 * c["sugar_pct"]).round(0),
                "sat fat %": (100 * c["sat_fat_pct"]).round(0),
                "sodium mg/100kcal": np.expm1(c["log_sodium_density"]).round(0),
            }
        )

    def summary(self):
        table = self.centroids()
        table.insert(0, "archetype", self.names_)
        return table
