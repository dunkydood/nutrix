"""Exercise every NUTRIX API endpoint against a throwaway database.

    .venv/Scripts/python tests/check_api.py

Each call is checked for its expected status code and a basic property of
the response. Results go to outputs/app/api_checks.json, which the project
report reads. The user's real database is never touched.
"""

import json
import os
import sys
import tempfile
import time
import warnings
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["NUTRIX_DB"] = str(Path(tempfile.mkdtemp()) / "check.db")
warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

import api.main as nutrix  # noqa: E402

client = TestClient(nutrix.app)
checks = []


def check(label, method, path, expect=200, test=None, **kwargs):
    start = time.perf_counter()
    response = client.request(method, path, **kwargs)
    ms = (time.perf_counter() - start) * 1000
    body = response.json()
    ok = response.status_code == expect and (test is None or bool(test(body)))
    checks.append({
        "label": label,
        "method": method,
        "path": path.split("?")[0],
        "status": response.status_code,
        "expected": expect,
        "ms": round(ms),
        "ok": ok,
    })
    print(f"{'PASS' if ok else 'FAIL'}  {method:6s} {path:48s} {response.status_code}  {ms:6.0f} ms  {label}")
    return body


meta = check("catalogue metadata", "GET", "/api/meta", test=lambda b: b["recipes"] > 70000)
check("default profile and targets", "GET", "/api/profile", test=lambda b: b["targets"]["kcal"] > 1000)
check(
    "update profile",
    "PUT",
    "/api/profile",
    json={"name": "Test", "sex": "male", "age": 24, "height_cm": 176, "weight_kg": 72, "activity": "moderate", "goal": "gain"},
    test=lambda b: b["profile"]["goal"] == "gain",
)
check("reject unknown diet", "PUT", "/api/profile", expect=422, json={"diets": ["paleo"]})
check("reject out-of-range age", "PUT", "/api/profile", expect=422, json={"age": 12})
check("recommendations without likes", "GET", "/api/recommendations?n=8", test=lambda b: len(b["items"]) == 8)
search = check("search by ingredient", "GET", "/api/recipes?q=lentil&page_size=6", test=lambda b: b["total"] > 0)
recipe_id = search["items"][0]["id"]
check("recipe detail", "GET", f"/api/recipes/{recipe_id}", test=lambda b: len(b["ingredients"]) > 0)
check("missing recipe", "GET", "/api/recipes/999999999", expect=404)
check("like a recipe", "POST", f"/api/likes/{recipe_id}", test=lambda b: b["liked"])
check("list likes", "GET", "/api/likes", test=lambda b: len(b["items"]) == 1)
check("recommendations after a like", "GET", "/api/recommendations?n=8", test=lambda b: b["liked"] == 1)
check(
    "log an eaten meal",
    "POST",
    "/api/log",
    json={"slot": "lunch", "recipe_id": recipe_id, "servings": 1.5, "status": "eaten"},
    test=lambda b: b["eaten"]["kcal"] > 0,
)
log = check("read today's log", "GET", f"/api/log?day={date.today().isoformat()}", test=lambda b: len(b["entries"]) == 1)
entry = log["entries"][0]["entry_id"]
check("change servings", "PATCH", f"/api/log/{entry}", json={"servings": 1.0}, test=lambda b: b["entries"][0]["servings"] == 1.0)
check("reject invalid slot", "POST", "/api/log", expect=422, json={"slot": "brunch", "recipe_id": recipe_id})
dash = check("dashboard", "GET", "/api/dashboard", test=lambda b: len(b["recommendations"]) == 4 and b["insight"]["text"])
plan = check("generate a 3-day plan", "POST", "/api/plan", json={"days": 3}, test=lambda b: len(b["days"]) == 3)
meals = [{"day": d["date"], "slot": m["slot"], "recipe_id": m["id"], "servings": m["servings"]} for d in plan["days"] for m in d["meals"]]
check("save plan to calendar", "POST", "/api/plan/save", json={"meals": meals}, test=lambda b: b["saved"] == len(meals))
check("30-day progress", "GET", "/api/progress?days=30", test=lambda b: len(b["days"]) == 30)
check("analytics", "GET", "/api/analytics", test=lambda b: len(b["map"]) == 3000)
check("delete a log entry", "DELETE", f"/api/log/{entry}")
check("unlike", "DELETE", f"/api/likes/{recipe_id}", test=lambda b: not b["liked"])
check("clear log", "DELETE", "/api/log", test=lambda b: b["cleared"])

passed = sum(c["ok"] for c in checks)
print(f"\n{passed} of {len(checks)} checks passed")
out = ROOT / "outputs" / "app" / "api_checks.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"passed": passed, "total": len(checks), "checks": checks}, indent=2))
sys.exit(0 if passed == len(checks) else 1)
