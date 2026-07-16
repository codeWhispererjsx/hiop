/* eslint-disable react-hooks/refs, react-hooks/set-state-in-effect */
import { useCallback, useEffect, useRef, useState } from "react";
export function useRequest<T>(loader: () => Promise<T>, _deps: unknown[] = []) {
  const dependencyKey = JSON.stringify(_deps);
  const [data, setData] = useState<T | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const requestVersion = useRef(0);
  const loaderRef = useRef(loader); loaderRef.current = loader;
  const reload = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true); setError("");
    try {
      const result = await loaderRef.current();
      if (version === requestVersion.current) setData(result);
    } catch (e) {
      if (version === requestVersion.current) setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, []);
  useEffect(() => { void reload(); return () => { requestVersion.current += 1; }; }, [reload, dependencyKey]);
  return { data, setData, loading, error, reload };
}
