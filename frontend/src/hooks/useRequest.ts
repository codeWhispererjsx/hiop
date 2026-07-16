/* eslint-disable react-hooks/refs, react-hooks/set-state-in-effect */
import { useCallback, useEffect, useRef, useState } from "react";
export function useRequest<T>(loader: () => Promise<T>, _deps: unknown[] = []) {
  const dependencyKey = JSON.stringify(_deps);
  const [data, setData] = useState<T | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const loaderRef = useRef(loader); loaderRef.current = loader;
  const reload = useCallback(async () => { setLoading(true); setError(""); try { setData(await loaderRef.current()); } catch (e) { setError(e instanceof Error ? e.message : "Request failed"); } finally { setLoading(false); } }, []);
  useEffect(() => { void reload(); }, [reload, dependencyKey]);
  return { data, setData, loading, error, reload };
}
