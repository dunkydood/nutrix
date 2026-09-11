import { Search } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type Card } from "../api";
import RecipeCard from "../components/RecipeCard";
import { useApp } from "../state";

interface Page {
  total: number;
  page: number;
  page_size: number;
  items: Card[];
}

const SORTS = [
  ["popular", "Most reviewed"],
  ["rating", "Top rated"],
  ["quick", "Quickest"],
  ["protein", "Highest protein"],
  ["light", "Lightest"],
] as const;

const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export default function FoodLibrary() {
  const { meta } = useApp();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  const [course, setCourse] = useState("");
  const [archetype, setArchetype] = useState("");
  const [sort, setSort] = useState("popular");
  const [personal, setPersonal] = useState(true);
  const [photosOnly, setPhotosOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<Card[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filterKey = [q, course, archetype, sort, personal, photosOnly].join("|");

  useEffect(() => setText(q), [q]);
  useEffect(() => setPage(1), [filterKey]);

  useEffect(() => {
    let alive = true;
    const search = new URLSearchParams({
      q,
      sort,
      personal: String(personal),
      photos_only: String(photosOnly),
      page: String(page),
      page_size: "24",
    });
    if (course) search.set("course", course);
    if (archetype) search.set("archetype", archetype);
    setLoading(true);
    setError(null);
    api
      .get<Page>(`/recipes?${search}`)
      .then((res) => {
        if (!alive) return;
        setTotal(res.total);
        setItems((prev) => (page === 1 ? res.items : [...prev, ...res.items]));
      })
      .catch((err: Error) => alive && setError(err.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // filterKey captures every filter value used above
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey, page]);

  function submit(e: FormEvent) {
    e.preventDefault();
    setParams(text.trim() ? { q: text.trim() } : {});
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Food Library</h1>
          <p>
            {meta ? `${meta.recipes.toLocaleString()} recipes, ${meta.with_photo.toLocaleString()} with photos. ` : ""}
            Search by recipe name or ingredient.
          </p>
        </div>
      </div>

      <section className="panel">
        <form className="filters" onSubmit={submit}>
          <label className="field grow">
            Search
            <div className="search" style={{ width: "100%" }}>
              <Search size={18} />
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Chicken, lentils, banana bread..." />
            </div>
          </label>
          <label className="field">
            Course
            <select value={course} onChange={(e) => setCourse(e.target.value)}>
              <option value="">All courses</option>
              {meta?.courses.map((c) => (
                <option key={c} value={c}>
                  {capitalise(c)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Archetype
            <select value={archetype} onChange={(e) => setArchetype(e.target.value)}>
              <option value="">All archetypes</option>
              {meta?.archetypes.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Sort
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {SORTS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button className="btn btn-primary" type="submit">
            Search
          </button>
          <div className="chips" style={{ width: "100%" }}>
            <label className="toggle">
              <input type="checkbox" checked={personal} onChange={(e) => setPersonal(e.target.checked)} />
              Match my diet and cooking-time settings
            </label>
            <label className="toggle">
              <input type="checkbox" checked={photosOnly} onChange={(e) => setPhotosOnly(e.target.checked)} />
              With photos only
            </label>
          </div>
        </form>
      </section>

      <p className="muted">
        {loading && page === 1 ? "Searching..." : `${total.toLocaleString()} recipe${total === 1 ? "" : "s"}`}
        {q && ` for “${q}”`}
      </p>
      {error && <p className="error">{error}</p>}

      <div className="card-grid">
        {items.map((card) => (
          <RecipeCard key={card.id} card={card} />
        ))}
      </div>

      {items.length < total && (
        <div className="load-more">
          <button className="btn btn-ghost" onClick={() => setPage((p) => p + 1)} disabled={loading}>
            {loading ? "Loading..." : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
