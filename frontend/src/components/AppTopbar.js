import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { availableWorkspaces, workspaceForPath } from "../auth/portalDestination";
import { useShell } from "./AppShell";
import api from "../api/axios";
import Icon from "./ui/Icon";
import StatusBadge from "./ui/StatusBadge";
import SaccoLogo from "./SaccoLogo";
import { navigationFor, ROUTES } from "../navigation/routes";

// ── AppTopbar ────────────────────────────────────────────────────────────────
// Sticky top bar: menu toggle | search | workspace | bell | account.
// The cooperative identity lives in the full-height sidebar on desktop.

export default function AppTopbar() {
  const { user, logout } = useAuth();
  const { collapsed, setCollapsed, mobileOpen, setMobileOpen, setSearchOpen, menuTriggerRef, searchTriggerRef } = useShell();
  const navigate  = useNavigate();
  const location  = useLocation();

  const [openMenu, setOpenMenu]           = useState("");
  const [notifState, setNotifState]       = useState("idle");
  const [notifications, setNotifications] = useState([]);
  const [unread, setUnread]               = useState(null);
  const [actionError, setActionError]     = useState("");

  const menuWrapRef  = useRef(null);
  const panelRef     = useRef(null);
  const triggerRefs  = useRef({});
  const mountedRef   = useRef(false);

  const currentWorkspace = workspaceForPath(user, location.pathname) || "member";
  const isStaffArea = currentWorkspace === "staff" || ["clerk", "credit_officer", "treasurer", "secretary", "chairman", "kyc_reviewer", "welfare_officer"].includes(currentWorkspace);
  const isCrewArea  = currentWorkspace === "crew";
  const initials    = (user?.first_name || user?.username || "U").trim().charAt(0).toUpperCase();
  const workspaces  = availableWorkspaces(user);

  const currentPage = navigationFor(user, currentWorkspace)
    .flatMap((group) => group.items)
    .find((item) => location.pathname === item.to || location.pathname.startsWith(`${item.to}/`));
  const workspaceLabel = workspaces.find((workspace) => workspace.id === currentWorkspace)?.shortLabel;
  const quickActions = currentWorkspace === "staff"
    ? [
        { label: "Open transport operations", to: ROUTES.adminTransport, permission: "staff.manage", icon: "truck" },
        { label: "Manage roles and duties", to: ROUTES.adminAccess, permission: "staff.manage", icon: "shield" },
        { label: "View audit log", to: ROUTES.adminAuditLog, permission: "audit.log.read", icon: "receipt" },
      ].filter((action) => Array.isArray(user?.permissions) && user.permissions.includes(action.permission))
    : currentWorkspace === "crew"
      ? [{ label: "Open my shift", to: ROUTES.transportCrew, permission: "transport.read_assigned", icon: "bus" }]
      : [
          { label: "Make a deposit", to: ROUTES.savings, permission: "payments.initiate_own", icon: "wallet" },
          { label: "Apply for a loan", to: ROUTES.loans, permission: "loans.read_own", icon: "bank" },
          { label: "View statements", to: ROUTES.transactions, permission: "statements.read_own", icon: "file" },
        ].filter((action) => Array.isArray(user?.permissions) && user.permissions.includes(action.permission));

  // ── Notifications ──────────────────────────────────────────────────────────
  const loadNotifications = useCallback(async () => {
    if (!mountedRef.current) return;
    setNotifState("loading");
    setActionError("");
    try {
      const res = await api.get("notifications/");
      if (!Array.isArray(res.data?.notifications) || !Number.isInteger(res.data?.unread_count)) {
        throw new Error("bad response");
      }
      if (!mountedRef.current) return;
      setNotifications(res.data.notifications.slice(0, 6));
      setUnread(res.data.unread_count);
      setNotifState("ready");
    } catch {
      if (mountedRef.current) setNotifState("error");
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Auto-refresh every 30 s.
  useEffect(() => {
    loadNotifications();
    const interval = window.setInterval(loadNotifications, 30_000);
    return () => window.clearInterval(interval);
  }, [loadNotifications]);

  const markRead = async (notification) => {
    setActionError("");
    try {
      if (!notification.is_read) await api.post(`notifications/${notification.id}/read/`);
      setNotifications((items) =>
        items.map((item) => item.id === notification.id ? { ...item, is_read: true } : item)
      );
      if (!notification.is_read) setUnread((c) => Math.max(0, (c || 0) - 1));
      setOpenMenu("");
      if (notification.link) navigate(notification.link);
    } catch {
      setActionError("Could not update this notification. Try again.");
    }
  };

  const markAllRead = async () => {
    setActionError("");
    try {
      await api.post("notifications/read-all/");
      setNotifications((items) => items.map((item) => ({ ...item, is_read: true })));
      setUnread(0);
    } catch {
      setActionError("Could not mark notifications as read.");
    }
  };

  // ── Menu open/close helpers ───────────────────────────────────────────────
  const toggleMenu = (name) => {
    setOpenMenu((prev) => {
      if (prev === name) return "";
      if (name === "notifications") loadNotifications();
      return name;
    });
  };

  // Close menus on route change.
  useEffect(() => { setOpenMenu(""); }, [location.pathname]);

  // Click-outside & Escape.
  useEffect(() => {
    if (!openMenu) return;
    function handler(event) {
      if (event.type === "keydown" && event.key === "Escape") {
        const name = openMenu;
        setOpenMenu("");
        triggerRefs.current[name]?.focus();
        return;
      }
      if (event.type === "mousedown" && menuWrapRef.current && !menuWrapRef.current.contains(event.target)) {
        setOpenMenu("");
      }
    }
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", handler);
    };
  }, [openMenu]);

  // Arrow-key navigation inside open panels.
  useEffect(() => {
    if (!openMenu || !panelRef.current) return;
    function handler(event) {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const items = Array.from(
        panelRef.current.querySelectorAll("a[href], button:not([disabled])")
      ).filter((el) => el.getClientRects().length > 0);
      if (!items.length) return;
      const idx = items.indexOf(document.activeElement);
      const next = event.key === "ArrowDown"
        ? items[(idx + 1) % items.length]
        : items[(idx - 1 + items.length) % items.length];
      event.preventDefault();
      next.focus();
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [openMenu]);

  // Focus first item when panel opens.
  useEffect(() => {
    if (!openMenu || !panelRef.current) return;
    window.requestAnimationFrame(() => {
      const first = panelRef.current?.querySelector("a[href], button:not([disabled])");
      first?.focus();
    });
  }, [openMenu]);

  const handleLogout = async () => {
    setOpenMenu("");
    await logout();
    navigate("/", { replace: true });
  };

  // ── Workspace switch ───────────────────────────────────────────────────────
  const switchWorkspace = (id) => {
    const ws = workspaces.find((w) => w.id === id);
    if (ws) {
      try { localStorage.setItem("sacco_workspace", ws.id); } catch { /* optional preference */ }
      setOpenMenu(""); navigate(ws.path);
    }
  };

  return (
    <header className="app-topbar" role="banner">
      {/* Skip link */}
      <a className="skip-to-content" href="#app-main-content">Skip to content</a>

      {/* Desktop menu control collapses the rail; mobile opens the drawer. */}
      <button
        type="button"
        className="app-topbar-menu-btn desktop-only"
        aria-label={collapsed ? "Expand navigation sidebar" : "Collapse navigation sidebar"}
        aria-controls="app-sidebar"
        aria-expanded={!collapsed}
        onClick={() => setCollapsed((value) => !value)}
      >
        <Icon name="menu" size={19} />
        <span>Menu</span>
      </button>

      <button
        type="button"
        className="app-topbar-icon-btn app-menu-toggle mobile-only"
        aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
        aria-controls="app-sidebar"
        aria-expanded={mobileOpen}
        ref={menuTriggerRef}
        onClick={() => setMobileOpen((v) => !v)}
      >
        <Icon name={mobileOpen ? "close" : "menu"} size={20} />
      </button>

      {/* Compact identity appears only beside the menu on small screens. */}
      <div className="app-topbar-mobile-brand" aria-hidden="true">
        <span className="app-topbar-mark" aria-hidden="true">
          <SaccoLogo size={28} variant="light" />
        </span>
        <span className="app-topbar-name">
          <strong>Nairobi West</strong>
        </span>
      </div>

      {/* Search trigger */}
      <button
        ref={searchTriggerRef}
        type="button"
        className="app-topbar-search-btn"
        onClick={() => setSearchOpen(true)}
        aria-label="Search — press Ctrl K"
      >
        <Icon name="search" size={16} />
        <span className="app-topbar-search-label">Search…</span>
        <kbd className="app-topbar-kbd" aria-hidden="true">Ctrl K</kbd>
      </button>

      <div className="app-topbar-context" aria-label="Current page and workspace">
        <strong>{currentPage?.label || (isStaffArea ? "Staff operations" : isCrewArea ? "Transport crew" : "Member services")}</strong>
        <span>{workspaceLabel || (isStaffArea ? "Staff" : isCrewArea ? "Crew" : "Member")} workspace</span>
      </div>

      {/* Right-side tools */}
      <div className="app-topbar-tools" ref={menuWrapRef}>

        {/* Workspace switcher — only when multiple workspaces available */}
        {workspaces.length > 1 && (
          <label className="app-topbar-ws app-topbar-ws-desktop">
            <span className="sr-only">Switch workspace</span>
            <select
              value={workspaces.some((w) => w.id === currentWorkspace) ? currentWorkspace : (workspaces[0]?.id || "")}
              onChange={(e) => switchWorkspace(e.target.value)}
              aria-label="Switch workspace"
            >
              {workspaces.map((ws) => (
                <option key={ws.id} value={ws.id}>{ws.shortLabel || ws.label}</option>
              ))}
            </select>
          </label>
        )}

        {quickActions.length > 0 && (
          <div className="app-topbar-menu-wrap app-quick-actions-wrap">
            <button
              ref={(el) => { triggerRefs.current.quick = el; }}
              type="button"
              className="app-topbar-quick-btn"
              aria-haspopup="menu"
              aria-expanded={openMenu === "quick"}
              aria-controls="topbar-quick-panel"
              onClick={() => toggleMenu("quick")}
            >
              <Icon name="plus" size={17} />
              <span>Quick actions</span>
            </button>
            {openMenu === "quick" && (
              <div
                id="topbar-quick-panel"
                className="app-topbar-panel app-quick-panel"
                role="menu"
                aria-label="Quick actions"
                ref={panelRef}
              >
                {quickActions.map((action) => (
                  <NavLink
                    key={action.label}
                    role="menuitem"
                    className="app-panel-link"
                    to={action.to}
                    onClick={() => setOpenMenu("")}
                  >
                    <Icon name={action.icon} size={16} /> {action.label}
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Notification bell */}
        <div className="app-topbar-menu-wrap">
          <button
            ref={(el) => { triggerRefs.current.notifications = el; }}
            type="button"
            className="app-topbar-icon-btn"
            aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
            aria-haspopup="dialog"
            aria-expanded={openMenu === "notifications"}
            aria-controls="topbar-notif-panel"
            onClick={() => toggleMenu("notifications")}
          >
            <Icon name="bell" size={19} />
            {unread > 0 && (
              <span className="app-topbar-badge" aria-hidden="true">
                {unread > 9 ? "9+" : unread}
              </span>
            )}
          </button>

          {openMenu === "notifications" && (
            <section
              id="topbar-notif-panel"
              className="app-topbar-panel app-notif-panel"
              role="dialog"
              aria-modal="false"
              aria-label="Recent notifications"
              ref={panelRef}
            >
              <div className="app-panel-header">
                <div>
                  <h2>Notifications</h2>
                  <p>{unread === null ? "Recent updates" : `${unread} unread`}</p>
                </div>
                <Link to={ROUTES.notifications} onClick={() => setOpenMenu("")}>View all</Link>
              </div>
              {actionError && <p className="app-panel-error" role="alert">{actionError}</p>}
              {notifState === "loading" && <p className="app-panel-state">Loading…</p>}
              {notifState === "error" && (
                <div className="app-panel-state">
                  <p>Could not load notifications.</p>
                  <button type="button" onClick={loadNotifications}>Retry</button>
                </div>
              )}
              {notifState === "ready" && notifications.length === 0 && (
                <p className="app-panel-state">No notifications yet.</p>
              )}
              {notifState === "ready" && notifications.length > 0 && (
                <ul className="app-notif-list">
                  {notifications.map((notif) => (
                    <li key={notif.id}>
                      <button type="button" onClick={() => markRead(notif)}>
                        <span className="app-notif-copy">
                          <strong>{notif.title}</strong>
                          <span>{notif.message}</span>
                          <StatusBadge
                            status={notif.is_read ? "confirmed" : "pending"}
                            label={notif.is_read ? "Read" : "Unread"}
                          />
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {notifState === "ready" && unread > 0 && (
                <button type="button" className="app-notif-mark-all" onClick={markAllRead}>
                  Mark all as read
                </button>
              )}
            </section>
          )}
        </div>

        {/* Account menu */}
        <div className="app-topbar-menu-wrap">
          <button
            ref={(el) => { triggerRefs.current.account = el; }}
            type="button"
            className="app-topbar-account-btn"
            aria-label={`Account menu for ${user?.first_name || user?.username || "user"}`}
            aria-haspopup="menu"
            aria-expanded={openMenu === "account"}
            aria-controls="topbar-account-panel"
            onClick={() => toggleMenu("account")}
          >
            <span className="app-topbar-avatar" aria-hidden="true">{initials}</span>
            <Icon name="chevronDown" size={14} />
          </button>

          {openMenu === "account" && (
            <div
              id="topbar-account-panel"
              className="app-topbar-panel app-account-panel"
              role="menu"
              aria-label="Account menu"
              ref={panelRef}
            >
              <div className="app-panel-heading">
                {user?.first_name
                  ? `${user.first_name}${user.last_name ? " " + user.last_name : ""}`
                  : user?.username || "Account"
                }
                {user?.staff_role && (
                  <span className="app-panel-role">{user.staff_role.replaceAll("_", " ")}</span>
                )}
              </div>
              {workspaces.length > 1 && (
                <div className="app-workspace-menu" aria-label="Available workspaces">
                  <p className="app-workspace-menu-title">Switch workspace</p>
                  {workspaces.map((workspace) => (
                    <button
                      key={workspace.id}
                      type="button"
                      role="menuitemradio"
                      aria-checked={workspace.id === currentWorkspace}
                      className="app-panel-link app-workspace-option"
                      onClick={() => switchWorkspace(workspace.id)}
                    >
                      <Icon name={
                        workspace.id === "staff" ? "shield"
                        : workspace.id === "crew" ? "bus"
                        : workspace.id === "owner" ? "truck"
                        : workspace.id === "welfare_officer" ? "heart"
                        : workspace.id === "chairman" ? "vote"
                        : workspace.id === "secretary" ? "file"
                        : workspace.id === "treasurer" ? "bank"
                        : workspace.id === "credit_officer" ? "receipt"
                        : workspace.id === "clerk" ? "receipt"
                        : workspace.id === "kyc_reviewer" ? "id"
                        : "user"
                      } size={16} />
                      <span>{workspace.label}</span>
                      {workspace.id === currentWorkspace && <span className="sr-only">Current workspace</span>}
                    </button>
                  ))}
                  <div className="app-panel-divider" role="separator" />
                </div>
              )}
              <NavLink role="menuitem" className="app-panel-link" to={ROUTES.profile} onClick={() => setOpenMenu("")}>
                <Icon name="user" size={16} /> Profile &amp; security
              </NavLink>
              <NavLink role="menuitem" className="app-panel-link" to={ROUTES.changePassword} onClick={() => setOpenMenu("")}>
                <Icon name="lock" size={16} /> Change password
              </NavLink>
              <NavLink role="menuitem" className="app-panel-link" to={ROUTES.notifications} onClick={() => setOpenMenu("")}>
                <Icon name="bell" size={16} /> Notifications
              </NavLink>
              <div className="app-panel-divider" role="separator" />
              <button
                role="menuitem"
                type="button"
                className="app-panel-link app-panel-logout"
                onClick={handleLogout}
              >
                <Icon name="logout" size={16} /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
