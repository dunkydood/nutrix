import { Clock, Heart, Plus, Star, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type RecipeDetail } from "../api";
import { useApi, useApp } from "../state";
import Photo from "./Photo";
import useEscape from "./useEscape";

export default function RecipeModal({ id, onClose }: { id: number; onClose: () => void }) {
  const { openRecipe, addToPlan, refresh, toast } = useApp();
  const { data, error, loading } = useApi<RecipeDetail>(`/recipes/${id}`);
  const [liked, setLiked] = useState(false);
  useEscape(onClose);

  useEffect(() => {
    if (data) setLiked(data.liked);
  }, [data]);

  async function toggleLike() {
    if (!data) return;
    try {
      if (liked) await api.del(`/likes/${data.id}`);
      else await api.post(`/likes/${data.id}`);
      setLiked(!liked);
      toast(liked ? "Removed from liked recipes" : "Liked. Recommendations will adapt.");
      refresh();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={data?.name ?? "Recipe"} onClick={(e) => e.stopPropagation()}>
        <div className="modal-hero">
          {data ? <Photo src={data.photo ?? data.image} course={data.course} alt={data.name} /> : <div className="skeleton" style={{ height: "100%" }} />}
          <button className="icon-btn modal-close" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>
        {error && <p className="error" style={{ padding: 28 }}>{error}</p>}
        {loading && !data && <p className="muted" style={{ padding: 28 }}>Loading recipe...</p>}
        {data && (
          <div className="modal-content">
            <div>
              <h2>{data.name}</h2>
              <div className="modal-meta">
                <span style={{ textTransform: "capitalize" }}>{data.course ?? "Uncategorised"}</span>
                <span>{data.archetype}</span>
                <span>
                  <Clock size={15} /> {data.minutes} min
                </span>
                {data.rating !== null && (
                  <span>
                    <Star size={15} /> {data.rating.toFixed(1)} ({data.reviews} reviews)
                  </span>
                )}
              </div>
              <div className="chips">
                {data.tags.map((t) => (
                  <span key={t} className="chip">{t}</span>
                ))}
              </div>
              {data.description && <p className="muted" style={{ marginTop: 16, lineHeight: 1.6 }}>{data.description}</p>}

              <h4>Ingredients</h4>
              <ul className="ingredients">
                {data.ingredients.map((ing) => (
                  <li key={ing}>{ing}</li>
                ))}
              </ul>

              <h4>Steps</h4>
              <ol className="steps">
                {data.steps.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ol>
            </div>

            <aside>
              <div className="chips" style={{ marginTop: 50 }}>
                <button className="btn btn-primary" onClick={() => addToPlan(data)}>
                  <Plus size={16} /> Add to Plan
                </button>
                <button className={`btn btn-ghost${liked ? " on" : ""}`} onClick={toggleLike} aria-pressed={liked}>
                  <Heart size={16} fill={liked ? "#fb7185" : "none"} color={liked ? "#fb7185" : "currentColor"} /> {liked ? "Liked" : "Like"}
                </button>
              </div>

              <h4>Nutrition per serving</h4>
              <table className="nutrition-table">
                <tbody>
                  <tr><td>Calories</td><td>{data.kcal} kcal</td></tr>
                  <tr><td>Protein</td><td>{data.protein} g</td></tr>
                  <tr><td>Carbohydrate</td><td>{data.carbs} g</td></tr>
                  <tr><td>Sugar</td><td>{data.sugar} g</td></tr>
                  <tr><td>Fat</td><td>{data.fat} g</td></tr>
                  <tr><td>Saturated fat</td><td>{data.sat_fat} g</td></tr>
                  <tr><td>Sodium</td><td>{data.sodium} mg</td></tr>
                </tbody>
              </table>
              {data.course_source === "model" && (
                <p className="credit">Course predicted by the SVM course classifier.</p>
              )}

              {data.similar.length > 0 && (
                <>
                  <h4>Similar recipes</h4>
                  <div className="similar">
                    {data.similar.map((s) => (
                      <button key={s.id} className="mini-card" onClick={() => openRecipe(s.id)}>
                        <Photo src={s.image} course={s.course} alt={s.name} label={false} />
                        <span>{s.name}</span>
                      </button>
                    ))}
                  </div>
                </>
              )}
              {(data.photo || data.image) && <p className="credit">Photo: Food.com community</p>}
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
