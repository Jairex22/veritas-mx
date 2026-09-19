import { useEffect, useState } from "react";
import { adminApi } from "../../lib/api";
import { getAdminToken } from "../../lib/adminAuth";
import { card, table, th, td } from "./adminUi";

export default function AdminAiUsagePage() {
  const api = adminApi(getAdminToken());
  const [usage, setUsage] = useState<any[]>([]);

  useEffect(() => {
    api.aiUsage().then((res: any) => setUsage(res.usage));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const totalRequests = usage.reduce((s, u) => s + u.requestsCount, 0);
  const totalTokens = usage.reduce((s, u) => s + u.tokensIn + u.tokensOut, 0);

  return (
    <div>
      <h1>Consumo de IA</h1>
      <p style={{ color: "var(--cf-text-muted)" }}>
        Conteo real de llamadas y tokens usados por el motor de IA (cuando está configurado). Útil para estimar
        costo, no es una proyección de ventas.
      </p>
      <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
        <div style={card}>
          <div style={{ fontSize: 12, color: "var(--cf-text-muted)" }}>Llamadas (30 días)</div>
          <div style={{ fontSize: 28, fontWeight: 800 }}>{totalRequests}</div>
        </div>
        <div style={card}>
          <div style={{ fontSize: 12, color: "var(--cf-text-muted)" }}>Tokens totales (30 días)</div>
          <div style={{ fontSize: 28, fontWeight: 800 }}>{totalTokens.toLocaleString("es-MX")}</div>
        </div>
      </div>
      <div style={card}>
        <table style={table}>
          <thead>
            <tr>
              <th style={th}>Fecha</th>
              <th style={th}>Llamadas</th>
              <th style={th}>Tokens entrada</th>
              <th style={th}>Tokens salida</th>
            </tr>
          </thead>
          <tbody>
            {usage.map((u) => (
              <tr key={u.date}>
                <td style={td}>{u.date}</td>
                <td style={td}>{u.requestsCount}</td>
                <td style={td}>{u.tokensIn}</td>
                <td style={td}>{u.tokensOut}</td>
              </tr>
            ))}
            {usage.length === 0 && (
              <tr>
                <td style={td} colSpan={4}>
                  Sin datos todavía (o la IA está pendiente de configurar).
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
