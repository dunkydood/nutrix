"""Recipe recommendation from review history.

A review on Food.com means the user cooked the recipe, so every review counts
as a positive signal (implicit feedback) whatever its stars. The recommender
has the two-stage shape used by production systems:

1. Candidate generators score every recipe for a user:
   - popularity: how many people reviewed the recipe;
   - PureSVD collaborative filtering: a truncated SVD of the user x recipe
     matrix, so users who cooked similar things share latent factors;
   - content: TF-IDF over ingredients and tags, matched against the recipes
     the user already cooked.
2. A learned ranker re-orders the union of the generators' top candidates,
   using their scores together with recipe and user-match features.

Offline evaluation is leave-last-out in time. For every user with at least
``MIN_HISTORY`` reviewed recipes the most recent one is hidden as the test
target and the one before it as the validation target. Generators see only
what is left; the ranker is trained on the validation targets and scored on
the test targets.

PureSVD folds a new history into the factor space without refitting, so the
same models serve app users who simply pick a few recipes they like.
"""

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, normalize

from recipes import COURSES, identity, recipe_stats

MIN_HISTORY = 3
TOP_K = 10
POOL_SIZE = 50
BATCH = 256

# Tags that describe Food.com's tag hierarchy rather than the recipe.
STRUCTURAL_TAGS = {
    "preparation", "time-to-make", "course", "main-ingredient", "dietary",
    "occasion", "cuisine", "equipment", "taste-mood", "number-of-servings",
    "low-in-something", "high-in-something", "free-of-something",
}

COURSE_CODES = COURSES + ["unknown"]

# Recipe columns in the order stored in ``HybridRecommender.recipe_features_``.
# The first five also describe a user's taste as the mean over their history.
RECIPE_FEATURES = [
    "log_kcal", "protein_pct", "carbs_pct", "fat_pct", "sugar_pct",
    "log_minutes", "n_ingredients", "rating", "log_n_ratings",
]
TASTE = 5

FEATURES = [
    "svd", "svd_z", "content", "content_z", "popularity", "popularity_z",
    "trending", "trending_z",
    *RECIPE_FEATURES,
    "kcal_gap", "shares_gap", "sugar_gap", "course_share", "log_history", "recipe_age",
]


class ItemIndex:
    """Maps recipe ids to matrix columns and back."""

    def __init__(self, recipe_ids):
        self.ids = np.asarray(recipe_ids)
        self._pos = pd.Series(np.arange(len(self.ids)), index=self.ids)

    def __len__(self):
        return len(self.ids)

    def positions(self, recipe_ids):
        """Column of each id; every id must be known."""
        return self._pos.loc[np.asarray(recipe_ids)].to_numpy()

    def known_positions(self, recipe_ids):
        """Columns of the ids that are known, silently skipping the rest."""
        return self._pos.reindex(np.asarray(recipe_ids)).dropna().astype(int).to_numpy()


def interaction_matrix(interactions, index):
    """Binary user x recipe matrix and the user id of each row."""
    users = pd.Index(interactions["user_id"].unique())
    rows = users.get_indexer(interactions["user_id"])
    cols = index.positions(interactions["recipe_id"])
    X = sp.coo_matrix(
        (np.ones(len(rows), dtype=np.float32), (rows, cols)),
        shape=(len(users), len(index)),
    ).tocsr()
    X.data[:] = 1
    return X, users


def history_matrix(histories, n_items):
    """Binary user x recipe matrix from lists of column positions."""
    rows = np.repeat(np.arange(len(histories)), [len(h) for h in histories])
    cols = np.concatenate([np.asarray(h, dtype=int) for h in histories]) if histories else []
    X = sp.coo_matrix(
        (np.ones(len(rows), dtype=np.float32), (rows, cols)),
        shape=(len(histories), n_items),
    ).tocsr()
    X.data[:] = 1
    return X


def temporal_split(interactions, min_history=MIN_HISTORY):
    """Leave-last-out split into train, validation and test interactions.

    Repeat reviews of the same recipe are collapsed to the first. Users with
    fewer than ``min_history`` distinct recipes stay entirely in train, where
    they still help the collaborative model learn.
    """
    df = interactions.drop_duplicates(["user_id", "recipe_id"], keep="first")
    df = df.sort_values("date", kind="stable")
    size = df.groupby("user_id")["recipe_id"].transform("size")
    recent = df.groupby("user_id").cumcount(ascending=False)
    eligible = size >= min_history
    test = df[eligible & (recent == 0)]
    val = df[eligible & (recent == 1)]
    train = df[~(eligible & (recent <= 1))]
    return train, val, test


