import { useEffect, useState } from "react";
import { adminApi } from "../../lib/api";
import { getAdminToken } from "../../lib/adminAuth";
import { card, input, button, buttonSecondary, buttonDanger, table, th, td } from "./adminUi";

const EMPTY_ITEM = {
  category: "General",
  name: "",
  description: "",
  priceCents: 0,
  durationMinutes: null as number | null,
  variants: [] as { name: string; priceCents: number }[],
  imageUrl: null as string | null,
  active: true,
  promo: null as { priceCents: number; startsAt: string; endsAt: string; label?: string } | null,
};

export default function AdminCatalogPage() {
  const api = adminApi(getAdminToken());
  const [items, setItems] = useState<any[]>([]);
  const [editing, setEditing] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const res = await api.listCatalog();
    setItems(res.items);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function money(cents: number) {
    return (cents / 100).toLocaleString("es-MX", { style: "currency", currency: "MXN" });
  }

  async function save() {
    setError(null);
    try {
      if (editing.id) {
        await api.updateCatalogItem(editing.id, editing);
      } else {
        await api.createCatalogItem(editing);
      }
      setEditing(null);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove(id: string) {
    if (!confirm("¿Eliminar este artículo del catálogo?")) return;
    await api.deleteCatalogItem(id);
    await load();
  }

  return (
    <div>
      <h1>Catálogo</h1>
      <p style={{ color: "var(--cf-text-muted)" }}>
        Publicar un artículo aquí no garantiza inventario disponible; el asistente lo aclara a las personas.
      </p>

      <div style={card}>
        <table style={table}>
          <thead>
            <tr>
              <th style={th}>Categoría</th>
              <th style={th}>Nombre</th>
              <th style={th}>Precio</th>
              <th style={th}>Duración</th>
              <th style={th}>Activo</th>
              <th style={th}>Promoción</th>
              <th style={th} />
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td style={td}>{item.category}</td>
                <td style={td}>{item.name}</td>
                <td style={td}>{money(item.priceCents)}</td>
                <td style={td}>{item.durationMinutes ? `${item.durationMinutes} min` : "—"}</td>
                <td style={td}>{item.active ? "Sí" : "No"}</td>
                <td style={td}>{item.promo ? money(item.promo.priceCents) : "—"}</td>
                <td style={td}>
                  <button style={buttonSecondary} onClick={() => setEditing(item)}>
                    Editar
                  </button>{" "}
                  <button style={buttonDanger} onClick={() => remove(item.id)}>
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button style={{ ...button, marginTop: 16 }} onClick={() => setEditing({ ...EMPTY_ITEM })}>
          + Nuevo artículo
        </button>
      </div>

      {editing && (
        <div style={card}>
          <h3 style={{ marginTop: 0 }}>{editing.id ? "Editar artículo" : "Nuevo artículo"}</h3>
          {error && <p style={{ color: "var(--cf-danger)" }}>{error}</p>}
          <Field label="Categoría">
            <input style={input} value={editing.category} onChange={(e) => setEditing({ ...editing, category: e.target.value })} />
          </Field>
          <Field label="Nombre">
            <input style={input} value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
          </Field>
          <Field label="Descripción">
            <textarea
              style={{ ...input, minHeight: 60 }}
              value={editing.description}
              onChange={(e) => setEditing({ ...editing, description: e.target.value })}
            />
          </Field>
          <Field label="Precio (MXN)">
            <input
              style={input}
              type="number"
              step="0.01"
              value={editing.priceCents / 100}
              onChange={(e) => setEditing({ ...editing, priceCents: Math.round(Number(e.target.value) * 100) })}
            />
          </Field>
          <Field label="Duración en minutos (solo para servicios/citas; vacío = producto)">
            <input
              style={input}
              type="number"
              value={editing.durationMinutes ?? ""}
              onChange={(e) =>
                setEditing({ ...editing, durationMinutes: e.target.value === "" ? null : Number(e.target.value) })
              }
            />
          </Field>
          <Field label="URL de imagen (opcional)">
            <input
              style={input}
              value={editing.imageUrl ?? ""}
              onChange={(e) => setEditing({ ...editing, imageUrl: e.target.value || null })}
            />
          </Field>
          <Field label="Activo (visible para clientes)">
            <input
              type="checkbox"
              checked={editing.active}
              onChange={(e) => setEditing({ ...editing, active: e.target.checked })}
            />
          </Field>

          <h4>Promoción con vigencia (opcional)</h4>
          <Field label="Activar promoción">
            <input
              type="checkbox"
              checked={!!editing.promo}
              onChange={(e) =>
                setEditing({
                  ...editing,
                  promo: e.target.checked
                    ? { priceCents: editing.priceCents, startsAt: new Date().toISOString(), endsAt: new Date().toISOString(), label: "Promoción" }
                    : null,
                })
              }
            />
          </Field>
          {editing.promo && (
            <>
              <Field label="Precio de promoción (MXN)">
                <input
                  style={input}
                  type="number"
                  step="0.01"
                  value={editing.promo.priceCents / 100}
                  onChange={(e) =>
                    setEditing({ ...editing, promo: { ...editing.promo, priceCents: Math.round(Number(e.target.value) * 100) } })
                  }
                />
              </Field>
              <Field label="Inicia (fecha y hora)">
                <input
                  style={input}
                  type="datetime-local"
                  value={editing.promo.startsAt.slice(0, 16)}
                  onChange={(e) =>
                    setEditing({ ...editing, promo: { ...editing.promo, startsAt: new Date(e.target.value).toISOString() } })
                  }
                />
              </Field>
              <Field label="Termina (fecha y hora)">
                <input
                  style={input}
                  type="datetime-local"
                  value={editing.promo.endsAt.slice(0, 16)}
                  onChange={(e) =>
                    setEditing({ ...editing, promo: { ...editing.promo, endsAt: new Date(e.target.value).toISOString() } })
                  }
                />
              </Field>
            </>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button style={button} onClick={save}>
              Guardar
            </button>
            <button style={buttonSecondary} onClick={() => setEditing(null)}>
              Cancelar
            </button>
          </div>
        </div>
      )}
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
