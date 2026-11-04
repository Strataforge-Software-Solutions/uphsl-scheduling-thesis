/* Subject-kind labels shown to users. The data still stores "major" / "minor"; people see
   "Gen Ed" for minor subjects and the actual program name (e.g. "BS Computer Science") for major ones. */
export const GEN_ED = "Gen Ed";

export function kindLabel(classification, programName) {
  if (classification === "minor") return GEN_ED;
  return programName || "Program subject";
}

/* Options for a "which subjects?" dropdown: both / program only / Gen Ed only. */
export function kindFilterOptions(programName) {
  const prog = programName || "Program subjects";
  return [
    { value: "", label: `${prog} & ${GEN_ED}` },
    { value: "major", label: `${prog} only` },
    { value: "minor", label: `${GEN_ED} only` },
  ];
}