class Popularity:
    def fit(self, X):
        counts = np.asarray(X.sum(axis=0)).ravel()
        self.scores_ = np.log1p(counts).astype(np.float32)
        return self

    def score(self, H):
        return np.tile(self.scores_, (H.shape[0], 1))


class Trending:
    """Reviews each recipe received in the months before a given day.

    Food.com activity moves over time, and a user's next recipe is often one
    that is being cooked a lot right now rather than an all-time favourite.
    The window ends before the month being served, so no review from that
    month or later is used.
    """

    def __init__(self, window_months=12):
        self.window_months = window_months

    def fit(self, interactions, index):
        month = interactions["date"].to_numpy().astype("datetime64[M]").astype(np.int64)
        self.first_month_ = int(month.min())
        rows = month - self.first_month_
        counts = sp.coo_matrix(
            (np.ones(len(rows), np.float32), (rows, index.positions(interactions["recipe_id"]))),
            shape=(int(rows.max()) + 1, len(index)),
        ).toarray()
        self.cumulative_ = np.vstack(
            [np.zeros((1, len(index)), np.float32), counts.cumsum(axis=0, dtype=np.float32)]
        )
        return self

    def score(self, ref_day):
        month = np.asarray(ref_day).astype("datetime64[D]").astype("datetime64[M]").astype(np.int64)
        hi = np.clip(month - self.first_month_, 0, len(self.cumulative_) - 1)
        lo = np.clip(hi - self.window_months, 0, None)
        return np.log1p(self.cumulative_[hi] - self.cumulative_[lo])


class PureSVD:
    def __init__(self, n_factors=64, random_state=42):
        self.n_factors = n_factors
        self.random_state = random_state

    def fit(self, X):
        svd = TruncatedSVD(self.n_factors, n_iter=7, random_state=self.random_state)
        svd.fit(X)
        self.components_ = svd.components_.astype(np.float32)
        self.explained_variance_ratio_ = svd.explained_variance_ratio_
        return self

    def user_factors(self, H):
        return np.asarray(H @ self.components_.T, dtype=np.float32)

    def score(self, H):
        return self.user_factors(H) @ self.components_


def recipe_tokens(ingredients, tags):
    return [f"ing:{i}" for i in ingredients] + [
        f"tag:{t}" for t in tags if t not in STRUCTURAL_TAGS
    ]


class ContentModel:
    def __init__(self, min_df=3):
        self.min_df = min_df

    def fit(self, recipes):
        docs = [recipe_tokens(i, t) for i, t in zip(recipes["ingredients"], recipes["tags"])]
        self.vectorizer_ = TfidfVectorizer(
            analyzer=identity, min_df=self.min_df, sublinear_tf=True, dtype=np.float32
        )
        self.matrix_ = normalize(self.vectorizer_.fit_transform(docs)).tocsr()
        return self

    def score(self, H):
        profiles = normalize(H @ self.matrix_).toarray()
        return np.ascontiguousarray((self.matrix_ @ profiles.T).T, dtype=np.float32)

    def similarity(self, rows, cols):
        return (self.matrix_[rows] @ self.matrix_[cols].T).toarray()


def mask_seen(S, seen):
    coo = seen.tocoo()
    S[coo.row, coo.col] = -np.inf


def rank_of(S, target):
    """0-based rank of each row's target column; ties count half."""
    t = S[np.arange(len(target)), target][:, None]
    higher = (S > t).sum(axis=1)
    ties = (S == t).sum(axis=1) - 1
    return higher + ties / 2


def ranking_metrics(ranks, k=TOP_K):
    """Hit rate, NDCG and MRR for one relevant item per user.

    A rank of ``inf`` marks a target the pipeline never surfaced.
    """
    ranks = np.asarray(ranks, dtype=float)
    hit = ranks < k
    with np.errstate(divide="ignore"):
        ndcg = np.where(hit, 1 / np.log2(ranks + 2), 0.0)
    return {
        f"HR@{k}": float(hit.mean()),
        f"NDCG@{k}": float(ndcg.mean()),
        "MRR": float(np.mean(1 / (ranks + 1))),
    }


