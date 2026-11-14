/**
 * AppNavigation.test.js
 *
 * Tests for the new two-panel shell: AppShell + AppTopbar + AppSidebar + SearchDialog.
 * We test observable behaviour, not implementation details.
 */
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useShell } from "./AppShell";
import { MemoryRouter } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import api from "../api/axios";
import AppTopbar from "./AppTopbar";
import AppSidebar from "./AppSidebar";
import SearchDialog from "./SearchDialog";
import { AppShell } from "./AppShell";

jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../api/axios", () => ({ get: jest.fn(), post: jest.fn() }));
// SaccoLogo renders an img via PUBLIC_URL; stub it in tests.
jest.mock("./SaccoLogo", () => () => <span data-testid="sacco-logo" />);

// ── Helpers ────────────────────────────────────────────────────────────────
function renderInShell(ui, { initialPath = "/dashboard" } = {}) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppShell>{ui}</AppShell>
    </MemoryRouter>
  );
}

function renderNav({ initialPath = "/dashboard" } = {}) {
  return renderInShell(
    <>
      <AppTopbar />
      <AppSidebar />
    </>,
    { initialPath }
  );
}

// Render the shell with the SearchDialog included so it can read searchOpen from context.
function renderFull({ initialPath = "/dashboard", isStaff = false } = {}) {
  useAuth.mockReturnValue({
    user: {
      username: "alice",
      first_name: "Alice",
      transport_roles: [],
      is_staff: isStaff,
      is_admin: isStaff,
      is_superuser: false,
      permissions: isStaff ? ["staff.console", "members.review", "loans.appraise"] : [
        "accounts.read_own", "loans.read_own", "statements.read_own", "notifications.read_own", "profile.read_own",
      ],
      workspaces: isStaff
        ? [
            { id: "member", label: "Member services", short_label: "Member", path: "/dashboard" },
            { id: "staff", label: "Staff operations", short_label: "Staff", path: "/admin/dashboard" },
          ]
        : [{ id: "member", label: "Member services", short_label: "Member", path: "/dashboard" }],
    },
    logout: jest.fn(),
  });
  return renderInShell(
    <>
      <AppTopbar />
      <AppSidebar />
      <SearchDialog />
    </>,
    { initialPath }
  );
}

const memberUser = {
  username: "alice",
  first_name: "Alice",
  transport_roles: [],
  is_staff: false,
  is_admin: false,
  is_superuser: false,
  permissions: [
    "accounts.read_own", "loans.read_own", "statements.read_own", "payments.initiate_own",
    "notifications.read_own", "profile.read_own",
  ],
  workspaces: [{ id: "member", label: "Member services", short_label: "Member", path: "/dashboard" }],
};

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  // Most tests do not inspect notifications. Keep this request pending so a
  // fast mock response cannot update AppTopbar after a synchronous assertion.
  api.get.mockImplementation(() => new Promise(() => {}));
  useAuth.mockReturnValue({ user: memberUser, logout: jest.fn() });
});

// ── AppShell context sanity check ──────────────────────────────────────────
describe("AppShell context", () => {
  test("setSearchOpen propagates to consumers in the same tree", async () => {
    function Consumer() {
      const { searchOpen, setSearchOpen } = useShell();
      return (
        <>
          <button onClick={() => setSearchOpen(true)}>open</button>
          {searchOpen && <div role="status">open</div>}
        </>
      );
    }
    render(
      <MemoryRouter>
        <AppShell><Consumer /></AppShell>
      </MemoryRouter>
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "open" }));
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });
});

