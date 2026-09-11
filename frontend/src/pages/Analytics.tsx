import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Analytics as AnalyticsData, ProgressDay, Targets } from "../api";
import { useApi, useApp } from "../state";

const COLORS = ["#3ddc84", "#f4c152", "#5bb8f5", "#f87171", "#a78bfa", "#fb923c", "#2dd4bf", "#f472b6", "#a3e635"];
const tooltipStyle = { background: "#0f2018", border: "1px solid rgba(126,214,160,0.28)", borderRadius: 10 };
const axisTick = { fill: "#93aa9c", fontSize: 12 };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function MapTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload as { name: string; archetype: string };
  return (
    <div style={{ ...tooltipStyle, padding: "8px 12px" }}>
      <b>{point.name}</b>
      <div className="muted">{point.archetype}</div>
    </div>
  );
}

export default function Analytics() {
  const { openRecipe } = useApp();
  const analytics = useApi<AnalyticsData>("/analytics");
  const progress = useApi<{ targets: Targets; days: ProgressDay[] }>("/progress?days=30");
  const a = analytics.data;
  const p = progress.data;

  const logged = p?.days.filter((d) => d.logged) ?? [];
  const avg = (key: "kcal" | "protein") => (logged.length ? Math.round(logged.reduce((s, d) => s + d[key], 0) / logged.length) : 0);
  const series = p?.days.map((d) => ({ label: d.day.slice(5), kcal: Math.round(d.kcal), on: d.on_target })) ?? [];

  const models = a
    ? [
        ...Object.entries(a.generators).map(([name, m]) => ({ name: `${name} (generator)`, hr: +(m["HR@10"] * 100).toFixed(2), ranker: false })),
        ...Object.entries(a.rankers).map(([name, m]) => ({ name, hr: +(m["HR@10"] * 100).toFixed(2), ranker: true })),
      ].sort((x, y) => x.hr - y.hr)
    : [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Analytics</h1>
          <p>Your eating over the last 30 days, and how well the machine-learning models behind NUTRIX perform.</p>
        </div>
      </div>

      <section className="panel">
        <div className="panel-title">Your last 30 days</div>
        {p && (
          <>
            <div className="grid cols-4" style={{ marginBottom: 16 }}>
              <div className="stat"><b>{logged.length}</b><span>days with meals eaten</span></div>
              <div className="stat"><b>{p.days.filter((d) => d.on_target).length}</b><span>days within 10% of target</span></div>
              <div className="stat"><b>{avg("kcal").toLocaleString()}</b><span>average kcal on logged days</span></div>
              <div className="stat"><b>{avg("protein")} g</b><span>average protein on logged days</span></div>
            </div>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={series}>
                <CartesianGrid stroke="rgba(126,214,160,0.08)" vertical={false} />
                <XAxis dataKey="label" tick={axisTick} interval={3} />
                <YAxis tick={axisTick} width={48} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(126,214,160,0.06)" }} />
                <ReferenceLine y={Math.round(p.targets.kcal)} stroke="#f4c152" strokeDasharray="5 5" />
                <Bar dataKey="kcal" name="kcal eaten" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                  {series.map((d) => (
                    <Cell key={d.label} fill={d.on ? "#3ddc84" : "#2f6b4a"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <p className="faint" style={{ fontSize: 12 }}>Bright bars are days within 10% of your calorie target (dashed line).</p>
          </>
        )}
      </section>

      {analytics.error && <p className="error">{analytics.error}</p>}
      {a && (
        <>
          <div className="grid cols-2">
            <section className="panel">
              <div className="panel-title">Recommender: hit rate at 10</div>
              <p className="muted" style={{ fontSize: 14, marginBottom: 12 }}>
                How often the recipe a user reviewed next is in the top 10 of {a.data.recipes.toLocaleString()}, on{" "}
                {a.evaluation_users.toLocaleString()} users. Random guessing scores 0.013%.
              </p>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={models} layout="vertical" margin={{ left: 40 }}>
                  <CartesianGrid stroke="rgba(126,214,160,0.08)" horizontal={false} />
                  <XAxis type="number" tick={axisTick} unit="%" />
                  <YAxis type="category" dataKey="name" tick={axisTick} width={150} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(126,214,160,0.06)" }} />
                  <Bar dataKey="hr" name="HR@10 (%)" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                    {models.map((m) => (
                      <Cell key={m.name} fill={m.name === a.ranker_choice ? "#3ddc84" : m.ranker ? "#2f9e62" : "#5bb8f5"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="faint" style={{ fontSize: 12 }}>
                Chosen ranker: {a.ranker_choice}. Candidate retrieval finds the true next recipe for{" "}
                {(a.retrieval_recall.test * 100).toFixed(1)}% of users, which caps every ranker.
              </p>
            </section>

            <section className="panel">
              <div className="panel-title">Other models</div>
              <table className="nutrition-table">
                <tbody>
                  <tr><td>Course classifier (SVM) accuracy</td><td>{(a.course.accuracy * 100).toFixed(1)}%</td></tr>
                  <tr><td>Course classifier macro F1</td><td>{a.course.macro_f1.toFixed(2)}</td></tr>
                  <tr><td>Courses filled for untagged recipes</td><td>{a.course.filled_by_model.toLocaleString()}</td></tr>
                  <tr><td>Intake regression, cross-validated R²</td><td>{a.intake.cv_r2.toFixed(2)}</td></tr>
                  <tr><td>Intake regression RMSE</td><td>{Math.round(a.intake.cv_rmse)} kcal</td></tr>
                  <tr><td>Formula R² against reported intake</td><td>{a.intake.formula_r2.toFixed(2)}</td></tr>
                  <tr><td>Nutrition archetypes (K-means)</td><td>{a.k}</td></tr>
                  <tr><td>CART rules agreement with K-means</td><td>{(a.tree_fidelity * 100).toFixed(0)}%</td></tr>
                </tbody>
              </table>
              <p className="faint" style={{ fontSize: 12, marginTop: 10 }}>
                Trained on {a.data.interactions.toLocaleString()} Food.com reviews by {a.data.users.toLocaleString()} users and{" "}
                {a.data.nhanes_adults.toLocaleString()} NHANES adults.
              </p>
            </section>
          </div>

          <section className="panel">
            <div className="panel-title">Recipe nutrition map</div>
            <p className="muted" style={{ fontSize: 14, marginBottom: 8 }}>
              3,000 recipes placed by the first two principal components of their nutrient profile, coloured by archetype. Click a
              point to open the recipe.
            </p>
            <ResponsiveContainer width="100%" height={420}>
              <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
                <CartesianGrid stroke="rgba(126,214,160,0.08)" />
                <XAxis type="number" dataKey="x" name="PC1" tick={axisTick} />
                <YAxis type="number" dataKey="y" name="PC2" tick={axisTick} width={40} />
                <Tooltip content={<MapTooltip />} />
                <Legend wrapperStyle={{ fontSize: 13 }} />
                {a.archetypes.map((row, i) => {
                  const name = String(row.archetype);
                  return (
                    <Scatter
                      key={name}
                      name={name}
                      data={a.map.filter((pt) => pt.archetype === name)}
                      fill={COLORS[i % COLORS.length]}
                      fillOpacity={0.7}
                      shape="circle"
                      isAnimationActive={false}
                      onClick={(point) => {
                        const id = (point as unknown as { payload?: { id?: number } }).payload?.id;
                        if (id) openRecipe(id);
                      }}
                    />
                  );
                })}
              </ScatterChart>
            </ResponsiveContainer>
          </section>

          <section className="panel">
            <div className="panel-title">Archetype centres</div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    {Object.keys(a.archetypes[0] ?? {}).map((key) => (
                      <th key={key}>{key}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {a.archetypes.map((row, i) => (
                    <tr key={String(row.archetype)}>
                      {Object.entries(row).map(([key, value]) => (
                        <td key={key}>
                          {key === "archetype" && <span className="legend-dot" style={{ background: COLORS[i % COLORS.length] }} />}
                          {key === "share" ? `${Math.round(Number(value) * 100)}%` : String(value)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
