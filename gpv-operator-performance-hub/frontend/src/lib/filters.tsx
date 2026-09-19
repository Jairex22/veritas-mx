import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

interface GlobalFilters {
  periodDays: number;
  shift: string;
  setPeriodDays: (v: number) => void;
  setShift: (v: string) => void;
}

const FiltersContext = createContext<GlobalFilters | undefined>(undefined);
const STORAGE_KEY = "gpv_filters";

export function FiltersProvider({ children }: { children: ReactNode }) {
  const [periodDays, setPeriodDays] = useState<number>(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw).periodDays ?? 30 : 30;
  });
  const [shift, setShift] = useState<string>(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw).shift ?? "" : "";
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ periodDays, shift }));
  }, [periodDays, shift]);

  return (
    <FiltersContext.Provider value={{ periodDays, shift, setPeriodDays, setShift }}>
      {children}
    </FiltersContext.Provider>
  );
}

export function useFilters() {
  const ctx = useContext(FiltersContext);
  if (!ctx) throw new Error("useFilters debe usarse dentro de FiltersProvider");
  return ctx;
}
