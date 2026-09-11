import { BarChart3, BookOpen, CalendarDays, LayoutDashboard, Leaf, Settings, Sparkles, Target, User } from "lucide-react";
import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/profile", label: "My Profile", icon: User },
  { to: "/goals", label: "Goals", icon: Target },
  { to: "/meal-plan", label: "Meal Plan", icon: CalendarDays },
  { to: "/recommendations", label: "Recommendations", icon: Sparkles },
  { to: "/food-library", label: "Food Library", icon: BookOpen },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <img src="/leaf.svg" alt="" />
        <div>
          <div className="brand-name">NUTRIX</div>
          <div className="brand-sub">Intelligent Nutrition</div>
        </div>
      </div>
      <nav className="nav" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`} title={label}>
            <Icon size={20} strokeWidth={1.8} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-quote">
        <p>
          “Better
          <br />
          &nbsp;&nbsp;Food
          <br />
          Brighter
          <br />
          <span>You”</span>
        </p>
        <Leaf size={46} strokeWidth={1.2} />
      </div>
    </aside>
  );
}
