import { useEffect, useState } from "react";
import { adminApi } from "../../lib/api";
import { getAdminToken } from "../../lib/adminAuth";
import { card, input, button, buttonSecondary, buttonDanger } from "./adminUi";

const DAY_NAMES = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];

export default function AdminBusinessPage() {
  const api = adminApi(getAdminToken());
  const [business, setBusiness] = useState<any>(null);
  const [hours, setHours] = useState<any[]>([]);
  const [exceptions, setExceptions] = useState<any[]>([]);
  const [newException, setNewException] = useState({ date: "", closed: true, opens: "", closes: "", note: "" });
  const [faqs, setFaqs] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const me = await api.me();
    setBusiness(me.business);
    setHours(
      me.hours.length
        ? me.hours
        : Array.from({ length: 7 }, (_, d) => ({ dayOfWeek: d, opens: "09:00", closes: "18:00", closed: true }))
    );
    setExceptions(me.exceptions ?? []);
    const f = await api.listFaqs();
    setFaqs(f.faqs);
  }

  async function addException() {
    if (!newException.date) return;
    await api.addHourException(newException);
    setNewException({ date: "", closed: true, opens: "", closes: "", note: "" });
    await load();
  }

  async function removeException(date: string) {
    await api.deleteHourException(date);
    await load();
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!business) return <p>Cargando…</p>;

  async function saveBusiness() {
    setSaving(true);
    setError(null);
    setSavedMsg(null);
    try {
      await api.updateBusiness({
        name: business.name,
        description: business.description,
        address: business.address,
        mapsUrl: business.mapsUrl,
        timezone: business.timezone,
        whatsappNumber: business.whatsappNumber,
        contactEmail: business.contactEmail,
        contactPhone: business.contactPhone,
        colors: business.colors,
        policies: business.policies,
        retentionDays: business.retentionDays,
      });
      setSavedMsg("Guardado.");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function saveHours() {
    setSaving(true);
    setError(null);
    try {
      await api.updateHours(hours);
      setSavedMsg("Horario guardado.");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function addFaq() {
    const faq = { question: "Nueva pregunta", answer: "Respuesta...", active: true };
    const res = await api.createFaq(faq);
    setFaqs((prev) => [...prev, res.faq]);
  }

  async function saveFaq(id: string, patch: any) {
    await api.updateFaq(id, patch);
  }

  async function removeFaq(id: string) {
    await api.deleteFaq(id);
    setFaqs((prev) => prev.filter((f) => f.id !== id));
  }

  return (
    <div>
      <h1>Información del negocio</h1>
      {error && <p style={{ color: "var(--cf-danger)" }}>{error}</p>}
      {savedMsg && <p style={{ color: "var(--cf-success)" }}>{savedMsg}</p>}

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Datos básicos</h3>
        <Field label="Nombre">
          <input style={input} value={business.name} onChange={(e) => setBusiness({ ...business, name: e.target.value })} />
        </Field>
        <Field label="Descripción">
          <textarea
            style={{ ...input, minHeight: 70 }}
            value={business.description}
            onChange={(e) => setBusiness({ ...business, description: e.target.value })}
          />
        </Field>
        <Field label="Dirección">
          <input
            style={input}
            value={business.address ?? ""}
            onChange={(e) => setBusiness({ ...business, address: e.target.value })}
          />
        </Field>
        <Field label="Enlace de mapa (opcional)">
          <input
            style={input}
            value={business.mapsUrl ?? ""}
            onChange={(e) => setBusiness({ ...business, mapsUrl: e.target.value })}
          />
        </Field>
        <Field label="Zona horaria">
          <input
            style={input}
            value={business.timezone}
            onChange={(e) => setBusiness({ ...business, timezone: e.target.value })}
          />
        </Field>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Contacto</h3>
        <Field label="WhatsApp (con lada, ej. +525512345678)">
          <input
            style={input}
            value={business.whatsappNumber ?? ""}
            onChange={(e) => setBusiness({ ...business, whatsappNumber: e.target.value })}
          />
        </Field>
        <Field label="Correo de contacto">
          <input
            style={input}
            value={business.contactEmail ?? ""}
            onChange={(e) => setBusiness({ ...business, contactEmail: e.target.value })}
          />
        </Field>
        <Field label="Teléfono de contacto">
          <input
            style={input}
            value={business.contactPhone ?? ""}
            onChange={(e) => setBusiness({ ...business, contactPhone: e.target.value })}
          />
        </Field>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Identidad visual</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          {(["ivory", "graphite", "petrol", "coral"] as const).map((key) => (
            <Field key={key} label={key}>
              <input
                style={input}
                type="color"
                value={business.colors[key]}
                onChange={(e) => setBusiness({ ...business, colors: { ...business.colors, [key]: e.target.value } })}
              />
            </Field>
          ))}
        </div>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Políticas</h3>
        <Field label="Entrega">
          <textarea
            style={{ ...input, minHeight: 60 }}
            value={business.policies?.delivery ?? ""}
            onChange={(e) => setBusiness({ ...business, policies: { ...business.policies, delivery: e.target.value } })}
          />
        </Field>
        <Field label="Cancelación">
          <textarea
            style={{ ...input, minHeight: 60 }}
            value={business.policies?.cancellation ?? ""}
            onChange={(e) => setBusiness({ ...business, policies: { ...business.policies, cancellation: e.target.value } })}
          />
        </Field>
        <Field label="Cambios">
          <textarea
            style={{ ...input, minHeight: 60 }}
            value={business.policies?.changes ?? ""}
            onChange={(e) => setBusiness({ ...business, policies: { ...business.policies, changes: e.target.value } })}
          />
        </Field>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Retención de datos</h3>
        <Field label="Días que se conservan conversaciones y solicitudes">
          <input
            style={input}
            type="number"
            min={1}
            value={business.retentionDays}
            onChange={(e) => setBusiness({ ...business, retentionDays: Number(e.target.value) })}
          />
        </Field>
      </div>

      <button style={button} onClick={saveBusiness} disabled={saving}>
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>

      <div style={{ ...card, marginTop: 32 }}>
        <h3 style={{ marginTop: 0 }}>Horario habitual</h3>
        {hours
          .slice()
          .sort((a, b) => a.dayOfWeek - b.dayOfWeek)
          .map((h) => (
            <div key={h.dayOfWeek} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <span style={{ width: 100, fontSize: 13 }}>{DAY_NAMES[h.dayOfWeek]}</span>
              <label style={{ fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={!h.closed}
                  onChange={(e) =>
                    setHours((prev) => prev.map((x) => (x.dayOfWeek === h.dayOfWeek ? { ...x, closed: !e.target.checked } : x)))
                  }
                />{" "}
                Abierto
              </label>
              {!h.closed && (
                <>
                  <input
                    type="time"
                    value={h.opens}
                    style={{ ...input, width: 110 }}
                    onChange={(e) =>
                      setHours((prev) => prev.map((x) => (x.dayOfWeek === h.dayOfWeek ? { ...x, opens: e.target.value } : x)))
                    }
                  />
                  <input
                    type="time"
                    value={h.closes}
                    style={{ ...input, width: 110 }}
                    onChange={(e) =>
                      setHours((prev) => prev.map((x) => (x.dayOfWeek === h.dayOfWeek ? { ...x, closes: e.target.value } : x)))
                    }
                  />
                </>
              )}
            </div>
          ))}
        <button style={button} onClick={saveHours} disabled={saving}>
          Guardar horario
        </button>
      </div>

      <div style={{ ...card, marginTop: 32 }}>
        <h3 style={{ marginTop: 0 }}>Excepciones de horario</h3>
        <p style={{ fontSize: 13, color: "var(--cf-text-muted)" }}>
          Para días específicos distintos al horario habitual (festivos, cierres, horario especial).
        </p>
        {exceptions.map((e) => (
          <div key={e.date} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, fontSize: 13 }}>
            <strong>{e.date}</strong>
            <span>{e.closed ? `Cerrado${e.note ? ` (${e.note})` : ""}` : `${e.opens} - ${e.closes}`}</span>
            <button style={buttonDanger} onClick={() => removeException(e.date)}>
              Quitar
            </button>
          </div>
        ))}
        <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap", marginTop: 12 }}>
          <Field label="Fecha">
            <input
              style={input}
              type="date"
              value={newException.date}
              onChange={(e) => setNewException({ ...newException, date: e.target.value })}
            />
          </Field>
          <Field label="¿Cerrado todo el día?">
            <input
              type="checkbox"
              checked={newException.closed}
              onChange={(e) => setNewException({ ...newException, closed: e.target.checked })}
            />
          </Field>
          {!newException.closed && (
            <>
              <Field label="Abre">
                <input
                  style={input}
                  type="time"
                  value={newException.opens}
                  onChange={(e) => setNewException({ ...newException, opens: e.target.value })}
                />
              </Field>
              <Field label="Cierra">
                <input
                  style={input}
                  type="time"
                  value={newException.closes}
                  onChange={(e) => setNewException({ ...newException, closes: e.target.value })}
                />
              </Field>
            </>
          )}
          <Field label="Nota (opcional)">
            <input
              style={input}
              value={newException.note}
              onChange={(e) => setNewException({ ...newException, note: e.target.value })}
            />
          </Field>
          <button style={buttonSecondary} onClick={addException}>
            + Agregar excepción
          </button>
        </div>
      </div>

      <div style={{ ...card, marginTop: 32 }}>
        <h3 style={{ marginTop: 0 }}>Preguntas frecuentes</h3>
        {faqs.map((f) => (
          <div key={f.id} style={{ borderTop: "1px solid var(--cf-border)", paddingTop: 10, marginTop: 10 }}>
            <input
              style={{ ...input, fontWeight: 700, marginBottom: 6 }}
              value={f.question}
              onChange={(e) => setFaqs((prev) => prev.map((x) => (x.id === f.id ? { ...x, question: e.target.value } : x)))}
              onBlur={() => saveFaq(f.id, { question: f.question })}
            />
            <textarea
              style={{ ...input, minHeight: 50 }}
              value={f.answer}
              onChange={(e) => setFaqs((prev) => prev.map((x) => (x.id === f.id ? { ...x, answer: e.target.value } : x)))}
              onBlur={() => saveFaq(f.id, { answer: f.answer })}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
              <button style={buttonDanger} onClick={() => removeFaq(f.id)}>
                Eliminar
              </button>
            </div>
          </div>
        ))}
        <button style={{ ...buttonSecondary, marginTop: 12 }} onClick={addFaq}>
          + Agregar pregunta frecuente
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block", fontSize: 13, marginBottom: 10 }}>
      {label}
      <div style={{ marginTop: 4 }}>{children}</div>
    </label>
  );
}
