import { useEffect, useState } from "react";
import { api } from "./api";

export type Features = { change_management: boolean; problem_management: boolean };

const disabled: Features = { change_management: false, problem_management: false };
let cached: Promise<Features> | null = null;

// Frozen modules stay hidden when the server cannot be asked.
export function loadFeatures(): Promise<Features> {
  cached ??= api<Features>("/features").catch(() => { cached = null; return disabled; });
  return cached;
}

export function useFeatures(): Features | null {
  const [features, setFeatures] = useState<Features | null>(null);
  useEffect(() => {
    let active = true;
    void loadFeatures().then((value) => { if (active) setFeatures(value); });
    return () => { active = false; };
  }, []);
  return features;
}
