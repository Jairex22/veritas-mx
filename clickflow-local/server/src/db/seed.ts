// Datos de DEMOSTRACIÓN, claramente marcados como tales (isDemo = true).
// Este script es idempotente: si el negocio ya existe (por slug), no lo
// vuelve a crear, así que correr `npm run seed` varias veces es seguro.
import bcrypt from "bcryptjs";
import {
  getBusinessBySlug,
  insertAdminUser,
  insertBusiness,
  insertCatalogItem,
  insertFaq,
  replaceBusinessHours,
} from "./repo.js";
import type { Business, BusinessHours, CatalogItem, Faq } from "../types.js";

const DEFAULT_COLORS = { ivory: "#F7F4EE", graphite: "#222B32", petrol: "#245C57", coral: "#D96C56" };

type SeedBusiness = Omit<Business, "id" | "createdAt">;

function seedOne(
  business: SeedBusiness,
  hours: BusinessHours[],
  catalog: Omit<CatalogItem, "id" | "businessId">[],
  faqs: Omit<Faq, "id" | "businessId">[],
  adminEmail: string,
  adminPassword: string
) {
  const existing = getBusinessBySlug(business.slug);
  if (existing) {
    console.log(`[seed] "${business.slug}" ya existe, se omite.`);
    return existing;
  }
  const created = insertBusiness(business);
  replaceBusinessHours(created.id, hours);
  for (const item of catalog) {
    insertCatalogItem({ ...item, businessId: created.id });
  }
  for (const faq of faqs) {
    insertFaq({ ...faq, businessId: created.id });
  }
  insertAdminUser({
    businessId: created.id,
    email: adminEmail,
    passwordHash: bcrypt.hashSync(adminPassword, 10),
    role: "owner",
  });
  console.log(`[seed] Creado "${created.name}" (${created.slug}). Admin: ${adminEmail} / ${adminPassword}`);
  return created;
}

function weekly(schedule: Partial<Record<number, { opens: string; closes: string } | null>>): BusinessHours[] {
  const days = [0, 1, 2, 3, 4, 5, 6];
  return days.map((d) => {
    const entry = schedule[d];
    if (!entry) return { dayOfWeek: d, opens: "00:00", closes: "00:00", closed: true };
    return { dayOfWeek: d, opens: entry.opens, closes: entry.closes, closed: false };
  });
}

function inTwoWeeksIso(daysAhead = 0) {
  const d = new Date();
  d.setDate(d.getDate() + daysAhead);
  return d.toISOString();
}

// ---------- 1) Barbería Don César (demo principal) ----------

