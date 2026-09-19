import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./lib/auth";
import { ThemeProvider } from "./lib/theme";
import { FiltersProvider } from "./lib/filters";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import PlantSummary from "./pages/PlantSummary";
import Performance from "./pages/Performance";
import Operators from "./pages/Operators";
import OperatorDetail from "./pages/OperatorDetail";
import Stations from "./pages/Stations";
import Quality from "./pages/Quality";
import Training from "./pages/Training";
import Comparisons from "./pages/Comparisons";
import Alerts from "./pages/Alerts";
import SettingsPage from "./pages/Settings";
import Audit from "./pages/Audit";

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <FiltersProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<PlantSummary />} />
                <Route path="/rendimiento" element={<Performance />} />
                <Route path="/operadores" element={<Operators />} />
                <Route path="/operadores/:operatorId" element={<OperatorDetail />} />
                <Route path="/estaciones" element={<Stations />} />
                <Route path="/calidad" element={<Quality />} />
                <Route path="/capacitacion" element={<Training />} />
                <Route path="/comparaciones" element={<Comparisons />} />
                <Route path="/alertas" element={<Alerts />} />
                <Route path="/configuracion" element={<SettingsPage />} />
                <Route path="/auditoria" element={<Audit />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </FiltersProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
