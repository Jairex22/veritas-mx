import { Navigate, Route, Routes } from "react-router-dom";
import HomePage from "./pages/HomePage";
import AssistantPage from "./pages/AssistantPage";
import AdminLoginPage from "./pages/admin/AdminLoginPage";
import AdminLayout from "./pages/admin/AdminLayout";
import AdminDashboardPage from "./pages/admin/AdminDashboardPage";
import AdminBusinessPage from "./pages/admin/AdminBusinessPage";
import AdminCatalogPage from "./pages/admin/AdminCatalogPage";
import AdminRequestsPage from "./pages/admin/AdminRequestsPage";
import AdminConversationsPage from "./pages/admin/AdminConversationsPage";
import AdminUnansweredPage from "./pages/admin/AdminUnansweredPage";
import AdminAiUsagePage from "./pages/admin/AdminAiUsagePage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/assistant/:businessSlug" element={<AssistantPage />} />

      <Route path="/admin/login" element={<AdminLoginPage />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<AdminDashboardPage />} />
        <Route path="business" element={<AdminBusinessPage />} />
        <Route path="catalog" element={<AdminCatalogPage />} />
        <Route path="requests" element={<AdminRequestsPage />} />
        <Route path="conversations" element={<AdminConversationsPage />} />
        <Route path="unanswered" element={<AdminUnansweredPage />} />
        <Route path="ai-usage" element={<AdminAiUsagePage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
