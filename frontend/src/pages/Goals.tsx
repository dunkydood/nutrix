import { Dumbbell, Scale, TrendingDown } from "lucide-react";
import { api, type ProfileInfo } from "../api";
import { useApi, useApp } from "../state";

const ICONS = { lose: TrendingDown, maintain: Scale, gain: Dumbbell } as const;

export default function Goals() {
  const { meta, toast, refresh } = useApp();
  const info = useApi<ProfileInfo>("/profile");

  async function choose(goal: string, label: string) {
    try {
      await api.put("/profile", { goal });
      toast(`Goal set to ${label}`);
      refresh();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  if (info.error && !info.data) return <p className="error">{info.error}</p>;
  if (!info.data) return <div className="skeleton" style={{ minHeight: 400 }} />;

  const { profile, targets: t, nhanes, labels } = info.data;
  const energyShare = (grams: number, kcalPerGram: number) => Math.round((grams * kcalPerGram * 100) / t.kcal);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Goals</h1>
          <p>Your goal sets the daily calorie adjustment and how energy is split between protein, carbohydrate and fat.</p>
        </div>
      </div>

      <div className="goal-options">
        {meta?.goals.map((g) => {
          const Icon = ICONS[g.value as keyof typeof ICONS];
          return (
            <button
              key={g.value}
              className={`goal-option${profile.goal === g.value ? " on" : ""}`}
              onClick={() => choose(g.value, g.label)}
              aria-pressed={profile.goal === g.value}
            >
              <Icon size={26} />
              <b>{g.label}</b>
              <span>{g.adjust ? `${g.adjust > 0 ? "+" : ""}${g.adjust} kcal per day` : "No calorie adjustment"}</span>
            </button>
          );
        })}
      </div>

      <div className="grid cols-2">
        <div className="panel">
          <div className="panel-title">Daily calories</div>
          <div className="big-number">
            {Math.round(t.kcal).toLocaleString()} <span className="muted" style={{ fontSize: 18 }}>kcal</span>
          </div>
          <table className="nutrition-table" style={{ marginTop: 18 }}>
            <tbody>
              <tr><td>Resting energy (Mifflin-St Jeor)</td><td>{Math.round(t.bmr).toLocaleString()} kcal</td></tr>
              <tr><td>Activity multiplier ({labels.activity})</td><td>× {t.pal}</td></tr>
              <tr><td>Goal adjustment ({labels.goal})</td><td>{t.adjust > 0 ? "+" : ""}{t.adjust} kcal</td></tr>
            </tbody>
          </table>
          <p className="faint" style={{ fontSize: 13, marginTop: 12 }}>
            Targets never drop below 1,200 kcal for women or 1,500 kcal for men.
          </p>
        </div>

        <div className="panel">
          <div className="panel-title">Macronutrients and limits</div>
          <table className="nutrition-table">
            <tbody>
              <tr><td>Protein</td><td>{Math.round(t.protein)} g · {energyShare(t.protein, 4)}% of energy</td></tr>
              <tr><td>Carbohydrate</td><td>{Math.round(t.carbs)} g · {energyShare(t.carbs, 4)}% of energy</td></tr>
              <tr><td>Fat</td><td>{Math.round(t.fat)} g · {energyShare(t.fat, 9)}% of energy</td></tr>
              <tr><td>Sugar, at most</td><td>{Math.round(t.sugar_limit)} g (10% of energy, WHO)</td></tr>
              <tr><td>Sodium, at most</td><td>{t.sodium_limit.toLocaleString()} mg</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Compared with real people</div>
        <p style={{ fontSize: 17 }}>
          NHANES 2017-2018 adults with your age, sex, size and activity report eating about{" "}
          <b>{nhanes.reported_kcal.toLocaleString()} kcal/day</b>.
        </p>
        <p className="muted" style={{ marginTop: 10, lineHeight: 1.6 }}>
          From a linear regression on {nhanes.n.toLocaleString()} US adults (cross-validated R² {nhanes.cv_r2.toFixed(2)}).
          Food recalls under-report: across the survey the formula averages {Math.round(nhanes.mean_formula).toLocaleString()} kcal
          against {Math.round(nhanes.mean_intake).toLocaleString()} kcal reported, so your target stays on the formula.
        </p>
      </div>
    </div>
  );
}
