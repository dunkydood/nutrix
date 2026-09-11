import { Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type ProfileInfo } from "../api";
import { useApi, useApp } from "../state";

export default function Settings() {
  const { meta, toast, refresh } = useApp();
  const info = useApi<ProfileInfo>("/profile");
  const [diets, setDiets] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [maxMinutes, setMaxMinutes] = useState(120);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!info.data) return;
    setDiets(info.data.profile.diets);
    setExcluded(info.data.profile.excluded);
    setMaxMinutes(info.data.profile.max_minutes);
  }, [info.data]);

  function toggleDiet(value: string) {
    setDiets((all) => (all.includes(value) ? all.filter((d) => d !== value) : [...all, value]));
  }

  function addTerm() {
    const term = draft.trim().toLowerCase();
    if (term && !excluded.includes(term)) setExcluded([...excluded, term]);
    setDraft("");
  }

  async function save() {
    setSaving(true);
    try {
      await api.put("/profile", { diets, excluded, max_minutes: maxMinutes });
      toast("Food preferences saved");
      refresh();
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  async function clearLog() {
    if (!window.confirm("Delete every planned and eaten meal? This cannot be undone.")) return;
    try {
      await api.del("/log");
      toast("Meal log cleared");
      refresh();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Settings</h1>
          <p>Food preferences apply to recommendations, the food library and meal plans.</p>
        </div>
      </div>

      <section className="panel">
        <div className="panel-title">Diet</div>
        <div className="chips">
          {meta?.diets.map((d) => (
            <button key={d.value} className={`chip${diets.includes(d.value) ? " on" : ""}`} aria-pressed={diets.includes(d.value)} onClick={() => toggleDiet(d.value)}>
              {d.label}
            </button>
          ))}
        </div>
        <p className="faint" style={{ fontSize: 13, marginTop: 8 }}>Based on the tags recipe authors gave on Food.com.</p>

        <div className="panel-title" style={{ marginTop: 24 }}>Leave out ingredients</div>
        <div className="tag-input">
          {excluded.map((term) => (
            <span key={term} className="tag">
              {term}
              <button onClick={() => setExcluded(excluded.filter((x) => x !== term))} aria-label={`Stop excluding ${term}`}>
                <X size={14} />
              </button>
            </span>
          ))}
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === ",") {
                e.preventDefault();
                addTerm();
              }
            }}
            onBlur={addTerm}
            placeholder="Type an ingredient and press Enter, e.g. peanut"
            aria-label="Ingredient to leave out"
          />
        </div>
        <p className="faint" style={{ fontSize: 13, marginTop: 8 }}>Recipes with any ingredient containing these words are hidden.</p>

        <div className="panel-title" style={{ marginTop: 24 }}>Maximum cooking time: {maxMinutes} min</div>
        <input
          type="range"
          min={10}
          max={240}
          step={10}
          value={maxMinutes}
          onChange={(e) => setMaxMinutes(Number(e.target.value))}
          style={{ width: "min(440px, 100%)" }}
          aria-label="Maximum cooking time in minutes"
        />

        <div style={{ marginTop: 22 }}>
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving..." : "Save preferences"}
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-title">Your data</div>
        <p className="muted">Your profile, liked recipes and meal log are stored locally in data/user/nutrix.db.</p>
        <button className="btn btn-danger" style={{ marginTop: 14 }} onClick={clearLog}>
          <Trash2 size={16} /> Clear meal log
        </button>
      </section>

      <section className="panel">
        <div className="panel-title">About the data</div>
        <p className="muted" style={{ lineHeight: 1.7 }}>
          Recipes and reviews come from Food.com Recipes and Interactions (Majumder et al., 2019). Recipe photos load from Food.com and
          belong to their contributors. Intake comparisons use NHANES 2017-2018 from the US CDC. Nutrition is per serving as published
          on Food.com. NUTRIX is a university project, not medical or dietetic advice.
        </p>
      </section>
    </div>
  );
}