// ── AppTopbar ────────────────────────────────────────────────────────────────
describe("AppTopbar", () => {
  test("renders brand link pointing to member dashboard for a plain member", () => {
    renderNav();
    expect(
      screen.getByRole("link", { name: /Nairobi West Transport Cooperative/i })
    ).toHaveAttribute("href", "/dashboard");
  });

  test("brand link points to admin dashboard when on a staff path", () => {
    useAuth.mockReturnValue({
      user: {
        ...memberUser,
        is_staff: true,
        is_admin: true,
        permissions: [...memberUser.permissions, "staff.manage"],
        workspaces: [...memberUser.workspaces, { id: "staff", label: "Staff operations", short_label: "Staff", path: "/admin/dashboard" }],
      },
      logout: jest.fn(),
    });
    renderNav({ initialPath: "/admin/dashboard" });
    expect(
      screen.getByRole("link", { name: /Nairobi West Transport Cooperative/i })
    ).toHaveAttribute("href", "/admin/dashboard");
  });

  test("search button is present and accessible", () => {
    renderNav();
    expect(screen.getByRole("button", { name: /Search/i })).toBeInTheDocument();
  });

  test("topbar identifies the active page and workspace", () => {
    renderNav({ initialPath: "/dashboard" });
    expect(screen.getByLabelText("Current page and workspace")).toHaveTextContent("Home");
    expect(screen.getByLabelText("Current page and workspace")).toHaveTextContent("Member workspace");
  });

  test("desktop menu control collapses and expands the shared navigation rail", () => {
    renderNav();
    const shell = document.querySelector(".app-shell-root");
    const collapse = screen.getByRole("button", { name: "Collapse navigation sidebar" });
    fireEvent.click(collapse);
    expect(shell).toHaveAttribute("data-sidebar-collapsed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Expand navigation sidebar" }));
    expect(shell).toHaveAttribute("data-sidebar-collapsed", "false");
  });

  test("notification badge reflects unread count from server", async () => {
    api.get.mockResolvedValueOnce({ data: { notifications: [], unread_count: 5 } });
    renderNav();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /5 unread/i })).toBeInTheDocument()
    );
  });

  test("account menu opens on click with profile and sign-out items", () => {
    renderNav();
    fireEvent.click(screen.getByRole("button", { name: /Account menu for Alice/i }));
    expect(screen.getByRole("menu", { name: /Account menu/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Profile/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Sign out/i })).toBeInTheDocument();
  });

  test("account menu closes with Escape and returns focus to its trigger", async () => {
    renderNav();
    const trigger = screen.getByRole("button", { name: /Account menu for Alice/i });
    fireEvent.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  test("workspace switcher absent for single-workspace member", () => {
    renderNav();
    expect(
      screen.queryByRole("combobox", { name: /switch workspace/i })
    ).not.toBeInTheDocument();
  });

  test("workspace switcher present for multi-workspace staff user", () => {
    useAuth.mockReturnValue({
      user: {
        ...memberUser,
        is_staff: true,
        is_admin: true,
        permissions: [...memberUser.permissions, "staff.console"],
        workspaces: [...memberUser.workspaces, { id: "staff", label: "Staff operations", short_label: "Staff", path: "/admin/dashboard" }],
      },
      logout: jest.fn(),
    });
    renderNav({ initialPath: "/admin/dashboard" });
    expect(
      screen.getByRole("combobox", { name: /switch workspace/i })
    ).toBeInTheDocument();
  });

  test("account menu exposes backend-approved workspace switching", () => {
    useAuth.mockReturnValue({
      user: {
        ...memberUser,
        permissions: [...memberUser.permissions, "staff.console"],
        workspaces: [...memberUser.workspaces, { id: "staff", label: "Staff operations", short_label: "Staff", path: "/admin/dashboard" }],
      },
      logout: jest.fn(),
    });
    renderNav();
    fireEvent.click(screen.getByRole("button", { name: /Account menu/i }));
    expect(screen.getAllByText("Switch workspace")).toHaveLength(2);
    expect(screen.getByRole("menuitemradio", { name: /Staff operations/i })).toBeInTheDocument();
  });

  test("quick actions navigate to workflows and do not post or approve transactions", () => {
    renderNav();
    fireEvent.click(screen.getByRole("button", { name: /Quick actions/i }));
    expect(screen.getByRole("menu", { name: /Quick actions/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Make a deposit/i })).toHaveAttribute("href", "/savings");
    expect(screen.getByRole("menuitem", { name: /Apply for a loan/i })).toHaveAttribute("href", "/loans");
    expect(screen.queryByText(/disburse|approve/i)).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  test("notification panel shows error state when first fetch fails, then recovers", async () => {
    // First call (auto-fetch on mount) fails → notifState="error".
    // Second call (Retry button) succeeds.
    api.get
      .mockRejectedValueOnce(new Error("offline"))
      .mockRejectedValueOnce(new Error("still offline"))
      .mockResolvedValueOnce({ data: { notifications: [], unread_count: 0 } });

    renderNav();
    // Wait for mount-fetch to settle
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));

    // Open panel — error state is already set from the failed mount fetch
    fireEvent.click(screen.getByRole("button", { name: /^Notifications/i }));
    expect(
      await screen.findByText((text) => text.includes("Could not load notifications"))
    ).toBeInTheDocument();

    // Retry succeeds
    fireEvent.click(screen.getByRole("button", { name: /Retry/i }));
    expect(await screen.findByText(/No notifications yet/i)).toBeInTheDocument();
  });
});