class HybridRecommender:
    """Generators, recipe features and an optional ranker over one catalogue."""

    def __init__(self, recipes, n_factors=64, pool_size=POOL_SIZE, course_col="course"):
        self.n_factors = n_factors
        self.pool_size = pool_size
        self.index = ItemIndex(recipes["recipe_id"])
        self.content = ContentModel().fit(recipes)
        courses = pd.Categorical(recipes[course_col].fillna("unknown"), categories=COURSE_CODES)
        self.course_codes_ = np.asarray(courses.codes)
        self.course_onehot_ = sp.csr_matrix(
            (np.ones(len(recipes), np.float32), (np.arange(len(recipes)), self.course_codes_)),
            shape=(len(recipes), len(COURSE_CODES)),
        )
        self.submitted_day_ = recipes["submitted"].to_numpy().astype("datetime64[D]").astype(np.int64)
        self._static = pd.DataFrame(
            {
                "log_kcal": recipes["log_kcal"].to_numpy(),
                "protein_pct": recipes["protein_pct"].to_numpy(),
                "carbs_pct": recipes["carbs_pct"].to_numpy(),
                "fat_pct": recipes["fat_pct"].to_numpy(),
                "sugar_pct": recipes["sugar_pct"].to_numpy(),
                "log_minutes": np.log1p(recipes["minutes"]).to_numpy(),
                "n_ingredients": recipes["n_ingredients"].to_numpy(),
            }
        )
        self.ranker = None

    def fit(self, interactions):
        """Fit the generators and rating features on ``interactions``.

        Only the interactions passed here feed the rating features, so an
        evaluation run that passes the train split cannot see the targets.
        """
        X, self.users_ = interaction_matrix(interactions, self.index)
        self.popularity = Popularity().fit(X)
        self.trending = Trending().fit(interactions, self.index)
        self.svd = PureSVD(self.n_factors).fit(X)

        stats = recipe_stats(interactions).reindex(self.index.ids)
        global_mean = interactions.loc[interactions["rating"] > 0, "rating"].mean()
        features = self._static.copy()
        features["rating"] = stats["rating"].fillna(global_mean).to_numpy()
        features["log_n_ratings"] = np.log1p(stats["n_ratings"].fillna(0)).to_numpy()
        self.recipe_features_ = features[RECIPE_FEATURES].to_numpy(dtype=np.float32)
        self.end_day_ = int(interactions["date"].max().to_datetime64().astype("datetime64[D]").astype(np.int64))
        self.X_ = X
        return self

    def generator_scores(self, H, ref_day):
        return {
            "svd": self.svd.score(H),
            "content": self.content.score(H),
            "popularity": self.popularity.score(H),
            "trending": self.trending.score(ref_day),
        }

    def candidates(self, H, seen, ref_day, allowed=None, pool_from=None):
        """Feature rows for the union of each generator's top recipes.

        ``H`` is the history used to score, ``seen`` the recipes that must not
        be recommended, ``ref_day`` the day each user is being served (as
        days since the epoch) and ``allowed`` an optional boolean mask of
        recipes that pass the user's filters. Recipes submitted after the
        serving day did not exist yet and are never candidates.

        ``pool_from`` limits which generators contribute candidates (all by
        default); every generator's score is still computed as a feature.
        """
        B = H.shape[0]
        ref_day = np.asarray(ref_day)
        scores = self.generator_scores(H, ref_day)
        valid = self.submitted_day_[None, :] <= ref_day[:, None]
        coo = seen.tocoo()
        valid[coo.row, coo.col] = False
        if allowed is not None:
            valid[:, ~np.asarray(allowed)] = False

        z, tops = {}, {}
        n = min(self.pool_size, len(self.index) - 1)
        for name, S in scores.items():
            mu = S.mean(axis=1, keepdims=True)
            sd = S.std(axis=1, keepdims=True) + 1e-6
            z[name] = (S - mu) / sd
            if pool_from is None or name in pool_from:
                masked = np.where(valid, S, -np.inf)
                tops[name] = np.argpartition(-masked, n, axis=1)[:, :n]

        counts = np.asarray(H.sum(axis=1)).ravel()
        taste = (H @ self.recipe_features_[:, :TASTE]) / np.maximum(counts, 1)[:, None]
        course_mix = (H @ self.course_onehot_).toarray() / np.maximum(counts, 1)[:, None]

        parts = []
        for b in range(B):
            items = np.unique(np.concatenate([tops[name][b] for name in tops]))
            items = items[valid[b, items]]
            rf = self.recipe_features_[items]
            part = {
                "user": np.full(len(items), b),
                "item": items,
            }
            for name in scores:
                part[name] = scores[name][b, items]
                part[f"{name}_z"] = z[name][b, items]
            for j, col in enumerate(RECIPE_FEATURES):
                part[col] = rf[:, j]
            part["kcal_gap"] = np.abs(rf[:, 0] - taste[b, 0])
            part["shares_gap"] = np.abs(rf[:, 1:4] - taste[b, 1:4]).sum(axis=1)
            part["sugar_gap"] = rf[:, 4] - taste[b, 4]
            part["course_share"] = course_mix[b, self.course_codes_[items]]
            part["log_history"] = np.full(len(items), np.log1p(counts[b]))
            part["recipe_age"] = ((ref_day[b] - self.submitted_day_[items]) / 365.0).astype(np.float32)
            parts.append(pd.DataFrame(part))
        return pd.concat(parts, ignore_index=True)

    def score_candidates(self, cand):
        if self.ranker is None:
            return (cand["svd_z"] + cand["content_z"] + 0.5 * cand["popularity_z"]).to_numpy()
        return self.ranker.predict_proba(cand[FEATURES])[:, 1]

    def recommend(self, liked_ids, n=20, allowed=None, pool_from=("svd", "content")):
        """Top recipes for someone who likes ``liked_ids``.

        By default candidates come only from the personal generators and the
        ranker orders them. Offline, popularity and trending add retrieval
        hits, but for a person who has just said what they like, a roast
        turkey ranked on popularity alone reads as a wrong answer. Pass
        ``pool_from=None`` to use every generator.

        With no liked recipes there is nothing to personalise on, so the
        well-rated popular recipes that pass the filters are returned.
        """
        liked = self.index.known_positions(liked_ids)
        if len(liked) == 0:
            f = self.recipe_features_
            score = f[:, RECIPE_FEATURES.index("rating")] * np.log1p(self.popularity.scores_)
            if allowed is not None:
                score = np.where(allowed, score, -np.inf)
            top = np.argsort(-score)[:n]
            top = top[np.isfinite(score[top])]
            return pd.DataFrame({"recipe_id": self.index.ids[top], "score": score[top]})

        H = history_matrix([liked], len(self.index))
        cand = self.candidates(H, H, np.array([self.end_day_]), allowed=allowed, pool_from=pool_from)
        if cand.empty:
            return pd.DataFrame(columns=["recipe_id", "score", "svd_z", "content_z", "popularity"])
        cand["score"] = self.score_candidates(cand)
        cand = cand.sort_values("score", ascending=False).head(n)
        out = cand[["item", "score", "svd_z", "content_z", "popularity"]].copy()
        out.insert(0, "recipe_id", self.index.ids[out.pop("item").to_numpy()])
        return out.reset_index(drop=True)

    def explain(self, recipe_ids, liked_ids):
        """For each recipe, the liked recipe it is most similar to in content."""
        liked = self.index.known_positions(liked_ids)
        rows = self.index.positions(recipe_ids)
        if len(liked) == 0:
            return pd.DataFrame({"recipe_id": recipe_ids, "because": None, "similarity": np.nan})
        sim = self.content.similarity(rows, liked)
        best = sim.argmax(axis=1)
        return pd.DataFrame(
            {
                "recipe_id": recipe_ids,
                "because": self.index.ids[liked[best]],
                "similarity": sim[np.arange(len(rows)), best],
            }
        )


