import type { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";
import { getBusinessById } from "../db/repo.js";

export interface AdminTokenPayload {
  adminId: string;
  businessId: string;
  role: string;
}

function getJwtSecret(): string {
  const secret = process.env.JWT_SECRET;
  if (!secret) {
    throw new Error("JWT_SECRET no está configurado en el servidor.");
  }
  return secret;
}

export function signAdminToken(payload: AdminTokenPayload): string {
  return jwt.sign(payload, getJwtSecret(), { expiresIn: "12h" });
}

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      admin?: AdminTokenPayload;
    }
  }
}

// Exige un JWT de administrador válido y, además, vuelve a resolver el
// negocio en el servidor (nunca confía en un businessId enviado por el
// cliente) para que cada operación quede aislada al negocio del token.
export function requireAdminAuth(req: Request, res: Response, next: NextFunction) {
  const header = req.headers.authorization;
  if (!header || !header.startsWith("Bearer ")) {
    return res.status(401).json({ error: "No autenticado." });
  }
  const token = header.slice("Bearer ".length);
  try {
    const payload = jwt.verify(token, getJwtSecret()) as AdminTokenPayload;
    const business = getBusinessById(payload.businessId);
    if (!business) {
      return res.status(401).json({ error: "Sesión inválida." });
    }
    req.admin = payload;
    next();
  } catch {
    return res.status(401).json({ error: "Sesión inválida o expirada." });
  }
}
