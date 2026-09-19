import { useEffect, useState } from "react";
import { adminApi } from "../../lib/api";
import { getAdminToken } from "../../lib/adminAuth";
import { card, table, th, td, buttonSecondary } from "./adminUi";

export default function AdminConversationsPage() {
  const api = adminApi(getAdminToken());
  const [conversations, setConversations] = useState<any[]>([]);
  const [selected, setSelected] = useState<any | null>(null);
  const [messages, setMessages] = useState<any[]>([]);

  async function load() {
    const res = await api.listConversations();
    setConversations(res.conversations);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openConversation(conv: any) {
    setSelected(conv);
    const res = await api.getConversationMessages(conv.id);
    setMessages(res.messages);
  }

  async function pauseForHuman(id: string) {
    await api.pauseForHuman(id, 60);
    await load();
  }

  return (
    <div>
      <h1>Conversaciones</h1>
      <p style={{ color: "var(--cf-text-muted)" }}>
        Revisa lo que el asistente respondió. Puedes pausar la automatización de una conversación cuando una
        persona del negocio la esté atendiendo directamente.
      </p>
      <div style={{ display: "flex", gap: 20 }}>
        <div style={{ ...card, flex: 1, minWidth: 280 }}>
          <table style={table}>
            <thead>
              <tr>
                <th style={th}>Sesión</th>
                <th style={th}>Última actividad</th>
                <th style={th} />
              </tr>
            </thead>
            <tbody>
              {conversations.map((c) => (
                <tr key={c.id}>
                  <td style={td}>{c.sessionId.slice(0, 10)}…</td>
                  <td style={td}>{new Date(c.lastActivityAt).toLocaleString("es-MX")}</td>
                  <td style={td}>
                    <button style={buttonSecondary} onClick={() => openConversation(c)}>
                      Ver
                    </button>{" "}
                    <button style={buttonSecondary} onClick={() => pauseForHuman(c.id)}>
                      Pausar 1h (atiendo yo)
                    </button>
                  </td>
                </tr>
              ))}
              {conversations.length === 0 && (
                <tr>
                  <td style={td} colSpan={3}>
                    Aún no hay conversaciones.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {selected && (
          <div style={{ ...card, flex: 1, minWidth: 280, maxHeight: 500, overflowY: "auto" }}>
            <h3 style={{ marginTop: 0 }}>Mensajes</h3>
            {messages.map((m) => (
              <div key={m.id} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 11, color: "var(--cf-text-muted)", textTransform: "uppercase" }}>
                  {m.role === "user" ? "Cliente" : "Asistente"} · {new Date(m.createdAt).toLocaleTimeString("es-MX")}
                </div>
                <div style={{ fontSize: 14 }}>{m.content}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
