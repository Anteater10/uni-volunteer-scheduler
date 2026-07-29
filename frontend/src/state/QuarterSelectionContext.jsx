// fix/ux-quarter-batch — admin-wide "which quarter am I looking at".
//
// Overview stats and the Events list are quarter-scoped; Manage Quarters is
// where the selection is made. The choice is shared through this context
// (provided by AdminLayout) and persisted in localStorage so it survives
// navigation between admin pages and page reloads.
//
// Selection semantics:
//   - nothing stored          → follow the current quarter (the backend's
//                               active-or-most-recent rule), shown as such
//   - a quarter id stored     → that quarter, archived ones included
//   - the sentinel "all"      → events list shows every quarter; stats fall
//                               back to the current quarter
import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { useQuarters } from "../lib/useQuarters";
import { activeOrRecentQuarter, findQuarterById, quarterContaining } from "../lib/weekUtils";

const STORAGE_KEY = "admin.selectedQuarterId";
export const ALL_QUARTERS = "all";

const QuarterSelectionContext = createContext(null);

function readStored() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

export function QuarterSelectionProvider({ children }) {
  const quartersQ = useQuarters();
  const quarters = useMemo(() => quartersQ.data || [], [quartersQ.data]);
  const [storedId, setStoredId] = useState(readStored);

  const setSelectedQuarterId = useCallback((id) => {
    setStoredId(id || null);
    try {
      if (id) window.localStorage.setItem(STORAGE_KEY, id);
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Private-mode storage failures just lose persistence, not function.
    }
  }, []);

  const value = useMemo(() => {
    const todayIso = new Date().toISOString().slice(0, 10);
    const currentQuarter = activeOrRecentQuarter(quarters, todayIso);
    const viewingAll = storedId === ALL_QUARTERS;
    // A stored id that no longer resolves (deleted quarter) falls back to
    // the current quarter rather than an empty screen.
    const explicit = !viewingAll && storedId ? findQuarterById(quarters, storedId) : null;
    const selectedQuarter = explicit || currentQuarter || null;
    return {
      quarters,
      quartersLoading: quartersQ.isPending,
      viewingAll,
      selectedQuarter,
      selectedQuarterId: selectedQuarter?.id ?? null,
      // Explicit selection ≠ just following the current quarter — the UI
      // uses this to offer a "back to current" affordance.
      isExplicitSelection: Boolean(explicit),
      isViewingCurrent:
        !viewingAll &&
        Boolean(selectedQuarter) &&
        quarterContaining(quarters, todayIso)?.id === selectedQuarter?.id,
      currentQuarter,
      setSelectedQuarterId,
    };
  }, [quarters, quartersQ.isPending, storedId, setSelectedQuarterId]);

  return (
    <QuarterSelectionContext.Provider value={value}>
      {children}
    </QuarterSelectionContext.Provider>
  );
}

// Inert fallback for renders outside the admin shell (mainly bare-page
// tests): no quarters, no selection, setter is a no-op. In the app the
// provider is mounted by AdminLayout, so every admin page gets the real one.
const FALLBACK = {
  quarters: [],
  quartersLoading: false,
  viewingAll: false,
  selectedQuarter: null,
  selectedQuarterId: null,
  isExplicitSelection: false,
  isViewingCurrent: false,
  currentQuarter: null,
  setSelectedQuarterId: () => {},
};

export function useSelectedQuarter() {
  return useContext(QuarterSelectionContext) || FALLBACK;
}
