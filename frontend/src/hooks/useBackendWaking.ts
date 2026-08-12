import { useEffect, useState } from "react";
import { setSlowRequestHandler } from "../api";

export function useBackendWaking(): boolean {
  const [isWaking, setIsWaking] = useState(false);

  useEffect(() => {
    setSlowRequestHandler(setIsWaking);
    return () => setSlowRequestHandler(null);
  }, []);

  return isWaking;
}
