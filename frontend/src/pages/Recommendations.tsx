import { ArrowRight, BrainCircuit, CheckCircle2, Circle, Heart } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { RecCard } from "../api";
import RecipeCard from "../components/RecipeCard";
import { useApi } from "../state";

const COURSES = ["all", "breakfast", "main", "side", "snack", "dessert", "beverage"];

export default function Recommendations() {
  const [course, setCourse] = useState("all");
  const [selected, setSelected] = useState(0);
  const path = `/recommendations?n=24${course === "all" ? "" : `&course=${course}`}`;
  const { data, error, loading } = useApi<{ items: RecCard[]; liked: number }>(path);
  const chosen = data?.items[selected] ?? data?.items[0];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Recommendations</h1>
          <p>Ranked by a recommender trained on 221,732 Food.com reviews, then matched to your daily targets.</p>
        </div>
      </div>

      {data && data.liked === 0 && (
        <div className="callout">
          <Heart size={22} />
          <span>
            You haven't liked any recipes yet, so these are well-rated popular picks.{" "}
            <Link to="/food-library">Like a few in the Food Library</Link> to personalise them.
          </span>
        </div>
      )}

      <div className="chips">
        {COURSES.map((c) => (
          <button
            key={c}
            className={`chip${course === c ? " on" : ""}`}
            style={{ textTransform: "capitalize" }}
            onClick={() => {
              setCourse(c);
              setSelected(0);
            }}
          >
            {c}
          </button>
        ))}
      </div>

      <div className="recs-row">
        <div>
          {error && <p className="error">{error}</p>}
          {loading && !data && (
            <div className="card-grid">
              {Array.from({ length: 8 }, (_, i) => (
                <div key={i} className="skeleton" style={{ minHeight: 330 }} />
              ))}
            </div>
          )}
          {data &&
            (data.items.length ? (
              <div className="card-grid">
                {data.items.map((card, i) => (
                  <RecipeCard key={card.id} card={card} active={i === selected} onSelect={() => setSelected(i)} />
                ))}
              </div>
            ) : (
              <div className="callout">No recipes in this course match your filters.</div>
            ))}
        </div>

        <aside className="panel why" style={{ alignSelf: "start", position: "sticky", top: 18 }}>
          <div className="panel-title" style={{ fontSize: 17 }}>Why this recommendation?</div>
          {chosen ? (
            <>
              <p className="why-for">
                {chosen.name} · {chosen.match}% match
              </p>
              <ul>
                {chosen.reasons.map((r) => (
                  <li key={r.text} className={r.ok ? "" : "no"}>
                    {r.ok ? <CheckCircle2 size={20} /> : <Circle size={20} />} {r.text}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted">Hover a recipe to see why it was picked.</p>
          )}
          <div className="powered">
            <BrainCircuit size={34} strokeWidth={1.4} />
            <div>
              <b>How match works</b>
              Half is how strongly the ranker expects you to cook it, half is how well it fits one meal of your daily targets.
            </div>
          </div>
          <Link to="/food-library" className="link-btn" style={{ marginTop: 16 }}>
            Browse all recipes <ArrowRight size={16} />
          </Link>
        </aside>
      </div>
    </div>
  );
}
