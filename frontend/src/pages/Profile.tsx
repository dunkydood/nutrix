import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type Card, type Profile as ProfileData, type ProfileInfo } from "../api";
import RecipeCard from "../components/RecipeCard";
import { useApi, useApp } from "../state";

export default function Profile() {
  const { meta, toast, refresh } = useApp();
  const info = useApi<ProfileInfo>("/profile");
  const likes = useApi<{ items: Card[] }>("/likes");
  const [form, setForm] = useState<ProfileData | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (info.data) setForm(info.data.profile);
  }, [info.data]);

  if (info.error && !form) return <p className="error">{info.error}</p>;
  if (!form) return <div className="skeleton" style={{ minHeight: 400 }} />;

  const set = <K extends keyof ProfileData>(key: K, value: ProfileData[K]) => setForm({ ...form, [key]: value });

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    try {
      await api.put("/profile", {
        name: form.name.trim(),
        sex: form.sex,
        age: form.age,
        height_cm: form.height_cm,
        weight_kg: form.weight_kg,
        activity: form.activity,
      });
      toast("Profile saved");
      refresh();
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  const t = info.data?.targets;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>My Profile</h1>
          <p>Used to calculate your calorie and macro targets. Everything stays on this computer.</p>
        </div>
      </div>

      <div className="grid cols-2">
        <form className="panel" onSubmit={save}>
          <div className="panel-title">About you</div>
          <div className="form-grid">
            <label className="field">
              Name
              <input value={form.name} maxLength={40} placeholder="Your name" onChange={(e) => set("name", e.target.value)} />
            </label>
            <label className="field">
              Sex
              <select value={form.sex} onChange={(e) => set("sex", e.target.value as ProfileData["sex"])}>
                <option value="female">Female</option>
                <option value="male">Male</option>
              </select>
            </label>
            <label className="field">
              Age
              <input type="number" min={18} max={79} value={form.age} onChange={(e) => set("age", Number(e.target.value))} />
            </label>
            <label className="field">
              Height (cm)
              <input type="number" min={130} max={220} value={form.height_cm} onChange={(e) => set("height_cm", Number(e.target.value))} />
            </label>
            <label className="field">
              Weight (kg)
              <input type="number" min={35} max={250} step={0.1} value={form.weight_kg} onChange={(e) => set("weight_kg", Number(e.target.value))} />
            </label>
            <label className="field">
              Activity
              <select value={form.activity} onChange={(e) => set("activity", e.target.value)}>
                {meta?.activity.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="faint" style={{ fontSize: 13, marginTop: 10 }}>
            {meta?.activity.find((a) => a.value === form.activity)?.help}
          </p>
          <button className="btn btn-primary" style={{ marginTop: 18 }} disabled={saving}>
            {saving ? "Saving..." : "Save profile"}
          </button>
        </form>

        <div className="panel">
          <div className="panel-title">Your daily targets</div>
          {t && (
            <div className="grid cols-2">
              <div className="stat"><b>{Math.round(t.kcal).toLocaleString()}</b><span>kcal per day</span></div>
              <div className="stat"><b>{Math.round(t.bmr).toLocaleString()}</b><span>kcal resting energy</span></div>
              <div className="stat"><b>{Math.round(t.protein)} g</b><span>protein</span></div>
              <div className="stat"><b>{Math.round(t.carbs)} g</b><span>carbohydrate</span></div>
              <div className="stat"><b>{Math.round(t.fat)} g</b><span>fat</span></div>
              <div className="stat"><b>{info.data?.labels.goal}</b><span>goal</span></div>
            </div>
          )}
          <p className="muted" style={{ marginTop: 16 }}>
            Change your goal on the <Link to="/goals">Goals</Link> page.
          </p>
        </div>
      </div>

      <section>
        <div className="section-head">
          <div>
            <h2>Recipes you like</h2>
            <p>These drive your recommendations and meal plans.</p>
          </div>
        </div>
        {likes.data?.items.length ? (
          <div className="card-grid">
            {likes.data.items.map((card) => (
              <RecipeCard key={card.id} card={{ ...card, liked: true }} />
            ))}
          </div>
        ) : (
          <div className="callout">
            <span>
              No liked recipes yet. Tap the heart on any recipe in the <Link to="/food-library">Food Library</Link>.
            </span>
          </div>
        )}
      </section>
    </div>
  );
}