seedOne(
  {
    slug: "barberia-don-cesar",
    name: "Barbería Don César",
    description:
      "Barbería de barrio con más de 12 años de experiencia. Cortes clásicos y modernos, arreglo de barba y tratamientos capilares.",
    logoUrl: null,
    colors: DEFAULT_COLORS,
    address: "Av. Insurgentes Sur 1234, Col. Del Valle, CDMX",
    mapsUrl: "https://maps.google.com/?q=Av.+Insurgentes+Sur+1234+CDMX",
    timezone: "America/Mexico_City",
    whatsappNumber: "+525512345678",
    contactEmail: "hola@barberiadoncesar.mx",
    contactPhone: "+525512345678",
    humanHandoffNotes: [
      { trigger: "queja o reclamo", note: "Derivar siempre a contacto humano, no intentar resolver quejas en el chat." },
      { trigger: "evento privado o grupo grande", note: "Requiere cotización especial del dueño." },
    ],
    policies: {
      delivery: "Es un servicio en sucursal; no aplica entrega a domicilio.",
      cancellation: "Puedes cancelar o mover tu cita sin costo hasta 2 horas antes de la hora agendada.",
      changes: "Si al llegar decides cambiar el servicio, el precio final se ajusta al servicio realmente realizado.",
    },
    aiEnabled: true,
    aiPaused: false,
    aiModel: "gpt-4.1-mini",
    isDemo: true,
    retentionDays: 180,
  },
  weekly({
    1: { opens: "10:00", closes: "20:00" },
    2: { opens: "10:00", closes: "20:00" },
    3: { opens: "10:00", closes: "20:00" },
    4: { opens: "10:00", closes: "20:00" },
    5: { opens: "10:00", closes: "21:00" },
    6: { opens: "09:00", closes: "18:00" },
    0: { opens: "10:00", closes: "15:00" },
  }),
  [
    {
      category: "Cortes",
      name: "Corte clásico",
      description: "Corte a tijera y máquina, incluye lavado.",
      priceCents: 15000,
      durationMinutes: 30,
      variants: [],
      imageUrl: null,
      active: true,
      promo: null,
    },
    {
      category: "Cortes",
      name: "Corte + barba",
      description: "Corte clásico o moderno más arreglo de barba con toalla caliente.",
      priceCents: 22000,
      durationMinutes: 45,
      variants: [],
      imageUrl: null,
      active: true,
      promo: null,
    },
    {
      category: "Barba",
      name: "Arreglo de barba tradicional",
      description: "Perfilado, navaja y toalla caliente.",
      priceCents: 12000,
      durationMinutes: 25,
      variants: [],
      imageUrl: null,
      active: true,
      promo: null,
    },
    {
      category: "Cortes",
      name: "Corte niño (hasta 10 años)",
      description: "Corte sencillo para niños.",
      priceCents: 11000,
      durationMinutes: 20,
      variants: [],
      imageUrl: null,
      active: true,
      promo: null,
    },
    {
      category: "Color",
      name: "Tinte para canas",
      description: "Cobertura de canas con producto profesional.",
      priceCents: 28000,
      durationMinutes: 50,
      variants: [],
      imageUrl: null,
      active: true,
      promo: {
        priceCents: 24000,
        startsAt: inTwoWeeksIso(-30),
        endsAt: inTwoWeeksIso(30),
        label: "Promo de temporada",
      },
    },
    {
      category: "Tratamientos",
      name: "Tratamiento capilar hidratante",
      description: "Tratamiento para cabello reseco o dañado.",
      priceCents: 30000,
      durationMinutes: 40,
      variants: [
        { name: "Sencillo", priceCents: 30000, durationMinutes: 40 },
        { name: "Intensivo (con masaje)", priceCents: 42000, durationMinutes: 60 },
      ],
      imageUrl: null,
      active: true,
      promo: null,
    },
  ],
  [
    { question: "¿Aceptan tarjeta?", answer: "Sí, aceptamos efectivo, tarjeta y transferencia.", active: true },
    { question: "¿Necesito cita previa?", answer: "Se recomienda agendar, sobre todo fines de semana, pero también recibimos por orden de llegada según disponibilidad.", active: true },
    { question: "¿Atienden niños?", answer: "Sí, tenemos el servicio de corte para niños hasta 10 años.", active: true },
  ],
  "admin@barberiadoncesar.mx",
  "demo1234"
);

// ---------- 2) Pastelería Dulce Trigo (ejemplo demo) ----------

seedOne(
  {
    slug: "pasteleria-dulce-trigo",
    name: "Pastelería Dulce Trigo",
    description: "Pastelería artesanal: pasteles por encargo, cupcakes y postres para eventos. [DEMO DE EJEMPLO]",
    logoUrl: null,
    colors: DEFAULT_COLORS,
    address: "Calle Reforma 88, Col. Centro, Guadalajara, Jal.",
    mapsUrl: null,
    timezone: "America/Mexico_City",
    whatsappNumber: "+523312345678",
    contactEmail: "pedidos@dulcetrigo.mx",
    contactPhone: "+523312345678",
    humanHandoffNotes: [
      { trigger: "pastel personalizado o de boda", note: "Requiere cotización directa con el dueño, no se cotiza solo por chat." },
    ],
    policies: {
      delivery: "Entregamos en Guadalajara y zona metropolitana con costo adicional según distancia; recolección en tienda sin costo.",
      cancellation: "Los pedidos personalizados no son cancelables 48 horas antes de la entrega.",
      changes: "Cambios de sabor o tamaño solo se aceptan hasta 72 horas antes de la fecha de entrega.",
    },
    aiEnabled: true,
    aiPaused: false,
    aiModel: "gpt-4.1-mini",
    isDemo: true,
    retentionDays: 180,
  },
  weekly({
    2: { opens: "09:00", closes: "19:00" },
    3: { opens: "09:00", closes: "19:00" },
    4: { opens: "09:00", closes: "19:00" },
    5: { opens: "09:00", closes: "20:00" },
    6: { opens: "09:00", closes: "20:00" },
    0: { opens: "10:00", closes: "15:00" },
  }),
  [
    {
      category: "Pasteles",
      name: "Pastel de chocolate",
      description: "Pan de chocolate húmedo con ganache. Se pide con 48 horas de anticipación.",
      priceCents: 45000,
      durationMinutes: null,
      variants: [
        { name: "Chico (8 porciones)", priceCents: 45000 },
        { name: "Mediano (14 porciones)", priceCents: 65000 },
        { name: "Grande (24 porciones)", priceCents: 95000 },
      ],
      imageUrl: null,
      active: true,
      promo: null,
    },
    {
      category: "Pasteles",
      name: "Red velvet",
      description: "Con queso crema, se pide con 48 horas de anticipación.",
      priceCents: 50000,
      durationMinutes: null,
      variants: [
        { name: "Chico (8 porciones)", priceCents: 50000 },
        { name: "Mediano (14 porciones)", priceCents: 72000 },
      ],
      imageUrl: null,
      active: true,
      promo: null,
    },
    {
      category: "Cupcakes",
      name: "Cupcakes surtidos (docena)",
      description: "Vainilla, chocolate y red velvet.",
      priceCents: 32000,
      durationMinutes: null,
      variants: [],
      imageUrl: null,
      active: true,
      promo: null,
    },
    {
      category: "Postres",
      name: "Pay de queso",
      description: "Individual o entero, con frutos rojos opcional.",
      priceCents: 28000,
      durationMinutes: null,
      variants: [],
      imageUrl: null,
      active: true,
      promo: null,
    },
  ],
  [
    { question: "¿Con cuánta anticipación debo pedir?", answer: "Para pasteles, mínimo 48 horas de anticipación; para pedidos grandes o de temporada alta, recomendamos una semana.", active: true },
    { question: "¿Hacen pasteles sin azúcar o veganos?", answer: "Por ahora no tenemos esa opción en el catálogo; si la necesitas, pide que te contactemos para revisarlo directamente.", active: true },
  ],
  "admin@dulcetrigo.mx",
  "demo1234"
);

