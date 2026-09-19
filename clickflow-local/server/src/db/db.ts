import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = process.env.DATA_DIR || path.resolve(__dirname, "../../data");
const DB_PATH = path.join(DATA_DIR, "clickflow.sqlite3");

fs.mkdirSync(DATA_DIR, { recursive: true });

export const db = new Database(DB_PATH);
db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");

// Esquema inicial. SQLite se eligió para poder instalar una base de datos
// persistente por negocio sin depender de un servidor de BD externo; si el
// producto crece a una plataforma multi-negocio con más tráfico concurrente,
// el mismo esquema es portable a Postgres.
db.exec(`
CREATE TABLE IF NOT EXISTS businesses (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  logo_url TEXT,
  colors_json TEXT NOT NULL,
  address TEXT,
  maps_url TEXT,
  timezone TEXT NOT NULL DEFAULT 'America/Mexico_City',
  whatsapp_number TEXT,
  contact_email TEXT,
  contact_phone TEXT,
  human_handoff_json TEXT NOT NULL DEFAULT '[]',
  policies_json TEXT NOT NULL DEFAULT '{}',
  ai_enabled INTEGER NOT NULL DEFAULT 1,
  ai_paused INTEGER NOT NULL DEFAULT 0,
  ai_model TEXT NOT NULL DEFAULT 'gpt-4.1-mini',
  is_demo INTEGER NOT NULL DEFAULT 0,
  retention_days INTEGER NOT NULL DEFAULT 180,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS business_hours (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  day_of_week INTEGER NOT NULL,
  opens TEXT NOT NULL,
  closes TEXT NOT NULL,
  closed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_hours_business ON business_hours(business_id);

CREATE TABLE IF NOT EXISTS business_hour_exceptions (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  closed INTEGER NOT NULL DEFAULT 1,
  opens TEXT,
  closes TEXT,
  note TEXT
);
CREATE INDEX IF NOT EXISTS idx_hour_exceptions_business ON business_hour_exceptions(business_id);

CREATE TABLE IF NOT EXISTS catalog_items (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  category TEXT NOT NULL DEFAULT 'General',
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  price_cents INTEGER NOT NULL,
  duration_minutes INTEGER,
  variants_json TEXT NOT NULL DEFAULT '[]',
  image_url TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  promo_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_catalog_business ON catalog_items(business_id);

CREATE TABLE IF NOT EXISTS faqs (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_faqs_business ON faqs(business_id);

CREATE TABLE IF NOT EXISTS admin_users (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'owner',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(business_id, email)
);

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL,
  channel TEXT NOT NULL DEFAULT 'widget',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_activity_at TEXT NOT NULL DEFAULT (datetime('now')),
  human_paused_until TEXT,
  UNIQUE(business_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_conversations_business ON conversations(business_id);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
  type TEXT NOT NULL,
  folio TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'solicitud_recibida',
  payload_json TEXT NOT NULL DEFAULT '{}',
  total_cents INTEGER,
  idempotency_key TEXT NOT NULL,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(business_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_requests_business ON requests(business_id);

CREATE TABLE IF NOT EXISTS unanswered_questions (
  id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
  question TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  resolved INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_unanswered_business ON unanswered_questions(business_id);

CREATE TABLE IF NOT EXISTS ai_usage (
  business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  requests_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (business_id, date)
);
`);

export function nowIso(): string {
  return new Date().toISOString();
}
