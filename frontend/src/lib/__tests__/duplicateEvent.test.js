// duplicateEvent.test.js — shift math + prefill builder for the redesigned
// duplicate flow (duplicate = prefilled, fully editable create form).
import { describe, expect, it } from "vitest";

import {
  addDaysIso,
  buildDuplicateInitial,
  computeShiftDays,
  defaultTargetQuarterId,
  defaultTargetWeek,
  weekRangeLabel,
  weekStartIso,
} from "../duplicateEvent";

const SPRING = {
  id: "q-spring",
  season: "spring",
  year: 2026,
  start_date: "2026-03-30",
  end_date: "2026-06-14",
  weeks_in_quarter: 11,
  display_name: "Spring 2026",
  archived_at: "2026-06-20T00:00:00Z",
};

const FALL = {
  id: "q-fall",
  season: "fall",
  year: 2026,
  start_date: "2026-09-28",
  end_date: "2026-12-13",
  weeks_in_quarter: 11,
  display_name: "Fall 2026",
  archived_at: null,
};

const SUMMER_A = {
  id: "q-summer-a",
  season: "summer",
  year: 2026,
  start_date: "2026-06-22",
  end_date: "2026-07-31",
  weeks_in_quarter: 6,
  display_name: "Summer 2026 · Session A",
  archived_at: null,
};

// Mid-day UTC times so local-date derivation can't drift a day in any
// test-runner timezone (same convention as EventSettingsModal.test.jsx).
const SOURCE_EVENT = {
  id: "ev-src",
  title: "CRISPR at Franklin",
  description: "Original run",
  location: "Room 12",
  school: "Franklin Elementary",
  visibility: "public",
  max_signups_per_user: 2,
  module_slug: "crispr-1",
  quarter_id: "q-spring",
  week_number: 3,
  start_date: "2026-04-15T12:00:00Z",
  end_date: "2026-04-15T15:00:00Z",
  slots: [
    {
      id: "slot-2",
      slot_type: "period",
      start_time: "2026-04-15T13:30:00Z",
      end_time: "2026-04-15T14:30:00Z",
      capacity: 4,
      location: "Room 13",
      current_count: 3,
    },
    {
      id: "slot-1",
      slot_type: "orientation",
      start_time: "2026-04-15T12:00:00Z",
      end_time: "2026-04-15T13:00:00Z",
      capacity: 10,
      location: null,
      current_count: 1,
    },
  ],
};

function localParts(iso) {
  const d = new Date(iso);
  return {
    date: `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`,
    time: `${d.getHours()}:${d.getMinutes()}`,
  };
}

function plusDaysLocal(iso, days) {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d;
}

describe("addDaysIso / weekStartIso", () => {
  it("adds days across month and year boundaries", () => {
    expect(addDaysIso("2026-03-30", 14)).toBe("2026-04-13");
    expect(addDaysIso("2026-12-28", 7)).toBe("2027-01-04");
    expect(addDaysIso("2026-04-13", -14)).toBe("2026-03-30");
  });

  it("week N starts (N-1) weeks after the quarter start", () => {
    expect(weekStartIso(FALL, 1)).toBe("2026-09-28");
    expect(weekStartIso(FALL, 3)).toBe("2026-10-12");
    expect(weekStartIso(SPRING, 3)).toBe("2026-04-13");
  });
});

describe("computeShiftDays", () => {
  it("aligns week starts across quarters (spring wk3 → fall wk3 = 182 days)", () => {
    expect(
      computeShiftDays({
        sourceEvent: SOURCE_EVENT,
        sourceRow: SPRING,
        targetRow: FALL,
        targetWeek: 3,
      }),
    ).toBe(182);
  });

  it("same-row shifts are whole weeks", () => {
    expect(
      computeShiftDays({
        sourceEvent: SOURCE_EVENT,
        sourceRow: SPRING,
        targetRow: SPRING,
        targetWeek: 5,
      }),
    ).toBe(14);
  });

  it("falls back to the event's own start date when the source row is unknown", () => {
    const orphan = { ...SOURCE_EVENT, quarter_id: null, week_number: null };
    // Event starts 2026-04-15; fall week 3 starts 2026-10-12 → 180 days.
    expect(
      computeShiftDays({
        sourceEvent: orphan,
        sourceRow: null,
        targetRow: FALL,
        targetWeek: 3,
      }),
    ).toBe(180);
  });
});