// ── AppSidebar ────────────────────────────────────────────────────────────────
describe("AppSidebar", () => {
  test("member sees member nav links (Home, Savings, Loans)", () => {
    renderNav({ initialPath: "/dashboard" });
    expect(screen.getByRole("link", { name: /^Home$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Savings and shares/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Loans$/i })).toBeInTheDocument();
    // Staff-only items must not appear
    expect(screen.queryByRole("link", { name: /Operations/i })).not.toBeInTheDocument();
  });

  test("system manager sees system actions without receiving member-review authority", () => {
    useAuth.mockReturnValue({
      user: {
        ...memberUser,
        is_staff: true,
        is_admin: true,
        staff_role: "accountant",
        permissions: [...memberUser.permissions, "staff.manage"],
        workspaces: [...memberUser.workspaces, { id: "staff", label: "Staff operations", short_label: "Staff", path: "/admin/dashboard" }],
      },
      logout: jest.fn(),
    });
    renderNav({ initialPath: "/admin/dashboard" });
    expect(screen.getByRole("link", { name: /System overview/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Transport management/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Membership review/i })).not.toBeInTheDocument();
  });

  test("superadmin sees Staff management and Audit log links", () => {
    useAuth.mockReturnValue({
      user: {
        ...memberUser,
        is_staff: true,
        is_admin: true,
        is_superuser: true,
        staff_role: "superadmin",
        permissions: [...memberUser.permissions, "staff.manage", "audit.log.read"],
        workspaces: [...memberUser.workspaces, { id: "staff", label: "Staff operations", short_label: "Staff", path: "/admin/dashboard" }],
      },
      logout: jest.fn(),
    });
    renderNav({ initialPath: "/admin/dashboard" });
    expect(screen.getByRole("link", { name: /Staff accounts/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Audit log/i })).toBeInTheDocument();
  });

  test("driver on /transport/crew path sees Shift link", () => {
    useAuth.mockReturnValue({
      user: {
        ...memberUser,
        transport_roles: ["driver"],
        permissions: [...memberUser.permissions, "transport.read_assigned"],
        workspaces: [...memberUser.workspaces, { id: "crew", label: "Transport crew", short_label: "Crew", path: "/transport/crew" }],
      },
      logout: jest.fn(),
    });
    renderNav({ initialPath: "/transport/crew" });
    expect(screen.getByRole("link", { name: /Shift/i })).toBeInTheDocument();
  });

  test("active route link carries aria-current=page", () => {
    renderNav({ initialPath: "/savings" });
    expect(
      screen.getByRole("link", { name: /Savings and shares/i })
    ).toHaveAttribute("aria-current", "page");
  });

  test("desktop collapse button is present", () => {
    renderNav();
    expect(
      screen.getByRole("button", { name: /Collapse navigation sidebar/i })
    ).toBeInTheDocument();
  });

  test("sidebar gains is-collapsed class when collapse button is clicked", async () => {
    renderNav();
    const collapseBtn = screen.getByRole("button", { name: /Collapse navigation sidebar/i });
    const sidebar = document.getElementById("app-sidebar");
    expect(sidebar).not.toHaveClass("is-collapsed");
    fireEvent.click(collapseBtn);
    await waitFor(() => expect(sidebar).toHaveClass("is-collapsed"));
  });

  test("collapsed navigation tooltip appears on keyboard focus", async () => {
    renderNav();
    fireEvent.click(screen.getByRole("button", { name: /Collapse navigation sidebar/i }));
    const homeLink = screen.getByRole("link", { name: /^Home$/i });
    fireEvent.focus(homeLink);
    expect(await screen.findByRole("tooltip", { name: "Home" })).toBeInTheDocument();
    expect(homeLink).toHaveAttribute("aria-describedby", "nav-tooltip-dashboard");
  });

  test("mobile drawer makes the background inert and Escape restores focus", async () => {
    renderInShell(
      <div className="app-layout">
        <AppSidebar />
        <div className="app-content-region">
          <AppTopbar />
          <main className="app-main" id="app-main-content">Member content</main>
        </div>
      </div>
    );
    const trigger = screen.getByRole("button", { name: /Open navigation menu/i });
    fireEvent.click(trigger);
    expect(document.querySelector(".app-topbar")).toHaveAttribute("inert");
    expect(document.getElementById("app-main-content")).toHaveAttribute("inert");
    expect(screen.getByRole("dialog", { name: /Navigation menu/i })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(document.querySelector(".app-topbar")).not.toHaveAttribute("inert"));
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});

// ── SearchDialog ───────────────────────────────────────────────────────────
describe("SearchDialog", () => {
  // The SearchDialog reads `searchOpen` from AppShell context.
  // We use a minimal wrapper that exposes a plain open button — bypassing
  // the topbar — so the test is isolated from topbar notification fetches.
  function SearchTestWrapper() {
    const { setSearchOpen } = useShell();
    return (
      <>
        <button onClick={() => setSearchOpen(true)}>Open search</button>
        <SearchDialog />
      </>
    );
  }

  function renderSearch({ isStaff = false } = {}) {
    useAuth.mockReturnValue({
      user: {
        ...memberUser,
        is_staff: isStaff,
        is_admin: isStaff,
        permissions: isStaff ? [...memberUser.permissions, "staff.console", "members.review"] : memberUser.permissions,
        workspaces: isStaff
          ? [...memberUser.workspaces, { id: "staff", label: "Staff operations", short_label: "Staff", path: "/admin/dashboard" }]
          : memberUser.workspaces,
      },
      logout: jest.fn(),
    });
    render(
      <MemoryRouter>
        <AppShell>
          <SearchTestWrapper />
        </AppShell>
      </MemoryRouter>
    );
    // Open the dialog
    fireEvent.click(screen.getByRole("button", { name: "Open search" }));
  }

  test("dialog is accessible with role=dialog and label", async () => {
    renderSearch();
    expect(
      await screen.findByRole("dialog", { name: /Search navigation/i })
    ).toBeInTheDocument();
  });

  test("shows Quick navigation header when query is empty", async () => {
    renderSearch();
    await screen.findByRole("dialog");
    expect(screen.getByText(/Quick navigation/i)).toBeInTheDocument();
    expect(screen.getAllByRole("option").length).toBeGreaterThan(0);
  });

  test("typing filters results to matching pages", async () => {
    renderSearch();
    const input = await screen.findByRole("searchbox");
    fireEvent.change(input, { target: { value: "loan" } });
    await waitFor(() => {
      const results = screen.getAllByRole("option");
      expect(
        results.some((r) => r.textContent.toLowerCase().includes("loan"))
      ).toBe(true);
    });
  });

  test("staff-only pages hidden from plain member", async () => {
    renderSearch({ isStaff: false });
    const input = await screen.findByRole("searchbox");
    fireEvent.change(input, { target: { value: "operations" } });
    await waitFor(() => {
      expect(screen.queryByText(/Staff.*Operations/i)).not.toBeInTheDocument();
    });
  });

  test("is_staff flag alone does not add staff routes to navigation search", async () => {
    useAuth.mockReturnValue({
      user: { ...memberUser, is_staff: true, permissions: memberUser.permissions, workspaces: memberUser.workspaces },
      logout: jest.fn(),
    });
    render(
      <MemoryRouter>
        <AppShell><SearchTestWrapper /></AppShell>
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole("button", { name: "Open search" }));
    const input = await screen.findByRole("searchbox");
    fireEvent.change(input, { target: { value: "operations" } });
    expect(await screen.findByText(/No permitted pages found/i)).toBeInTheDocument();
  });

  test("Escape closes the dialog", async () => {
    renderSearch();
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("ArrowDown moves highlight from first to second result", async () => {
    renderSearch();
    await screen.findByRole("searchbox");
    const optionsBefore = screen.getAllByRole("option");
    expect(optionsBefore[0].querySelector("button")).toHaveClass("is-focused");
    fireEvent.keyDown(document, { key: "ArrowDown" });
    const optionsAfter = screen.getAllByRole("option");
    expect(optionsAfter[1].querySelector("button")).toHaveClass("is-focused");
  });

  test("footer contains keyboard shortcut hints", async () => {
    renderSearch();
    await screen.findByRole("dialog");
    const footer = document.querySelector(".search-dialog-footer");
    expect(footer).not.toBeNull();
    expect(footer.textContent).toMatch(/navigate/i);
    expect(footer.textContent).toMatch(/open/i);
  });
});
