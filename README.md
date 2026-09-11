# Personalised Nutrition Recommender

Recommending recipes a person will enjoy and turning them into meal plans that
hit their calorie and macronutrient targets, learned from real recipe reviews
and a national nutrition survey.

People who want to eat to a target face two questions: *how much* should I
eat, and *what* should I eat that I will actually like? This project answers
both from data. It sets a daily target, checks it against what real adults
report eating, learns taste from 220,000 Food.com reviews, and solves for a
day or week of meals that fits the target using recipes the person is likely
to enjoy.

Built for the 21CSC305P Machine Learning lab: every lab program is applied to
this single problem.

## Datasets

| Dataset | Contents | After cleaning |
|---|---|---|
| [Food.com Recipes and Interactions](https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions) (Majumder et al., EMNLP 2019), 2008-2018 cut | recipes with tags, ingredients, steps and nutrition per serving; reviews with 0-5 stars | 78,930 recipes, 221,732 reviews, 64,643 users |
| [NHANES 2017-2018](https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?BeginYear=2017) (US CDC) | measured weight and height, physical activity questionnaire, two 24-hour dietary recalls | 3,811 adults |
| [Food.com parsed scrape](https://huggingface.co/datasets/Karo8870/food.com-parsed-dataset) | photo URLs and original recipe names, joined through the recipe id in each photo URL | photos for 43,247 recipes (55%) |

Food.com stores nutrition as percent daily value. The daily values were
recovered from the data: with them, 4 kcal/g protein and carbohydrate plus
9 kcal/g fat reproduce the stated calories (median ratio 0.98). Three cleaning
rules remove 4,852 recipes (5.8%):

- calories per serving outside 20-2,500, which catches whole recipes entered
  as one serving;
- stated calories that disagree with the macronutrients by more than 30%;
- cooking time of zero or longer than a day.

NHANES keeps adults aged 18-79 who are not pregnant, whose recall was complete
and described as a usual day, and whose reported intake is plausible.

Raw files go in `data/raw/`. `src/download_data.py` fetches them all.

## How it works

1. **Targets.** Mifflin-St Jeor resting energy x activity factor, adjusted for
   the goal (lose / maintain / gain), split into protein, carbohydrate and fat.
2. **Recommendations.** Two stages, the shape used by production recommenders:
   - four candidate generators score all 78,930 recipes: popularity, trending
     (reviews in the previous 12 months), PureSVD collaborative filtering, and
     content similarity over ingredients and tags;
   - a random forest ranks the union of their top 50, using the generator
     scores, recipe features and how well each recipe matches the user's past
     choices.
3. **Meal plans.** A mixed-integer program (HiGHS via SciPy) picks one recipe
   and portion per slot per day. It minimises the gap to the calorie and macro
   targets, plus sugar over 10% of energy
   and sodium over 2,300 mg, plus a penalty for recipes the person is less
   likely to enjoy. Each slot's candidates mix the most preferred recipes with
   recipes whose macro balance suits the target, so a strong taste cannot
   push the plan off target. Weeks never repeat a dish.
4. **Course and archetype.** An SVM fills in the course of 7,266 untagged
   recipes so the planner can place them. K-means groups recipes into nine
   nutrition archetypes, which are explained by CART rules and mapped with PCA.
5. **NUTRIX app.** A React front end over a FastAPI service. It keeps one
   local profile, liked recipes and a log of planned and eaten meals in
   SQLite, so the dashboard's nutrition ring, weekly progress, weekly goal and
   insight reflect what was actually eaten.

## Layout

```
data/raw/                  Food.com CSVs and parquet, NHANES .xpt files
data/processed/            parquet caches and the app catalogue (generated)
data/user/                 nutrix.db: profile, likes and meal log (created by the API)
models/                    bundle.joblib and metrics.json (generated)
notebooks/
  nutrition_ml_lab.ipynb   all lab programs, in order
src/
  download_data.py         fetches the raw data
  recipes.py               loading, cleaning, nutrient features, course and diet tags
  energy.py                calorie targets, NHANES loading, intake regression
  course.py                SVM course classifier
  archetypes.py            K-means archetypes, CART rules, PCA map
  recommender.py           generators, leave-last-out evaluation, ensemble ranker
  planner.py               mixed-integer meal planner
  photos.py                recipe photos and original names from the parsed scrape
  build.py                 trains and evaluates everything the app uses
api/main.py                FastAPI service: models, profile, meal log
frontend/                  NUTRIX React app (Vite, TypeScript)
outputs/figures/           plots written by the notebook
outputs/lab_results.json   key numbers from the notebook
```

## Setup

```bash
py -3.12 -m venv .venv
.venv/Scripts/activate          # Windows
pip install -r requirements.txt
python src/download_data.py
cd frontend && npm install        # needs Node.js 20 or newer
```

A virtual environment is already created at `.venv` and the frontend packages
are installed.

scikit-learn is pinned to 1.9.0. On this machine Windows Smart App Control
blocks the compiled extension files of 1.9.1, and 1.9.0 is the build it already
trusts.

## Running

Train the models (about three minutes). This writes `models/` and the app
catalogue:

```bash
.venv/Scripts/python src/build.py
```

Notebook:

```bash
.venv/Scripts/python -m jupyter lab notebooks/nutrition_ml_lab.ipynb
```

App, as a single process. Build the frontend once, then the API serves it:

```bash
cd frontend && npm run build && cd ..
.venv/Scripts/python -m uvicorn api.main:app --port 8000
```

Open http://localhost:8000.

For development with hot reload, run the API and the Vite dev server in two
terminals and open http://localhost:5173 (Vite forwards `/api` to port 8000):

```bash
.venv/Scripts/python -m uvicorn api.main:app --reload --port 8000
cd frontend && npm run dev
```

Pages:

- **Dashboard**: today's calories and macros against target, a nutrition
  balance chart, an insight from your log, top recommendations with match
  scores and reasons, weekly protein and a weekly goal.
- **My Profile** and **Goals**: body measurements, activity, goal, targets and
  the NHANES comparison.
- **Meal Plan**: 1, 3 or 7-day optimised plans, saved to a calendar where
  meals are ticked off as eaten.
- **Recommendations**, **Food Library**: recipe cards with photos, likes,
  "Add to Plan", and full recipe details.
- **Analytics**: your last 30 days and the evaluation of every model.
- **Settings**: diet filters, ingredients to leave out, cooking time, clearing
  the log.

Recipe photos load from Food.com's image CDN and belong to their contributors.

## Results

Recommendation, leave-last-out on 6,453 users. Hit rate @10 is how often the
recipe the user reviewed next is in the top ten out of 78,930:

| Model | HR@10 | NDCG@10 |
|---|---|---|
| Generator: SVD | 0.53% | 0.0032 |
| Generator: trending | 0.76% | 0.0037 |
| Generator: content | 1.07% | 0.0069 |
| Generator: popularity | 1.35% | 0.0060 |
| Ranker: logistic regression | 2.01% | 0.0119 |
| Ranker: soft voting | 3.61% | 0.0221 |
| Ranker: gradient boosting | 3.69% | 0.0217 |
| **Ranker: random forest** (chosen on validation users) | **3.73%** | **0.0224** |

A random recommender would score 0.013%. Absolute numbers are low because the
data is extremely sparse: half of all recipes have one or two reviews, and 21%
of the test recipes were never reviewed in the training period at all. The
retrieval stage finds the true next recipe for 8.1% of users, which caps what
any ranker can reach.

| Other models | Result |
|---|---|
| Course SVM | 75.6% accuracy, macro F1 0.67 on 13,970 held-out recipes |
| Intake regression (NHANES) | cross-validated R² 0.16, RMSE 672 kcal; the formula scores R² -0.38 because it sits 274 kcal above reported intake on average, the known under-reporting in food recalls |
| Nutrition archetypes | k = 9 by silhouette; a depth-4 CART tree reproduces 80% of the K-means labels |
| Meal planner | across five test profiles (vegetarian, vegan weight loss, muscle gain, strong taste preferences), 3- and 7-day plans stay within 2.3% of the calorie target and 13% of each macronutrient, and a week plans in about 8 seconds |

## Lab program coverage

| Program | Method | Applied to |
|---|---|---|
| 1 | Load and view | recipes, reviews, survey |
| 2 | Summary statistics | nutrition sanity checks, cleaning rules, long tail of reviews |
| 3 | Linear regression | daily energy intake from age, sex, body size and activity |
| 4.1 | Bayesian logistic regression | P(dessert) from nutrient profile with credible intervals, via a Laplace approximation |
| 4.2 | SVM | recipe course from ingredients and nutrition |
| 5.1 | K-means | nutrition archetypes |
| 5.2 | Gaussian mixture model | taste segments of users |
| 5.3 | Hierarchical clustering | ingredients cooked together |
| 6 | PCA / truncated SVD | recipe nutrition map; latent factors of the review matrix |
| 7 | Hidden Markov Model | hidden eating phases in review histories |
| 8 | CART | archetypes as readable rules |
| 9 | Ensemble learning | random forest, gradient boosting and voting rankers |

## Limitations

- Food.com nutrition is computed from author-entered ingredients and serving
  counts, so individual recipes can be wrong even after cleaning.
- A review is a proxy for "cooked and liked". Users who cook without reviewing
  are invisible.
- The recipes and survey are both American.
- The calorie target is a population equation, not medical advice.