describe("buildDuplicateInitial", () => {
  it("shifts event and slot datetimes preserving wall-clock time", () => {
    const initial = buildDuplicateInitial(SOURCE_EVENT, 182);

    const src = localParts(SOURCE_EVENT.start_date);
    const dst = localParts(initial.start_date);
    expect(dst.time).toBe(src.time);
    const expected = plusDaysLocal(SOURCE_EVENT.start_date, 182);
    expect(new Date(initial.start_date).getTime()).toBe(expected.getTime());

    expect(initial.slots).toHaveLength(2);
    // Sorted by start time — orientation slot (12:00Z) first.
    expect(initial.slots[0].slot_type).toBe("orientation");
    expect(new Date(initial.slots[0].start_time).getTime()).toBe(
      plusDaysLocal("2026-04-15T12:00:00Z", 182).getTime(),
    );
    expect(localParts(initial.slots[1].end_time).time).toBe(
      localParts("2026-04-15T14:30:00Z").time,
    );
  });

  it("copies the editable fields and strips ids and signup counts", () => {
    const initial = buildDuplicateInitial(SOURCE_EVENT, 182);
    expect(initial.title).toBe("CRISPR at Franklin");
    expect(initial.location).toBe("Room 12");
    expect(initial.school).toBe("Franklin Elementary");
    expect(initial.module_slug).toBe("crispr-1");
    expect(initial.max_signups_per_user).toBe(2);
    for (const slot of initial.slots) {
      expect(slot.id).toBeUndefined();
      expect(slot.current_count).toBeUndefined();
    }
    expect(initial.slots[0].capacity).toBe(10);
    expect(initial.slots[1].location).toBe("Room 13");
    // Missing slot location falls back to empty string, not "null".
    expect(initial.slots[0].location).toBe("");
  });
});

describe("target defaults", () => {
  it("defaults to the quarter containing today, skipping archived rows", () => {
    expect(
      defaultTargetQuarterId([SPRING, SUMMER_A, FALL], "2026-10-01"),
    ).toBe("q-fall");
    expect(
      defaultTargetQuarterId([SPRING, SUMMER_A, FALL], "2026-07-01"),
    ).toBe("q-summer-a");
  });

  it("in a gap, defaults to the next upcoming quarter", () => {
    expect(
      defaultTargetQuarterId([SPRING, SUMMER_A, FALL], "2026-08-15"),
    ).toBe("q-fall");
  });

  it("after everything ended, defaults to the last active quarter", () => {
    expect(
      defaultTargetQuarterId([SPRING, SUMMER_A, FALL], "2027-02-01"),
    ).toBe("q-fall");
  });

  it("cross-quarter default week mirrors the source week, clamped", () => {
    expect(
      defaultTargetWeek({ sourceEvent: SOURCE_EVENT, sourceRow: SPRING, targetRow: FALL }),
    ).toBe(3);
    const wk9 = { ...SOURCE_EVENT, week_number: 9 };
    expect(
      defaultTargetWeek({ sourceEvent: wk9, sourceRow: SPRING, targetRow: SUMMER_A }),
    ).toBe(6);
  });

  it("same-quarter default week bumps to the next week (recurring copy)", () => {
    expect(
      defaultTargetWeek({ sourceEvent: SOURCE_EVENT, sourceRow: SPRING, targetRow: SPRING }),
    ).toBe(4);
  });
});

describe("weekRangeLabel", () => {
  it("labels the week with its calendar range", () => {
    expect(weekRangeLabel(FALL, 3)).toBe("Oct 12 – Oct 18");
  });
});
