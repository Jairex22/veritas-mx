import "dotenv/config";
import express from "express";
import cors from "cors";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { resolveTenant } from "./middleware/tenant.js";
import { publicApiLimiter } from "./middleware/rateLimit.js";
import { publicRouter } from "./routes/public.js";
import { adminRouter } from "./routes/admin.js";
import { isAiConfigured } from "./ai/openaiClient.js";
import { logger } from "./utils/logger.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();

const allowedOrigins = process.env.CORS_ORIGIN?.split(",").map((s) => s.trim());
app.use(
  cors({
    origin: allowedOrigins && allowedOrigins.length > 0 ? allowedOrigins : true,
  })
);
app.use(express.json({ limit: "200kb" }));

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, aiConfigured: isAiConfigured(), time: new Date().toISOString() });
});

app.use("/api/public/business/:businessSlug", publicApiLimiter, resolveTenant, publicRouter);
app.use("/api/admin", adminRouter);

// El script de instalación (embed.js) y sus imágenes de demostración se
// sirven como archivos estáticos, sin build, para que integrarlo en la
// página de un negocio sea copiar un <script src="...">.
app.use("/embed", express.static(path.resolve(__dirname, "../public/embed")));
app.use("/demo-assets", express.static(path.resolve(__dirname, "../public/demo-assets")));

app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  logger.error("unhandled_error", { message: err?.message });
  res.status(500).json({ error: "Ocurrió un problema en el servidor. Intenta de nuevo." });
});

const port = Number(process.env.PORT) || 8787;
app.listen(port, () => {
  logger.info("server_started", { port, aiConfigured: isAiConfigured() });
  if (!isAiConfigured()) {
    logger.warn("ai_not_configured", {
      note: "OPENAI_API_KEY no está configurada. El chat usará el motor de respaldo determinista. IA pendiente de configurar.",
    });
  }
});