// ---------- 3) Carnicería La Res Buena (ejemplo demo) ----------

seedOne(
  {
    slug: "carniceria-la-res-buena",
    name: "Carnicería La Res Buena",
    description: "Carnicería de barrio, cortes frescos diarios y pedidos por kilo. [DEMO DE EJEMPLO]",
    logoUrl: null,
    colors: DEFAULT_COLORS,
    address: "Mercado Local, Local 12, Monterrey, N.L.",
    mapsUrl: null,
    timezone: "America/Monterrey",
    whatsappNumber: "+528112345678",
    contactEmail: null,
    contactPhone: "+528112345678",
    humanHandoffNotes: [
      { trigger: "pedido mayor a 10 kg", note: "Confirmar disponibilidad directamente con el encargado antes de prometer fecha." },
    ],
    policies: {
      delivery: "Entrega local el mismo día si el pedido se hace antes de las 12:00; fuera de esa hora, se entrega al día siguiente.",
      cancellation: "Los pedidos se pueden cancelar sin costo antes de ser preparados.",
      changes: "Cambios de corte o cantidad se aceptan mientras el pedido no se haya preparado.",
    },
    aiEnabled: true,
    aiPaused: false,
    aiModel: "gpt-4.1-mini",
    isDemo: true,
    retentionDays: 180,
  },
  weekly({
    1: { opens: "07:00", closes: "16:00" },
    2: { opens: "07:00", closes: "16:00" },
    3: { opens: "07:00", closes: "16:00" },
    4: { opens: "07:00", closes: "16:00" },
    5: { opens: "07:00", closes: "17:00" },
    6: { opens: "07:00", closes: "17:00" },
  }),
  [
    {
      category: "Res",
      name: "Bistec de res",
      description: "Corte para asar o freír, precio por kilo.",
      priceCents: 18000,
      durationMinutes: null,
      variants: [],
      imageUrl: null,
      active: true,
      promo: null,
    },
    {
      category: "Res",
      name: "Milanesa de res",
      description: "Corte delgado para empanizar, precio por kilo.",
      priceCents: 19500,
      durationMinutes: null,
      variants: [],
      imageUrl: null,
      active: true,
      promo: null,
    },
    {
      category: "Cerdo",
      name: "Chuleta de cerdo",
      description: "Precio por kilo.",
      priceCents: 14500,
      durationMinutes: null,
      variants: [],
      imageUrl: null,
      active: true,
      promo: null,
    },
    {
      category: "Res",
      name: "Carne molida de res",
      description: "Precio por kilo, molida al momento.",
      priceCents: 16000,
      durationMinutes: null,
      variants: [],
      imageUrl: null,
      active: true,
      promo: null,
    },
  ],
  [
    { question: "¿Hacen entregas a domicilio?", answer: "Sí, entrega local el mismo día si pides antes de las 12:00; después de esa hora, se entrega al día siguiente.", active: true },
    { question: "¿Puedo pedir un corte especial?", answer: "Sí, cuéntanos qué necesitas y lo confirmamos contigo directamente.", active: true },
  ],
  "admin@larestbuena.mx",
  "demo1234"
);

console.log("[seed] Listo.");
