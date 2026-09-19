import type { Business } from "../types.js";
import { getOpenAiClient, getConfiguredModel } from "./openaiClient.js";
import { runTool, toolDefinitions } from "./tools.js";
import { buildSystemPrompt } from "./systemPrompt.js";
import { recordAiUsage } from "../db/repo.js";
import { logger } from "../utils/logger.js";
import { runFallbackEngine } from "./fallbackEngine.js";

export interface ChatTurnInput {
  business: Business;
  history: { role: "user" | "assistant"; content: string }[]; // ya acotado por el llamador
  userMessage: string;
}

export interface ChatTurnResult {
  reply: string;
  aiConfigured: boolean;
  proposal: Record<string, unknown> | null;
  error: boolean;
}

const MAX_AGENT_STEPS = 4; // límite de pasos del agente por turno, para controlar costo y evitar loops
const MAX_HISTORY_MESSAGES = 16; // historial acotado para controlar costos

export async function runChatTurn(input: ChatTurnInput): Promise<ChatTurnResult> {
  const { business } = input;

  if (business.aiPaused) {
    return {
      reply:
        "El equipo del negocio pausó temporalmente las respuestas automáticas de este chat. Puedes dejar tu mensaje y te contactarán directamente, o intenta más tarde.",
      aiConfigured: true,
      proposal: null,
      error: false,
    };
  }

  const client = getOpenAiClient();
  if (!client) {
    return runFallbackEngine(business, input.history, input.userMessage);
  }

  try {
    const trimmedHistory = input.history.slice(-MAX_HISTORY_MESSAGES);
    const inputItems: any[] = [
      { role: "system", content: buildSystemPrompt(business) },
      ...trimmedHistory.map((m) => ({ role: m.role, content: m.content })),
      { role: "user", content: input.userMessage },
    ];

    const model = getConfiguredModel(business.aiModel);
    let lastProposal: Record<string, unknown> | null = null;
    let tokensIn = 0;
    let tokensOut = 0;

    for (let step = 0; step < MAX_AGENT_STEPS; step++) {
      const response = await client.responses.create({
        model,
        input: inputItems,
        tools: toolDefinitions as any,
      });

      const usage = (response as any).usage;
      if (usage) {
        tokensIn += usage.input_tokens ?? 0;
        tokensOut += usage.output_tokens ?? 0;
      }

      const output: any[] = (response as any).output ?? [];
      const functionCalls = output.filter((item) => item.type === "function_call");

      if (functionCalls.length === 0) {
        const text =
          (response as any).output_text ??
          output
            .flatMap((item) => item.content ?? [])
            .filter((c: any) => c.type === "output_text")
            .map((c: any) => c.text)
            .join("\n");

        recordAiUsage(business.id, tokensIn, tokensOut);
        return {
          reply: text || "Perdón, no pude generar una respuesta. ¿Puedes reformular tu pregunta?",
          aiConfigured: true,
          proposal: lastProposal,
          error: false,
        };
      }

      // Añadir las llamadas a función al historial de entrada y ejecutar cada una.
      for (const call of functionCalls) {
        inputItems.push(call);
        let result: unknown;
        try {
          const args = call.arguments ? JSON.parse(call.arguments) : {};
          result = runTool(business, call.name, args);
          if (
            result &&
            typeof result === "object" &&
            "proposalType" in (result as Record<string, unknown>)
          ) {
            lastProposal = result as Record<string, unknown>;
          }
        } catch (toolError) {
          logger.error("tool_execution_failed", { tool: call.name, businessId: business.id });
          result = { error: "No se pudo ejecutar la herramienta. Intenta de nuevo." };
        }
        inputItems.push({
          type: "function_call_output",
          call_id: call.call_id,
          output: JSON.stringify(result),
        });
      }
    }

    recordAiUsage(business.id, tokensIn, tokensOut);
    return {
      reply:
        "Estoy revisando varias cosas a la vez y no pude terminar. ¿Puedes decirme de nuevo, más simple, qué necesitas?",
      aiConfigured: true,
      proposal: lastProposal,
      error: false,
    };
  } catch (err) {
    logger.error("ai_provider_error", { businessId: business.id });
    return {
      reply:
        "Tuvimos un problema técnico para responder en este momento. Puedes intentar de nuevo en un momento, o usar el botón para hablar directamente con el negocio.",
      aiConfigured: true,
      proposal: null,
      error: true,
    };
  }
}
