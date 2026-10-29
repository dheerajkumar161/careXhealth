import { createBrowserRouter, Navigate } from "react-router-dom";
import { AREA_ROLES } from "@/lib/constants";
import LoginPage from "@/pages/LoginPage";
import SignupPage from "@/pages/SignupPage";
import DoctorAlerts from "@/pages/doctor/DoctorAlerts";
import DoctorLayout from "@/pages/doctor/DoctorLayout";
import DoctorOverview from "@/pages/doctor/DoctorOverview";
import DoctorPatient from "@/pages/doctor/DoctorPatient";
import DoctorPatients from "@/pages/doctor/DoctorPatients";
import DoctorReferrals from "@/pages/doctor/DoctorReferrals";
import DoctorTests from "@/pages/doctor/DoctorTests";
import NurseAlerts from "@/pages/nurse/NurseAlerts";
import NurseHandoffs from "@/pages/nurse/NurseHandoffs";
import NurseLayout from "@/pages/nurse/NurseLayout";
import NurseOverview from "@/pages/nurse/NurseOverview";
import NursePatient from "@/pages/nurse/NursePatient";
import NursePatients from "@/pages/nurse/NursePatients";
import PatientAppointments from "@/pages/patient/PatientAppointments";
import PatientAssistant from "@/pages/patient/PatientAssistant";
import PatientDocuments from "@/pages/patient/PatientDocuments";
import PatientLayout from "@/pages/patient/PatientLayout";
import PatientPlan from "@/pages/patient/PatientPlan";
import PatientToday from "@/pages/patient/PatientToday";
import ProviderLayout from "@/pages/provider/ProviderLayout";
import ProviderSchedule from "@/pages/provider/ProviderSchedule";
import ProviderTests from "@/pages/provider/ProviderTests";
import SettingsPage from "@/pages/SettingsPage";
import AuditPage from "@/pages/AuditPage";
import AdminLayout from "@/pages/admin/AdminLayout";
import AdminUsers from "@/pages/admin/AdminUsers";
import CaregiverLayout from "@/pages/caregiver/CaregiverLayout";
import JoinPage from "@/pages/JoinPage";
import { PublicOnly, RequireRole } from "./guards";

/** Same URL structure as the Next.js App Router version, so deep links in notifications keep working. */
export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/login" replace /> },
  { path: "/join", element: <JoinPage /> },
  {
    element: <PublicOnly />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/signup", element: <SignupPage /> },
    ],
  },
  {
    element: <RequireRole roles={AREA_ROLES["/doctor"]} />,
    children: [
      {
        path: "/doctor",
        element: <DoctorLayout />,
        children: [
          { index: true, element: <DoctorOverview /> },
          { path: "patients", element: <DoctorPatients /> },
          { path: "patients/:id", element: <DoctorPatient /> },
          { path: "referrals", element: <DoctorReferrals /> },
          { path: "tests", element: <DoctorTests /> },
          { path: "alerts", element: <DoctorAlerts /> },
          { path: "audit", element: <AuditPage /> },
          { path: "settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
  {
    element: <RequireRole roles={AREA_ROLES["/nurse"]} />,
    children: [
      {
        path: "/nurse",
        element: <NurseLayout />,
        children: [
          { index: true, element: <NurseOverview /> },
          { path: "patients", element: <NursePatients /> },
          { path: "patients/:id", element: <NursePatient /> },
          { path: "alerts", element: <NurseAlerts /> },
          { path: "handoffs", element: <NurseHandoffs /> },
          { path: "settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
  {
    element: <RequireRole roles={AREA_ROLES["/patient"]} />,
    children: [
      {
        path: "/patient",
        element: <PatientLayout />,
        children: [
          { index: true, element: <PatientToday /> },
          { path: "plan", element: <PatientPlan /> },
          { path: "appointments", element: <PatientAppointments /> },
          { path: "documents", element: <PatientDocuments /> },
          { path: "assistant", element: <PatientAssistant /> },
          { path: "settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
  {
    element: <RequireRole roles={AREA_ROLES["/provider"]} />,
    children: [
      {
        path: "/provider",
        element: <ProviderLayout />,
        children: [
          { index: true, element: <ProviderTests /> },
          { path: "schedule", element: <ProviderSchedule /> },
          { path: "settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
  {
    element: <RequireRole roles={AREA_ROLES["/caregiver"]} />,
    children: [
      {
        path: "/caregiver",
        element: <CaregiverLayout />,
        children: [
          { index: true, element: <PatientToday /> },
          { path: "plan", element: <PatientPlan /> },
          { path: "appointments", element: <PatientAppointments /> },
          { path: "documents", element: <PatientDocuments /> },
          { path: "settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
  {
    element: <RequireRole roles={AREA_ROLES["/admin"]} />,
    children: [
      {
        path: "/admin",
        element: <AdminLayout />,
        children: [
          { index: true, element: <AuditPage /> },
          { path: "users", element: <AdminUsers /> },
          { path: "settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/login" replace /> },
]);