class Evaluation:
    """The leave-last-out setup shared by every offline experiment."""

    def __init__(self, recipes, interactions, min_history=MIN_HISTORY):
        self.train, self.val, self.test = temporal_split(interactions, min_history)
        self.users = self.test["user_id"].to_numpy()
        self.recipes = recipes
        index = ItemIndex(recipes["recipe_id"])
        by_user = self.train.groupby("user_id")
        histories = by_user["recipe_id"].apply(lambda s: index.positions(s))
        self.H = history_matrix(list(histories.loc[self.users]), len(index))
        self.val_pos = index.positions(self.val.set_index("user_id").loc[self.users, "recipe_id"])
        self.test_pos = index.positions(self.test.set_index("user_id").loc[self.users, "recipe_id"])
        # Each target is served on the day the user actually reviewed it.
        self.val_day = self._days(self.val)
        self.test_day = self._days(self.test)
        # At test time the validation recipe is part of the user's past.
        self.H_test = self.H + history_matrix([[p] for p in self.val_pos], len(index))
        self.H_test.data[:] = 1

    def _days(self, split):
        dates = split.set_index("user_id").loc[self.users, "date"]
        return dates.to_numpy().astype("datetime64[D]").astype(np.int64)

    def fit_recommender(self, **kwargs):
        return HybridRecommender(self.recipes, **kwargs).fit(self.train)

    def evaluate_generators(self, rec, k=TOP_K):
        """Full-catalogue ranking metrics of each generator on the test targets."""
        ranks = {"svd": [], "content": [], "popularity": [], "trending": []}
        for s in range(0, len(self.users), BATCH):
            H = self.H_test[s:s + BATCH]
            day = self.test_day[s:s + BATCH]
            target = self.test_pos[s:s + BATCH]
            future = rec.submitted_day_[None, :] > day[:, None]
            for name, S in rec.generator_scores(H, day).items():
                mask_seen(S, H)
                S[future] = -np.inf
                ranks[name].append(rank_of(S, target))
        return {name: ranking_metrics(np.concatenate(r), k) for name, r in ranks.items()}

    def candidate_frame(self, rec, stage):
        """Candidates for every evaluation user, labelled with the target."""
        if stage == "val":
            history, day, target = self.H, self.val_day, self.val_pos
        else:
            history, day, target = self.H_test, self.test_day, self.test_pos
        frames = []
        for s in range(0, len(self.users), BATCH):
            H = history[s:s + BATCH]
            cand = rec.candidates(H, H, day[s:s + BATCH])
            cand["user"] += s
            frames.append(cand)
        cand = pd.concat(frames, ignore_index=True)
        cand["label"] = (cand["item"].to_numpy() == target[cand["user"].to_numpy()]).astype(int)
        return cand


