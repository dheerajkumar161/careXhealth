export const ROLES = ["DOCTOR", "NURSE", "PATIENT", "TEST_CENTER", "PROVIDER", "ADMIN", "CAREGIVER"] as const;
export type Role = (typeof ROLES)[number];

// Test centers and external care partners share the /provider area
export const ROLE_HOME: Record<Role, string> = {
  DOCTOR: "/doctor",
  NURSE: "/nurse",
  PATIENT: "/patient",
  TEST_CENTER: "/provider",
  PROVIDER: "/provider",
  ADMIN: "/admin",
  CAREGIVER: "/caregiver",
};

export const ROLE_LABEL: Record<Role, string> = {
  DOCTOR: "Doctor",
  NURSE: "Nurse",
  PATIENT: "Patient",
  TEST_CENTER: "Test Center",
  PROVIDER: "Care Partner",
  ADMIN: "Administrator",
  CAREGIVER: "Caregiver",
};

export const AREA_ROLES: Record<string, Role[]> = {
  "/doctor": ["DOCTOR"],
  "/nurse": ["NURSE"],
  "/patient": ["PATIENT"],
  "/provider": ["TEST_CENTER", "PROVIDER"],
  "/admin": ["ADMIN"],
  "/caregiver": ["CAREGIVER"],
};
