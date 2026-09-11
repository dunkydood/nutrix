import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Card, type Meta } from "./api";
import AddToPlanDialog from "./components/AddToPlanDialog";
import RecipeModal from "./components/RecipeModal";

interface Toast {
  id: number;
  text: string;
  tone: "ok" | "error";
}

interface AppState {
  meta: Meta | null;
  // Bumped after any change to the log, likes or profile so pages refetch.
  version: number;
  refresh: () => void;
  toast: (text: string, tone?: "ok" | "error") => void;
  openRecipe: (id: number) => void;
  addToPlan: (card: Card) => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [version, setVersion] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [recipeId, setRecipeId] = useState<number | null>(null);
  const [planCard, setPlanCard] = useState<Card | null>(null);

  useEffect(() => {
    api.get<Meta>("/meta").then(setMeta).catch(() => setMeta(null));
    // ?recipe=<id> opens that recipe, so recipe links can be shared.
    const linked = Number(new URLSearchParams(window.location.search).get("recipe"));
    if (linked) setRecipeId(linked);
  }, []);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  const toast = useCallback((text: string, tone: "ok" | "error" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((all) => [...all, { id, text, tone }]);
    window.setTimeout(() => setToasts((all) => all.filter((t) => t.id !== id)), 3500);
  }, []);

  const value: AppState = {
    meta,
    version,
    refresh,
    toast,
    openRecipe: setRecipeId,
    addToPlan: setPlanCard,
  };

  return (
    <Ctx.Provider value={value}>
      {children}
      {recipeId !== null && <RecipeModal id={recipeId} onClose={() => setRecipeId(null)} />}
      {planCard && <AddToPlanDialog card={planCard} onClose={() => setPlanCard(null)} />}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useApp() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}

export function useApi<T>(path: string | null) {
  const { version } = useApp();
  const [tick, setTick] = useState(0);
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({
    data: null,
    error: null,
    loading: path !== null,
  });

  useEffect(() => {
    if (path === null) return;
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    api
      .get<T>(path)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((err: Error) => alive && setState((s) => ({ data: s.data, error: err.message, loading: false })));
    return () => {
      alive = false;
    };
  }, [path, version, tick]);

  return { ...state, reload: () => setTick((t) => t + 1) };
}
