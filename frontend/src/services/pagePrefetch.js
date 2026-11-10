import API, { getSchedules } from "./api";
import { prefetchCurriculumData } from "./curriculumCache";

const prefetch = (requests) => requests.forEach(([url, params]) => {
  API.get(url, params ? { params } : {}).catch(() => {});
});

// Called only once navigation is activated, so this
// starts the destination's normal data requests a moment before the page
// mounts. In-flight GET sharing lets the page consume these same requests.
export function prefetchDashboardPage(page, role, { programId } = {}) {
  if (page === "curriculum") prefetchCurriculumData();

  if (page === "schedules" || page === "schedule") {
    getSchedules().catch(() => {});
    prefetch([["/rooms/"], ["/faculty/profiles/"]]);
  } else if (page === "curriculum") {
    prefetch([["/curriculum/programs/"]]);
  } else if (page === "exams") {
    prefetch([["/exams/"], ["/curriculum/subjects/"], ["/engine/sections/"], ["/rooms/"], ["/faculty/profiles/"]]);
  } else if (page === "conflicts") {
    prefetch([["/engine/conflicts/", {}]]);
  } else if (page === "minors") {
    prefetch([
      ["/engine/minor/comparison/", { semester: "1st Sem", year_level: "1st Year" }],
      ["/engine/conflicts/", { semester: "1st Sem" }],
    ]);
  } else if (page === "generate") {
    prefetch([["/curriculum/subjects/"], ["/curriculum/programs/"], ["/engine/sections/"]]);
  } else if (page === "coverage") {
    prefetch([["/faculty/profiles/"], ["/faculty/absences/"]]);
    if (role === "registrar") prefetch([["/engine/scheduling-config/"]]);
  } else if (page === "analytics") {
    prefetch([["/analytics/", {}], ["/engine/workload/", {}]]);
    if (role === "registrar") {
      prefetch([
        ["/analytics/registrar/gened-coverage/", {}], ["/analytics/room-heatmap/", {}],
        ["/analytics/registrar/dependencies/", {}], ["/analytics/capacity/", {}],
      ]);
    }
  } else if (page === "classlists") {
    prefetch([["/engine/students/"], ["/engine/sections/"], ["/curriculum/programs/"]]);
  } else if (page === "availability") {
    prefetch(role === "dean" ? [["/faculty/profiles/roster/"]] : [["/faculty/availability/"]]);
  }

  // The Dean's room overview is the largest schedule-tab dependency.
  if (page === "schedules" && role === "dean") {
    prefetch([["/rooms/dean/overview/", { program_id: programId || undefined }]]);
  }
}
