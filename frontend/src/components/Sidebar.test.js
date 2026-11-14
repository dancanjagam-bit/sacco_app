import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import api from "../api/axios";
import { AppShell } from "./AppShell";
import AppTopbar from "./AppTopbar";
import AppSidebar from "./AppSidebar";
import WorkspaceSwitcher from "./WorkspaceSwitcher";

jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../api/axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("./SaccoLogo", () => () => <span aria-hidden="true" />);

const workspaces = [
  { id: "member", label: "Member services", short_label: "Member", path: "/dashboard" },
  { id: "crew", label: "Transport crew", short_label: "Crew", path: "/transport/crew" },
  { id: "staff", label: "Staff operations", short_label: "Staff", path: "/admin/dashboard" },
];

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{location.pathname}</output>;
}

function renderMainNavigation(initialPath = "/dashboard") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppShell>
        <div className="app-layout">
          <AppTopbar />
          <div className="app-body">
            <AppSidebar />
            <main id="app-main-content" className="app-main" tabIndex="-1">Content</main>
          </div>
        </div>
      </AppShell>
    </MemoryRouter>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  useAuth.mockReturnValue({
    user: {
      username: "multi_role",
      first_name: "Member",
      permissions: ["accounts.read_own", "loans.read_own", "statements.read_own", "notifications.read_own", "profile.read_own"],
      workspaces: [workspaces[0]],
    },
    logout: jest.fn(),
  });
  api.get.mockResolvedValue({ data: { notifications: [], unread_count: 0 } });
});

test("workspace switcher only uses backend destinations and navigates", async () => {
  const user = { username: "multi_role", workspaces };
  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <WorkspaceSwitcher user={user} />
      <LocationProbe />
    </MemoryRouter>
  );
  expect(screen.getByRole("option", { name: "Crew" })).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Switch workspace" }), { target: { value: "crew" } });
  await waitFor(() => expect(screen.getByLabelText("Current route")).toHaveTextContent("/transport/crew"));
});

test("role labels without backend workspaces cannot expose staff destinations", () => {
  useAuth.mockReturnValue({
    user: {
      username: "title_only",
      staff_role: "chairman",
      is_staff: true,
      permissions: ["accounts.read_own"],
      workspaces: [workspaces[0]],
    },
    logout: jest.fn(),
  });
  renderMainNavigation();
  expect(screen.queryByRole("link", { name: /Operations/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: /Switch workspace/i })).not.toBeInTheDocument();
});

test("collapsed desktop rail and mobile drawer remain accessible", async () => {
  renderMainNavigation();
  fireEvent.click(screen.getByRole("button", { name: /Collapse navigation sidebar/i }));
  const home = screen.getByRole("link", { name: "Home" });
  fireEvent.focus(home);
  expect(await screen.findByRole("tooltip", { name: "Home" })).toBeInTheDocument();

  const menuTrigger = screen.getByRole("button", { name: /Open navigation menu/i });
  fireEvent.click(menuTrigger);
  expect(screen.getByRole("dialog", { name: /Navigation menu/i })).toBeInTheDocument();
  expect(document.querySelector(".app-topbar")).toHaveAttribute("inert");
  expect(document.getElementById("app-main-content")).toHaveAttribute("inert");
  fireEvent.keyDown(document, { key: "Escape" });
  await waitFor(() => expect(document.querySelector(".app-topbar")).not.toHaveAttribute("inert"));
  await waitFor(() => expect(menuTrigger).toHaveFocus());
});

test("notifications retry after a failed load and show empty only after success", async () => {
  api.get
    .mockRejectedValueOnce(new Error("offline"))
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ data: { notifications: [], unread_count: 0 } });
  renderMainNavigation();
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: /^Notifications/i }));
  expect(await screen.findByText("Could not load notifications.")).toBeInTheDocument();
  expect(screen.queryByText("No notifications yet.")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("No notifications yet.")).toBeInTheDocument();
});
