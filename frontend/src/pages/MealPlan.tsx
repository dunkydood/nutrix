import { CalendarCheck, ChevronLeft, ChevronRight, Shuffle, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, localISODate, type DayLog, type Nutrients, type Plan, type Targets } from "../api";
import Photo from "../components/Photo";
import Ring from "../components/Ring";
import { useApi, useApp } from "../state";

function shiftDay(iso: string, days: number) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return localISODate(d);
}

function dayLabel(iso: string) {
  const today = localISODate();
  if (iso === today) return "Today";
  if (iso === shiftDay(today, 1)) return "Tomorrow";
  if (iso === shiftDay(today, -1)) return "Yesterday";
  return new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short" });
}

function Totals({ totals, targets }: { totals: Nutrients; targets: Targets }) {
  const items = [
    ["kcal", "kcal", targets.kcal],
    ["protein", "g protein", targets.protein],
    ["carbs", "g carbs", targets.carbs],
    ["fat", "g fat", targets.fat],
  ] as const;
  return (
    <div className="totals-inline">
      {items.map(([key, unit, target]) => {
        const value = totals[key];
        const off = Math.abs(value / target - 1) > 0.15;
        return (
          <span key={key} title={off ? "More than 15% from target" : undefined}>
            <b className={off ? "off" : ""}>{Math.round(value).toLocaleString()}</b> / {Math.round(target).toLocaleString()} {unit}
          </span>
        );
      })}
    </div>
  );
}

