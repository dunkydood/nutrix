// Typed client for the NUTRIX API (api/main.py).

export type Slot = "breakfast" | "lunch" | "dinner" | "snack";
export type Status = "planned" | "eaten";

export interface Nutrients {
  kcal: number;
  protein: number;
  carbs: number;
  fat: number;
  sugar: number;
  sodium: number;
}

export interface Card extends Nutrients {
  id: number;
  name: string;
  course: string | null;
  archetype: string;
  minutes: number;
  image: string | null;
  servings: number;
  rating: number | null;
  reviews: number;
  tags: string[];
  liked?: boolean;
}

export interface Reason {
  text: string;
  ok: boolean;
}

export interface RecCard extends Card {
  match: number;
  because: string | null;
  reasons: Reason[];
}

export interface Targets {
  bmr: number;
  kcal: number;
  protein: number;
  carbs: number;
  fat: number;
  sugar_limit: number;
  sodium_limit: number;
  split: { protein: number; carbs: number; fat: number };
  pal: number;
  adjust: number;
}

export interface Profile {
  name: string;
  sex: "female" | "male";
  age: number;
  height_cm: number;
  weight_kg: number;
  activity: string;
  goal: string;
  diets: string[];
  excluded: string[];
  max_minutes: number;
}

export interface Labels {
  goal: string;
  activity: string;
  diet: string;
  allergies: string;
}

export interface ProfileInfo {
  profile: Profile;
  targets: Targets;
  labels: Labels;
  nhanes: { reported_kcal: number; cv_r2: number; n: number; mean_formula: number; mean_intake: number };
}

export interface LogEntry extends Card {
  entry_id: number;
  day: string;
  slot: Slot;
  status: Status;
}

export interface DayLog {
  day: string;
  entries: LogEntry[];
  eaten: Nutrients;
  planned: Nutrients;
  targets: Targets;
}

export interface WeekDay {
  day: string;
  date: string;
  protein: number;
  kcal: number;
  future: boolean;
  on_target: boolean;
}

export interface Dashboard {
  profile: Profile;
  labels: Labels;
  targets: Targets;
  today: { date: string; eaten: Nutrients; planned: Nutrients };
  balance: { axis: string; intake: number; target: number }[];
  insight: { text: string; action: string };
  recommendations: RecCard[];
  week: WeekDay[];
  protein_change: number | null;
  weekly_goal: { days_on_target: number; of: number; band: number };
  hero_image: string | null;
  liked: number;
}

export interface PlanMeal extends Card {
  slot: Slot;
}

export interface PlanDay {
  date: string;
  meals: PlanMeal[];
  totals: Nutrients;
}

export interface Plan {
  targets: Targets;
  days: PlanDay[];
}

export interface RecipeDetail extends Card {
  photo: string | null;
  description: string | null;
  ingredients: string[];
  steps: string[];
  sat_fat: number;
  course_source: string | null;
  liked: boolean;
  similar: Card[];
}

export interface Option {
  value: string;
  label: string;
  help?: string;
  adjust?: number;
}

export interface Meta {
  activity: Option[];
  goals: Option[];
  diets: Option[];
  courses: string[];
  archetypes: string[];
  slots: Slot[];
  recipes: number;
  with_photo: number;
}

export interface Metric {
  "HR@10": number;
  "NDCG@10": number;
  MRR: number;
}

export interface ProgressDay extends Nutrients {
  day: string;
  logged: boolean;
  on_target: boolean;
}

export interface Analytics {
  data: { recipes: number; interactions: number; users: number; nhanes_adults: number };
  evaluation_users: number;
  generators: Record<string, Metric>;
  rankers: Record<string, Metric>;
  ranker_choice: string;
  retrieval_recall: { val: number; test: number };
  course: { accuracy: number; macro_f1: number; n_test: number; filled_by_model: number; unassigned: number };
  intake: { n: number; cv_r2: number; cv_rmse: number; formula_r2: number; formula_rmse: number; mean_intake: number; mean_formula: number };
  archetypes: Record<string, number | string>[];
  tree_fidelity: number;
  k: number;
  map: { x: number; y: number; archetype: string; name: string; id: number }[];
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      // keep the status text
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export function localISODate(d = new Date()): string {
  const offset = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - offset).toISOString().slice(0, 10);
}

export function suggestedSlot(course: string | null): Slot {
  if (course === "breakfast") return "breakfast";
  if (course === "snack" || course === "dessert" || course === "beverage") return "snack";
  return new Date().getHours() < 15 ? "lunch" : "dinner";
}
