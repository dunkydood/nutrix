import {
  Activity,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Circle,
  Dumbbell,
  Leaf,
  Lightbulb,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from "recharts";
import type { Dashboard as DashboardData } from "../api";
import MacroBar from "../components/MacroBar";
import RecipeCard from "../components/RecipeCard";
import Ring from "../components/Ring";
import { useApi } from "../state";

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { data, error } = useApi<DashboardData>("/dashboard");
  const [selected, setSelected] = useState(0);

  if (error && !data) return <p className="error">Could not load the dashboard: {error}</p>;
  if (!data) return <DashboardSkeleton />;

  const t = data.targets;
  const { eaten, planned } = data.today;
  const pct = Math.round((eaten.kcal / t.kcal) * 100);
  const chosen = data.recommendations[selected] ?? data.recommendations[0];
  const goal = data.weekly_goal;
  const maxProtein = Math.max(t.protein, ...data.week.map((w) => w.protein));
  const balance = data.balance.map((b) => ({ ...b, intake: Math.min(b.intake, 150) }));
  const bannerImage = data.recommendations.slice(1).find((r) => r.image)?.image ?? data.hero_image;

  return (
    <div className="page">
      <section className="hero">
        <div>
          <h1>
            {greeting()}
            {data.profile.name ? `, ${data.profile.name}` : ""} 👋
          </h1>
          <h2>Your nutrition journey, powered by machine learning.</h2>
          <p>Personalized meal recommendations for a healthier, stronger you.</p>
          <div className="chips">
            <span className="chip"><Dumbbell size={18} /> {data.labels.goal}</span>
            <span className="chip"><Activity size={18} /> {data.labels.activity}</span>
            <span className="chip"><Leaf size={18} /> {data.labels.diet}</span>
            <span className="chip"><ShieldCheck size={18} /> {data.labels.allergies}</span>
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          {data.hero_image && <img src={data.hero_image} alt="" />}
          <div className="hero-script">
            Fuel
            <br />
            a better
            <br />
            tomorrow
          </div>
        </div>
      </section>

      <section className="dash-top">
        <div className="panel">
          <div className="panel-title">Today's Nutrition</div>
          <div className="today">
            <Ring value={eaten.kcal} max={t.kcal} size={156} stroke={13}>
              <b>{Math.round(eaten.kcal).toLocaleString()}</b>
              <span>/ {Math.round(t.kcal).toLocaleString()} kcal</span>
              <em>{pct}%</em>
            </Ring>
            <div>
              <MacroBar label="Protein" value={eaten.protein} target={t.protein} color="#3ddc84" />
              <MacroBar label="Carbohydrates" value={eaten.carbs} target={t.carbs} color="#f4c152" />
              <MacroBar label="Fats" value={eaten.fat} target={t.fat} color="#5bb8f5" />
              {planned.kcal > 0 && (
                <p className="planned-note">+{Math.round(planned.kcal).toLocaleString()} kcal planned, not yet eaten</p>
              )}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">Nutrition Balance</div>
          <ResponsiveContainer width="100%" height={215}>
            <RadarChart data={balance} outerRadius="68%">
              <PolarGrid stroke="rgba(160, 220, 180, 0.2)" />
              <PolarAngleAxis dataKey="axis" tick={{ fill: "#cfdcd4", fontSize: 12 }} />
              <PolarRadiusAxis domain={[0, 150]} tick={false} axisLine={false} />
              <Radar name="Recommended" dataKey="target" stroke="#93aa9c" fill="#93aa9c" fillOpacity={0.05} isAnimationActive={false} />
              <Radar name="Your Intake" dataKey="intake" stroke="#3ddc84" fill="#3ddc84" fillOpacity={0.28} dot isAnimationActive={false} />
              <Legend wrapperStyle={{ fontSize: 13 }} />
            </RadarChart>
          </ResponsiveContainer>
          <p className="faint" style={{ fontSize: 12 }}>
            Percent of today's target eaten. Sugar and sodium are measured against their upper limits.
          </p>
        </div>

        <div className="panel insight">
          <div>
            <div className="panel-title">
              <Sparkles size={22} /> Insight
            </div>
            <div className="insight-body">
              <Lightbulb size={26} />
              <p>{data.insight.text}</p>
            </div>
          </div>
          <button className="btn btn-primary btn-block" onClick={() => navigate(`/${data.insight.action}`)}>
            {data.insight.action === "meal-plan" ? "Open Meal Plan" : "View Recommendations"} <ArrowRight size={18} />
          </button>
        </div>
      </section>

      <section className="recs-row">
        <div>
          <div className="section-head">
            <div>
              <h2>Top Recommendations for You</h2>
              <p>
                {data.liked
                  ? `Based on your goals, targets and ${data.liked} liked recipe${data.liked > 1 ? "s" : ""}`
                  : "Based on your goals and preferences. Like recipes to personalise further."}
              </p>
            </div>
            <Link to="/recommendations" className="link-btn">
              View All <ArrowRight size={16} />
            </Link>
          </div>
          {data.recommendations.length ? (
            <div className="card-grid four">
              {data.recommendations.map((card, i) => (
                <RecipeCard key={card.id} card={card} active={i === selected} onSelect={() => setSelected(i)} />
              ))}
            </div>
          ) : (
            <div className="callout">No recipes match your current filters. Loosen them in Settings.</div>
          )}
        </div>
        <aside className="panel why">
          <div className="panel-title" style={{ fontSize: 17 }}>Why this recommendation?</div>
          {chosen && <p className="why-for">{chosen.name}</p>}
          <ul>
            {chosen?.reasons.map((r) => (
              <li key={r.text} className={r.ok ? "" : "no"}>
                {r.ok ? <CheckCircle2 size={20} /> : <Circle size={20} />} {r.text}
              </li>
            ))}
          </ul>
          <div className="powered">
            <BrainCircuit size={34} strokeWidth={1.4} />
            <div>
              <b>Powered by Machine Learning</b>
              Random forest ranker over collaborative, content, popularity and trending signals.
            </div>
          </div>
        </aside>
      </section>

      <section className="dash-bottom">
        <div className="panel">
          <div className="panel-title">
            <TrendingUp size={20} /> Your Progress
          </div>
          <div className="progress-card">
            <div className="trend">
              <TrendingUp size={26} />
              {data.protein_change === null ? (
                <div>
                  <b>—</b>
                  <span>Log meals this week and last week to see your protein trend</span>
                </div>
              ) : (
                <div>
                  <b>
                    {data.protein_change > 0 ? "+" : ""}
                    {data.protein_change}%
                  </b>
                  <span>Average protein intake this week</span>
                </div>
              )}
            </div>
            <div className="week-bars" aria-label="Protein eaten each day this week">
              {data.week.map((w) => (
                <div
                  key={w.date}
                  className={`week-bar${w.future ? " future" : ""}${w.protein === 0 ? " empty" : ""}`}
                  title={`${w.day}: ${Math.round(w.protein)} g protein`}
                >
                  <i style={{ height: `${Math.max(4, (w.protein / maxProtein) * 76)}px` }} />
                  {w.day}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">
            <Target size={20} /> Weekly Goal
          </div>
          <p className="muted" style={{ fontSize: 14 }}>
            Days eaten within {Math.round(goal.band * 100)}% of your calorie target
          </p>
          <div style={{ display: "flex", justifyContent: "space-between", margin: "18px 0 10px" }}>
            <span>{goal.days_on_target >= 4 ? "Great consistency!" : "Stay consistent!"}</span>
            <b>
              {goal.days_on_target} / {goal.of} days
            </b>
          </div>
          <div className="goal-track">
            <div className="goal-fill" style={{ width: `${(goal.days_on_target / goal.of) * 100}%` }} />
          </div>
        </div>

        <div className="panel banner">
          {bannerImage && <img src={bannerImage} alt="" />}
          <div className="banner-quote">
            Discipline
            <br />
            today, a healthier
            <br />
            tomorrow.
          </div>
          <div className="banner-brand">
            <img src="/leaf.svg" alt="" />
            <div>
              <strong>NUTRIX</strong>
              <span>
                More than food.
                <br />A better you.
              </span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="page" aria-busy="true">
      <div className="skeleton" style={{ minHeight: 190 }} />
      <div className="dash-top">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skeleton" style={{ minHeight: 250 }} />
        ))}
      </div>
      <div className="skeleton" style={{ minHeight: 330 }} />
    </div>
  );
}
