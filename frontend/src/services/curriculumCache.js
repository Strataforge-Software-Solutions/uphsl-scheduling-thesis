import API from "./api";

const CACHE_TTL_MS = 30_000;
let cachedData = null;
let expiresAt = 0;
let pendingRequest = null;

export function getCachedCurriculumData() {
  return cachedData && Date.now() < expiresAt ? cachedData : null;
}

export function loadCurriculumData() {
  const cached = getCachedCurriculumData();
  if (cached) return Promise.resolve(cached);
  if (pendingRequest) return pendingRequest;

  pendingRequest = Promise.all([
    API.get("/curriculum/subjects/"),
    API.get("/curriculum/academic-fields/"),
  ]).then(([subjects, fields]) => {
    cachedData = { subjects: subjects.data, academicFields: fields.data };
    expiresAt = Date.now() + CACHE_TTL_MS;
    return cachedData;
  }).finally(() => {
    pendingRequest = null;
  });

  return pendingRequest;
}

export function prefetchCurriculumData() {
  loadCurriculumData().catch(() => {});
}

export function updateCurriculumCache(update) {
  if (!cachedData) return;
  cachedData = typeof update === "function" ? update(cachedData) : { ...cachedData, ...update };
  expiresAt = Date.now() + CACHE_TTL_MS;
}

export function invalidateCurriculumCache() {
  cachedData = null;
  expiresAt = 0;
}
