import type { NextFunction, Request, Response } from "express";
import { getBusinessBySlug } from "../db/repo.js";
import type { Business } from "../types.js";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      business?: Business;
    }
  }
}

// Resuelve el negocio SIEMPRE por el slug de la URL, en el servidor.
// El modelo de IA y el cliente nunca pueden elegir a qué negocio acceder:
// cada ruta pública recibe :businessSlug y este middleware es la única
// puerta de entrada para cargar los datos de ese negocio.
export function resolveTenant(req: Request, res: Response, next: NextFunction) {
  const slug = req.params.businessSlug;
  const business = getBusinessBySlug(slug);
  if (!business) {
    return res.status(404).json({ error: "Negocio no encontrado." });
  }
  req.business = business;
  next();
}
