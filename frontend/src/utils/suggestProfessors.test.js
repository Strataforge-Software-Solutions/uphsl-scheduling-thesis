import { fits, rankProfessors } from "./suggestProfessors";

const h = (x) => x * 60;
const T = (id, free, extra = {}) => ({ id, label: `T${id}`, current_hours: 0, max_hours: 24, free, preferred: {}, ...extra });
const row = { blocks: [180], sections: 1, total_hours: 3 };

test("a teacher whose free time holds the block is suggested, with why", () => {
  const { suggested, others } = rankProfessors([T(1, { Tue: [[h(8), h(12)]] })], row, null);
  expect(others).toEqual([]);
  expect(suggested[0].why).toBe("Free Tue 8:00 AM-12:00 PM · 0 of 24 hrs");
});

test("the Dean's Start-End range is respected", () => {
  const t = T(1, { Tue: [[h(8), h(12)]] });
  expect(rankProfessors([t], row, [h(13), h(17)]).others[0].badge).toBe("No matching free time");
  expect(rankProfessors([t], row, [h(9), h(12)]).suggested.length).toBe(1);
  expect(rankProfessors([t], row, [h(10), h(12)]).suggested.length).toBe(0);      // only 2 h left inside the range
});

test("every section needs its own block", () => {
  expect(fits([{ day: "Tue", a: h(8), b: h(12) }], [180], 2)).toBe(false);
  expect(fits([{ day: "Tue", a: h(8), b: h(12) }, { day: "Wed", a: h(13), b: h(16) }], [180], 2)).toBe(true);
});

test("over the weekly limit is not suggested but stays listed", () => {
  const t = T(1, { Mon: [[h(7), h(20)]] }, { current_hours: 22 });
  const r = rankProfessors([t], row, null);
  expect(r.suggested).toEqual([]);
  expect(r.others[0].badge).toBe("Over weekly limit (25 of 24 hrs)");
  expect(rankProfessors([T(2, { Mon: [[h(7), h(20)]] }, { current_hours: 18 })], row, null, () => 4).others[0].badge).toMatch(/Over weekly limit/);
});

test("preferred-time overlap ranks first, then the lower load", () => {
  const free = { Mon: [[h(7), h(12)]] };
  const a = T(1, free, { current_hours: 2 }), b = T(2, free, { current_hours: 10, preferred: { Mon: [[h(8), h(11)]] } }), c = T(3, free, { current_hours: 1 });
  expect(rankProfessors([a, b, c], row, null).suggested.map((s) => s.teacher.id)).toEqual([2, 3, 1]);
});
