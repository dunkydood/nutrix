import { Bell, CalendarDays, ChevronDown, Search } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import type { DayLog, ProfileInfo } from "../api";
import { useApi } from "../state";

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export default function Topbar() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const profile = useApi<ProfileInfo>("/profile");
  const log = useApi<DayLog>("/log");

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const pending = log.data?.entries.filter((e) => e.status === "planned").length ?? 0;
  const name = profile.data?.profile.name || "Guest";
  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    navigate(`/food-library?q=${encodeURIComponent(query.trim())}`);
  }

  return (
    <header className="topbar">
      <form className="search" onSubmit={submit} role="search">
        <Search size={18} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search for meals, ingredients or nutrition info..."
          aria-label="Search recipes by name or ingredient"
        />
      </form>
      <div className="topbar-right">
        <div className="date">
          <CalendarDays size={20} strokeWidth={1.8} />
          {today}
        </div>
        <button
          className="icon-btn"
          onClick={() => navigate("/meal-plan")}
          title={pending ? `${pending} planned meal${pending > 1 ? "s" : ""} today not yet eaten` : "No planned meals waiting"}
          aria-label="Planned meals today"
        >
          <Bell size={22} strokeWidth={1.8} />
          {pending > 0 && <span className="badge-dot">{pending}</span>}
        </button>
        <div ref={menuRef} style={{ position: "relative" }}>
          <button className="user" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
            <div className="avatar">{initials(name)}</div>
            <div>
              <div className="user-name">{name}</div>
              <div className="user-sub">
                Keep Going <span className="online" />
              </div>
            </div>
            <ChevronDown size={18} />
          </button>
          {open && (
            <div className="menu" role="menu">
              <button role="menuitem" onClick={() => { setOpen(false); navigate("/profile"); }}>My Profile</button>
              <button role="menuitem" onClick={() => { setOpen(false); navigate("/goals"); }}>Goals</button>
              <button role="menuitem" onClick={() => { setOpen(false); navigate("/settings"); }}>Settings</button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
