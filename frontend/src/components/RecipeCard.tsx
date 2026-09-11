import { Heart, Plus } from "lucide-react";
import { useState, type MouseEvent } from "react";
import { api, type Card, type RecCard } from "../api";
import { useApp } from "../state";
import Photo from "./Photo";

interface Props {
  card: Card | RecCard;
  active?: boolean;
  onSelect?: () => void;
}

export default function RecipeCard({ card, active, onSelect }: Props) {
  const { openRecipe, addToPlan, refresh, toast } = useApp();
  const [liked, setLiked] = useState(Boolean(card.liked));
  const match = "match" in card ? card.match : null;
  const because = "because" in card ? card.because : null;

  async function toggleLike(e: MouseEvent) {
    e.stopPropagation();
    try {
      if (liked) await api.del(`/likes/${card.id}`);
      else await api.post(`/likes/${card.id}`);
      setLiked(!liked);
      toast(liked ? `Removed ${card.name} from liked recipes` : `Liked ${card.name}. Recommendations will adapt.`);
      refresh();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  return (
    <article className={`recipe-card${active ? " active" : ""}`} onMouseEnter={onSelect} onFocus={onSelect}>
      <button className="card-photo" onClick={() => openRecipe(card.id)} aria-label={`Open ${card.name}`}>
        <Photo src={card.image} course={card.course} alt={card.name} />
        {match !== null && <span className="match">{match}% Match</span>}
      </button>
      <button className={`like${liked ? " on" : ""}`} onClick={toggleLike} aria-pressed={liked} aria-label={liked ? "Unlike" : "Like"}>
        <Heart size={16} fill={liked ? "currentColor" : "none"} />
      </button>
      <div className="card-body">
        <h3 onClick={() => openRecipe(card.id)}>{card.name}</h3>
        <p className="card-tags">{card.tags.join(" • ")}</p>
        {because && <p className="card-because">Because you liked {because}</p>}
        <div className="macros">
          <div>
            <b>{card.kcal}</b>
            <span>kcal</span>
          </div>
          <div>
            <b>{Math.round(card.protein)}g</b>
            <span>Protein</span>
          </div>
          <div>
            <b>{Math.round(card.carbs)}g</b>
            <span>Carbs</span>
          </div>
          <div>
            <b>{Math.round(card.fat)}g</b>
            <span>Fats</span>
          </div>
        </div>
        <button className="btn btn-primary btn-block" onClick={() => addToPlan(card)}>
          <Plus size={16} /> Add to Plan
        </button>
      </div>
    </article>
  );
}
