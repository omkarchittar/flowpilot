"use client";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "./api";

export function useResource<T>(path: string | null, pollMs = 0) {
  const [result, setResult] = useState<{
    path: string;
    data?: T;
    error?: string;
  }>({ path: "" });
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const data = await api<T>(path, { signal: controller.signal });
        if (!controller.signal.aborted) setResult({ path, data });
      } catch (error) {
        if (!controller.signal.aborted)
          setResult((previous) => ({
            path,
            data: previous.path === path ? previous.data : undefined,
            error: errorMessage(error),
          }));
      } finally {
        if (pollMs && !controller.signal.aborted)
          timeout = setTimeout(load, pollMs);
      }
    };
    void load();
    return () => {
      controller.abort();
      clearTimeout(timeout);
    };
  }, [path, pollMs, revision]);
  return {
    data: result.path === path ? result.data : undefined,
    error: result.path === path ? result.error : undefined,
    refresh,
  };
}
