"use strict";

/**
 * GPV Process Genealogy - local server.
 *
 * Native Node.js only (http, fs, path, url, child_process) - no Express,
 * no build step, no node_modules required at runtime. Serves the
 * pre-built frontend from /public and a small read-only JSON API backed
 * by /data/assemblies.json.
 *
 * Run with:  node node/index.js
 */

const http = require("http");
const fs = require("fs");
const path = require("path");
const { URL } = require("url");
const { exec } = require("child_process");

const PORT = process.env.PORT ? Number(process.env.PORT) : 3000;
const HOST = "localhost";

const ROOT_DIR = path.resolve(__dirname, "..");
const PUBLIC_DIR = path.join(ROOT_DIR, "public");
const DATA_FILE = path.join(ROOT_DIR, "data", "assemblies.json");

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".ico": "image/x-icon",
  ".map": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

// ---------------------------------------------------------------------------
// Data access (single JSON file for now; keep this the ONLY place that
// knows about the storage format so it can be swapped for FactoryLogix /
// OData / CSV / SQL Server later without touching the HTTP layer below).
// ---------------------------------------------------------------------------
function loadAssemblies() {
  const raw = fs.readFileSync(DATA_FILE, "utf8");
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed.assemblies) ? parsed.assemblies : [];
}

function findAssembly(query) {
  if (!query) return null;
  const needle = decodeURIComponent(query).trim().toLowerCase();
  const assemblies = loadAssemblies();
  return (
    assemblies.find(
      (a) =>
        String(a.assembly).toLowerCase() === needle ||
        String(a.partNumber).toLowerCase() === needle
    ) || null
  );
}

function findLevel(assembly, levelId) {
  if (!assembly || !levelId) return null;
  const needle = decodeURIComponent(levelId).trim().toLowerCase();
  return (assembly.levels || []).find((l) => String(l.id).toLowerCase() === needle) || null;
}

function assemblySummary(a) {
  return {
    assembly: a.assembly,
    partNumber: a.partNumber,
    description: a.description,
    workOrder: a.workOrder,
    currentLevel: a.currentLevel,
    status: a.status,
    progress: a.progress,
    route: a.route,
  };
}

// ---------------------------------------------------------------------------
// JSON helpers
// ---------------------------------------------------------------------------
function sendJson(res, statusCode, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function sendNotFoundJson(res, message) {
  sendJson(res, 404, { error: message || "Not found" });
}

// ---------------------------------------------------------------------------
// Static file serving (with basic path-traversal protection)
// ---------------------------------------------------------------------------
function serveStatic(req, res, pathname) {
  let relativePath = pathname === "/" ? "/index.html" : pathname;
  relativePath = relativePath.split("?")[0];

  const decoded = decodeURIComponent(relativePath);
  const normalized = path.normalize(decoded).replace(/^(\.\.[/\\])+/, "");
  let filePath = path.join(PUBLIC_DIR, normalized);

  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Forbidden");
    return;
  }

  fs.stat(filePath, (err, stats) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }

    if (stats.isDirectory()) {
      filePath = path.join(filePath, "index.html");
    }

    fs.readFile(filePath, (readErr, content) => {
      if (readErr) {
        res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("Not found");
        return;
      }
      const ext = path.extname(filePath).toLowerCase();
      const contentType = MIME_TYPES[ext] || "application/octet-stream";
      res.writeHead(200, {
        "Content-Type": contentType,
        "Content-Length": content.length,
      });
      res.end(content);
    });
  });
}

