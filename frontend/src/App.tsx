import { Navigate, Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import Analytics from "./pages/Analytics";
import Dashboard from "./pages/Dashboard";
import FoodLibrary from "./pages/FoodLibrary";
import Goals from "./pages/Goals";
import MealPlan from "./pages/MealPlan";
import Profile from "./pages/Profile";
import Recommendations from "./pages/Recommendations";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <div className="app">
      <Sidebar />
      <main className="main">
        <Topbar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/goals" element={<Goals />} />
          <Route path="/meal-plan" element={<MealPlan />} />
          <Route path="/recommendations" element={<Recommendations />} />
          <Route path="/food-library" element={<FoodLibrary />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
