import { X } from "lucide-react";
import { useState } from "react";
import { api, localISODate, suggestedSlot, type Card, type Slot, type Status } from "../api";
import { useApp } from "../state";
import Photo from "./Photo";
import useEscape from "./useEscape";

const SLOTS: Slot[] = ["breakfast", "lunch", "dinner", "snack"];

export default function AddToPlanDialog({ card, onClose }: { card: Card; onClose: () => void }) {
  const { toast, refresh } = useApp();
  const [day, setDay] = useState(localISODate());
  const [slot, setSlot] = useState<Slot>(suggestedSlot(card.course));
  const [servings, setServings] = useState(card.servings || 1);
  const [status, setStatus] = useState<Status>("planned");
  const [busy, setBusy] = useState(false);
  useEscape(onClose);

  const per = card.servings || 1;
  const scale = (value: number) => Math.round((value / per) * servings);

  async function save() {
    setBusy(true);
    try {
      await api.post("/log", { day, slot, recipe_id: card.id, servings, status });
      toast(`${card.name} added to ${slot}${status === "eaten" ? " as eaten" : ""}`);
      refresh();
      onClose();
    } catch (err) {
      toast((err as Error).message, "error");
      setBusy(false);
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={`Add ${card.name} to plan`} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <Photo src={card.image} course={card.course} alt={card.name} label={false} />
          <div>
            <h3>{card.name}</h3>
            <p className="muted">
              {scale(card.kcal)} kcal · P {scale(card.protein)}g · C {scale(card.carbs)}g · F {scale(card.fat)}g
            </p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>

        <label className="field">
          Day
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        </label>

        <div className="field">
          Meal
          <div className="segmented">
            {SLOTS.map((s) => (
              <button key={s} className={slot === s ? "on" : ""} onClick={() => setSlot(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          Servings
          <div className="stepper">
            <button onClick={() => setServings((v) => Math.max(0.5, v - 0.5))} aria-label="Fewer servings">−</button>
            <b>{servings}</b>
            <button onClick={() => setServings((v) => Math.min(4, v + 0.5))} aria-label="More servings">+</button>
          </div>
        </div>

        <div className="field">
          Status
          <div className="segmented">
            <button className={status === "planned" ? "on" : ""} onClick={() => setStatus("planned")}>
              Planned
            </button>
            <button className={status === "eaten" ? "on" : ""} onClick={() => setStatus("eaten")}>
              Already eaten
            </button>
          </div>
        </div>

        <footer>
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? "Saving..." : "Save"}
          </button>
        </footer>
      </div>
    </div>
  );
}
