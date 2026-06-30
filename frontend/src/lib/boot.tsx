"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";
import type { Bootstrap } from "./types";

type BootCtx = {
  boot: Bootstrap | null;
  refreshBoot: () => void;
};

const Ctx = createContext<BootCtx>({ boot: null, refreshBoot: () => {} });

export function BootProvider({ children }: { children: React.ReactNode }) {
  const [boot, setBoot] = useState<Bootstrap | null>(null);

  const refreshBoot = useCallback(() => {
    api.bootstrap().then(setBoot).catch(() => {});
  }, []);

  useEffect(() => {
    refreshBoot();
  }, [refreshBoot]);

  return <Ctx.Provider value={{ boot, refreshBoot }}>{children}</Ctx.Provider>;
}

export function useBoot() {
  return useContext(Ctx).boot;
}

export function useBootRefresh() {
  return useContext(Ctx).refreshBoot;
}