export default function MealPlan() {
  const { toast, refresh, openRecipe } = useApp();
  const navigate = useNavigate();
  const [days, setDays] = useState(1);
  const [useLikes, setUseLikes] = useState(true);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [seed, setSeed] = useState(0);
  const [day, setDay] = useState(localISODate());
  const log = useApi<DayLog>(`/log?day=${day}`);

  async function generate(shuffle: boolean) {
    const nextSeed = shuffle ? seed + 1 : seed;
    setBusy(true);
    try {
      const result = await api.post<Plan>("/plan", { days, use_likes: useLikes, shuffle, seed: nextSeed });
      setPlan(result);
      setSeed(nextSeed);
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function savePlan() {
    if (!plan) return;
    const meals = plan.days.flatMap((d) =>
      d.meals.map((m) => ({ day: d.date, slot: m.slot, recipe_id: m.id, servings: m.servings })),
    );
    try {
      await api.post("/plan/save", { meals });
      toast(`Saved ${meals.length} meals to your calendar`);
      setDay(plan.days[0]!.date);
      refresh();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  async function setStatus(entryId: number, status: "planned" | "eaten") {
    try {
      await api.patch(`/log/${entryId}`, { status });
      refresh();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  async function remove(entryId: number) {
    try {
      await api.del(`/log/${entryId}`);
      refresh();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Meal Plan</h1>
          <p>An optimiser picks recipes and portions that hit your calorie and macro targets, from recipes you're likely to enjoy.</p>
        </div>
      </div>

      <section className="panel">
        <div className="plan-controls">
          <div className="field">
            Days
            <div className="segmented">
              {[1, 3, 7].map((n) => (
                <button key={n} className={days === n ? "on" : ""} onClick={() => setDays(n)}>
                  {n} {n === 1 ? "day" : "days"}
                </button>
              ))}
            </div>
          </div>
          <label className="toggle">
            <input type="checkbox" checked={useLikes} onChange={(e) => setUseLikes(e.target.checked)} />
            Lean toward recipes I like
          </label>
          <div className="chips" style={{ marginLeft: "auto" }}>
            <button className="btn btn-primary" onClick={() => generate(false)} disabled={busy}>
              <Sparkles size={16} /> {busy ? "Optimising..." : "Generate plan"}
            </button>
            <button className="btn btn-ghost" onClick={() => generate(true)} disabled={busy || !plan}>
              <Shuffle size={16} /> Shuffle
            </button>
            <button className="btn btn-ghost" onClick={savePlan} disabled={busy || !plan}>
              <CalendarCheck size={16} /> Save to calendar
            </button>
          </div>
        </div>
        {busy && (
          <p className="muted" style={{ marginTop: 14 }}>
            Solving a mixed-integer program for each day. A week takes about ten seconds.
          </p>
        )}
      </section>

      {plan?.days.map((d) => (
        <section key={d.date} className="panel plan-day">
          <div className="plan-day-head">
            <h3>{dayLabel(d.date)}</h3>
            <Totals totals={d.totals} targets={plan.targets} />
          </div>
          <div className="card-grid four">
            {d.meals.map((m) => (
              <article key={`${m.slot}-${m.id}`} className="recipe-card">
                <button className="card-photo" onClick={() => openRecipe(m.id)} aria-label={`Open ${m.name}`}>
                  <Photo src={m.image} course={m.course} alt={m.name} />
                </button>
                <div className="card-body">
                  <span className="slot-label">{m.slot}</span>
                  <h3 onClick={() => openRecipe(m.id)}>{m.name}</h3>
                  <p className="card-tags">
                    {m.servings} serving{m.servings === 1 ? "" : "s"} • {m.minutes} min
                  </p>
                  <div className="macros">
                    <div><b>{m.kcal}</b><span>kcal</span></div>
                    <div><b>{Math.round(m.protein)}g</b><span>Protein</span></div>
                    <div><b>{Math.round(m.carbs)}g</b><span>Carbs</span></div>
                    <div><b>{Math.round(m.fat)}g</b><span>Fats</span></div>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}

      <section className="panel">
        <div className="plan-day-head">
          <div className="panel-title" style={{ margin: 0 }}>My meals</div>
          <div className="day-nav">
            <button className="icon-btn" onClick={() => setDay(shiftDay(day, -1))} aria-label="Previous day">
              <ChevronLeft />
            </button>
            <b>{dayLabel(day)}</b>
            <button className="icon-btn" onClick={() => setDay(shiftDay(day, 1))} aria-label="Next day">
              <ChevronRight />
            </button>
            {day !== localISODate() && (
              <button className="btn btn-ghost btn-sm" onClick={() => setDay(localISODate())}>
                Today
              </button>
            )}
          </div>
        </div>
        {log.error && <p className="error">{log.error}</p>}
        {log.data && (
          <div className="today" style={{ marginTop: 16, alignItems: "start" }}>
            <Ring value={log.data.eaten.kcal} max={log.data.targets.kcal} size={140} stroke={12}>
              <b style={{ fontSize: 24 }}>{Math.round(log.data.eaten.kcal).toLocaleString()}</b>
              <span>/ {Math.round(log.data.targets.kcal).toLocaleString()} kcal</span>
            </Ring>
            <div>
              {log.data.entries.length === 0 ? (
                <div className="callout">
                  <span>
                    Nothing planned or eaten on this day. Generate a plan above or{" "}
                    <button className="link-btn" onClick={() => navigate("/recommendations")}>
                      add a recommended meal
                    </button>
                    .
                  </span>
                </div>
              ) : (
                <div className="log-list">
                  {log.data.entries.map((e) => (
                    <div key={e.entry_id} className={`log-row${e.status === "eaten" ? " eaten" : ""}`}>
                      <Photo src={e.image} course={e.course} alt={e.name} label={false} />
                      <div>
                        <span className="slot-label">{e.slot}</span>
                        <h4 onClick={() => openRecipe(e.id)}>{e.name}</h4>
                        <p>
                          {e.servings} serving{e.servings === 1 ? "" : "s"} · {e.kcal} kcal · P {Math.round(e.protein)}g · C{" "}
                          {Math.round(e.carbs)}g · F {Math.round(e.fat)}g
                        </p>
                      </div>
                      <label className="toggle">
                        <input
                          type="checkbox"
                          checked={e.status === "eaten"}
                          onChange={(ev) => setStatus(e.entry_id, ev.target.checked ? "eaten" : "planned")}
                        />
                        Eaten
                      </label>
                      <button className="icon-btn" onClick={() => remove(e.entry_id)} aria-label={`Remove ${e.name}`}>
                        <Trash2 size={18} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              {log.data.planned.kcal > 0 && (
                <p className="planned-note">{Math.round(log.data.planned.kcal).toLocaleString()} kcal planned, not yet eaten.</p>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
