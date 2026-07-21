/**
 * useQuarters — shared react-query hook for the admin-entered quarter rows
 * (issue #24). One small cacheable list serves week navigation, date
 * presets, the duplicate drawer, and the archived-quarters view.
 *
 * Selectors over the rows live in weekUtils.js (pure, testable).
 */
import { useQuery } from "@tanstack/react-query";

import api from "./api";

export function useQuarters() {
  return useQuery({
    queryKey: ["publicQuarters"],
    queryFn: () => api.public.getQuarters(),
    staleTime: 5 * 60 * 1000,
  });
}
