import { useEffect, useState } from "react";
import { adminApi } from "../../lib/api";
import { getAdminToken } from "../../lib/adminAuth";
import { card, table, th, td, buttonSecondary } from "./adminUi";

export default function AdminUnansweredPage() {
  const api = adminApi(getAdminToken());
  const [questions, setQuestions] = useState<any[]>([]);

  async function load() {
    const res = await api.listUnanswered();
    setQuestions(res.questions);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function resolve(id: string) {
    await api.resolveUnanswered(id);
    await load();
  }

  return (
    <div>
      <h1>Preguntas sin responder bien</h1>
      <p style={{ color: "var(--cf-text-muted)" }}>
        Aquí aparecen los mensajes que el asistente no pudo resolver con la información configurada (o que llegaron
        mientras la IA estaba pendiente de configurar). Úsalas para completar tu catálogo, políticas o preguntas
        frecuentes.
      </p>
      <div style={card}>
        <table style={table}>
          <thead>
            <tr>
              <th style={th}>Pregunta / mensaje</th>
              <th style={th}>Fecha</th>
              <th style={th}>Estado</th>
              <th style={th} />
            </tr>
          </thead>
          <tbody>
            {questions.map((q) => (
              <tr key={q.id}>
                <td style={td}>{q.question}</td>
                <td style={td}>{new Date(q.createdAt).toLocaleString("es-MX")}</td>
                <td style={td}>{q.resolved ? "Resuelta" : "Pendiente"}</td>
                <td style={td}>
                  {!q.resolved && (
                    <button style={buttonSecondary} onClick={() => resolve(q.id)}>
                      Marcar resuelta
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {questions.length === 0 && (
              <tr>
                <td style={td} colSpan={4}>
                  No hay preguntas pendientes.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