// ---------------------------------------------------------------------------
// API routing
// ---------------------------------------------------------------------------
function handleApi(req, res, pathname) {
  const parts = pathname.split("/").filter(Boolean); // ["api", "assemblies", ":assembly", ...]

  // GET /api/health
  if (parts.length === 2 && parts[1] === "health") {
    sendJson(res, 200, { status: "ok" });
    return;
  }

  // GET /api/assemblies
  if (parts.length === 2 && parts[1] === "assemblies") {
    try {
      const list = loadAssemblies().map(assemblySummary);
      sendJson(res, 200, { assemblies: list });
    } catch (err) {
      sendJson(res, 500, { error: "Could not read assemblies data", detail: String(err.message || err) });
    }
    return;
  }

  // GET /api/assemblies/:assembly
  if (parts.length === 3 && parts[1] === "assemblies") {
    try {
      const assembly = findAssembly(parts[2]);
      if (!assembly) {
        sendNotFoundJson(res, "Assembly not found");
        return;
      }
      sendJson(res, 200, assembly);
    } catch (err) {
      sendJson(res, 500, { error: "Could not read assemblies data", detail: String(err.message || err) });
    }
    return;
  }

  // GET /api/assemblies/:assembly/route
  if (parts.length === 4 && parts[1] === "assemblies" && parts[3] === "route") {
    try {
      const assembly = findAssembly(parts[2]);
      if (!assembly) {
        sendNotFoundJson(res, "Assembly not found");
        return;
      }
      const levels = (assembly.levels || []).map((l) => ({
        id: l.id,
        name: l.name,
        status: l.status,
        previousLevel: l.previousLevel,
        nextLevel: l.nextLevel,
        stationCount: (l.stations || []).length,
      }));
      sendJson(res, 200, {
        assembly: assembly.assembly,
        route: assembly.route,
        currentLevel: assembly.currentLevel,
        levels,
      });
    } catch (err) {
      sendJson(res, 500, { error: "Could not read assemblies data", detail: String(err.message || err) });
    }
    return;
  }

  // GET /api/assemblies/:assembly/levels/:level
  if (parts.length === 5 && parts[1] === "assemblies" && parts[3] === "levels") {
    try {
      const assembly = findAssembly(parts[2]);
      if (!assembly) {
        sendNotFoundJson(res, "Assembly not found");
        return;
      }
      const level = findLevel(assembly, parts[4]);
      if (!level) {
        sendNotFoundJson(res, "Level not found");
        return;
      }
      sendJson(res, 200, {
        assembly: assembly.assembly,
        partNumber: assembly.partNumber,
        description: assembly.description,
        workOrder: assembly.workOrder,
        level,
      });
    } catch (err) {
      sendJson(res, 500, { error: "Could not read assemblies data", detail: String(err.message || err) });
    }
    return;
  }

  sendNotFoundJson(res, "Unknown API endpoint");
}

// ---------------------------------------------------------------------------
// Server
// ---------------------------------------------------------------------------
const server = http.createServer((req, res) => {
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { "Content-Type": "text/plain; charset=utf-8", Allow: "GET, HEAD" });
    res.end("Method not allowed");
    return;
  }

  let pathname;
  try {
    pathname = new URL(req.url, `http://${req.headers.host || `${HOST}:${PORT}`}`).pathname;
  } catch (err) {
    res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Bad request");
    return;
  }

  if (pathname.startsWith("/api/")) {
    handleApi(req, res, pathname);
    return;
  }

  serveStatic(req, res, pathname);
});

function openBrowser(url) {
  const platform = process.platform;
  let command;
  if (platform === "win32") {
    command = `start "" "${url}"`;
  } else if (platform === "darwin") {
    command = `open "${url}"`;
  } else {
    command = `xdg-open "${url}"`;
  }
  exec(command, (err) => {
    if (err) {
      // Non-fatal: the server keeps running even if we can't auto-open a browser
      // (e.g. headless environment). The user can still open the URL manually.
    }
  });
}

server.listen(PORT, HOST, () => {
  const url = `http://${HOST}:${PORT}`;
  console.log("========================================");
  console.log("GPV PROCESS GENEALOGY");
  console.log("Server running");
  console.log(url);
  console.log("Press CTRL+C to stop");
  console.log("========================================");
  openBrowser(url);
});

process.on("SIGINT", () => {
  console.log("\nStopping GPV Process Genealogy server...");
  server.close(() => process.exit(0));
});