def ranker_models(random_state=42):
    """The models compared for the ranking stage (lab program 9).

    A linear baseline, two tree ensembles built differently (bagging and
    boosting) and a soft vote over all three.
    """

    def logistic():
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))

    def forest():
        return RandomForestClassifier(
            n_estimators=300, min_samples_leaf=10, n_jobs=-1, random_state=random_state
        )

    def boosting():
        return HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, random_state=random_state
        )

    return {
        "logistic regression": logistic(),
        "random forest": forest(),
        "gradient boosting": boosting(),
        "soft voting": VotingClassifier(
            [("lr", logistic()), ("rf", forest()), ("gb", boosting())], voting="soft"
        ),
    }


def sample_negatives(cand, negatives=30, random_state=42):
    """Keep users whose target was retrieved, with a sample of their negatives."""
    rng = np.random.default_rng(random_state)
    has_pos = cand.groupby("user")["label"].transform("max") == 1
    cand = cand[has_pos].copy()
    cand["_r"] = rng.random(len(cand))
    neg = cand[cand["label"] == 0].sort_values("_r")
    neg = neg[neg.groupby("user").cumcount() < negatives]
    out = pd.concat([cand[cand["label"] == 1], neg]).drop(columns="_r")
    return out.sort_values(["user", "item"]).reset_index(drop=True)


def pool_ranks(scores, cand, n_users):
    """Rank of each user's target among their candidates; inf if not retrieved."""
    df = pd.DataFrame({"user": cand["user"].to_numpy(), "label": cand["label"].to_numpy(), "p": scores})
    pos = df[df["label"] == 1].set_index("user")["p"]
    df["pos_p"] = df["user"].map(pos)
    df = df[df["pos_p"].notna()]
    higher = (df["p"] > df["pos_p"]).groupby(df["user"]).sum()
    ties = (df["p"] == df["pos_p"]).groupby(df["user"]).sum() - 1
    ranks = np.full(n_users, np.inf)
    ranks[higher.index.to_numpy()] = (higher + ties / 2).to_numpy()
    return ranks
