import { useSyncExternalStore } from "react";
import { ACTIVE_EVENT, getActiveRepository } from "@/lib/intelligenceApi";

function subscribe(onChange: () => void) {
  window.addEventListener(ACTIVE_EVENT, onChange);
  return () => window.removeEventListener(ACTIVE_EVENT, onChange);
}

/** The repository selected on the Repositories page ("" means the bundled demo). */
export function useActiveRepository(): string {
  return useSyncExternalStore(subscribe, getActiveRepository, () => "");
}
