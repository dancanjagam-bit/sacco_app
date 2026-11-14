import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useShell } from "./AppShell";
import { navigationFor } from "../navigation/routes";
import { workspaceForPath } from "../auth/portalDestination";
import Icon from "./ui/Icon";
import SaccoLogo from "./SaccoLogo";

// ── Component ─────────────────────────────────────────────────────────────────
export default function AppSidebar() {
  const { user }                = useAuth();
  const { collapsed, mobileOpen, setMobileOpen, menuTriggerRef } = useShell();
  const location                = useLocation();

  const sidebarRef  = useRef(null);
  const closeRef    = useRef(null);
  const previousPath = useRef(location.pathname);
  const [tooltip, setTooltip] = useState(null);

  const currentWorkspace = workspaceForPath(user, location.pathname) || "member";
  const visibleGroups = navigationFor(user, currentWorkspace);
  const homeHref = currentWorkspace === "staff" ? "/admin/dashboard"
    : currentWorkspace === "clerk" ? "/staff/clerk"
      : currentWorkspace === "credit_officer" ? "/staff/credit"
        : currentWorkspace === "treasurer" ? "/staff/treasury"
          : currentWorkspace === "secretary" ? "/staff/secretary"
            : currentWorkspace === "chairman" ? "/staff/chairman"
              : currentWorkspace === "kyc_reviewer" ? "/admin/id-verifications"
    : currentWorkspace === "owner" ? "/transport/owner"
      : currentWorkspace === "crew" ? "/transport/crew" : "/dashboard";

  const closeDrawer = useCallback((restoreFocus = true) => {
    setMobileOpen(false);
    if (restoreFocus) window.requestAnimationFrame(() => menuTriggerRef.current?.focus());
  }, [menuTriggerRef, setMobileOpen]);

  // Close mobile drawer on route change.
  useEffect(() => {
    if (previousPath.current !== location.pathname && mobileOpen) {
      setMobileOpen(false);
      window.requestAnimationFrame(() => document.getElementById("app-main-content")?.focus());
    }
    previousPath.current = location.pathname;
  }, [location.pathname, mobileOpen, setMobileOpen]);

  // Focus trap for mobile drawer.
  useEffect(() => {
    if (!mobileOpen) return;
    // Focus close button on open.
    window.requestAnimationFrame(() => closeRef.current?.focus());

    function handleKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDrawer(true);
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        sidebarRef.current?.querySelectorAll(
          'a[href], button:not([disabled]), select:not([disabled]), [tabindex="0"]'
        ) ?? []
      ).filter((el) => el.getClientRects().length > 0);
      const first = focusable[0];
      const last  = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [mobileOpen, closeDrawer]);

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="app-sidebar-backdrop"
          aria-hidden="true"
          onClick={() => closeDrawer(true)}
        />
      )}

      <aside
        id="app-sidebar"
        ref={sidebarRef}
        className={[
          "app-sidebar",
          collapsed  ? "is-collapsed"    : "",
          mobileOpen ? "is-mobile-open"  : "",
        ].filter(Boolean).join(" ")}
        aria-label="Primary navigation"
        // Acts as a dialog on mobile so AT reads it as a modal.
        role={mobileOpen ? "dialog" : undefined}
        aria-modal={mobileOpen ? true : undefined}
        aria-labelledby={mobileOpen ? "app-sidebar-title" : undefined}
      >
        <Link
          className="app-sidebar-brand"
          to={homeHref}
          aria-label="Nairobi West Transport Cooperative — go to workspace home"
          onClick={() => closeDrawer(false)}
        >
          <span className="app-sidebar-brand-mark" aria-hidden="true">
            <SaccoLogo size={44} variant="light" />
          </span>
          <span className="app-sidebar-brand-copy">
            <strong>Nairobi West</strong>
            <span>Tuktuk Operators</span>
            <small>Transport Cooperative Society</small>
          </span>
        </Link>

        {/* The topbar controls desktop collapse; this row is reserved for the
            accessible close action inside the mobile drawer. */}
        <div className="app-sidebar-header">
          {mobileOpen && <h2 className="sr-only" id="app-sidebar-title">Navigation menu</h2>}
          <button
            ref={closeRef}
            type="button"
            className="app-sidebar-close-btn mobile-only"
            aria-label="Close navigation menu"
            onClick={() => closeDrawer(true)}
          >
            <Icon name="close" size={18} />
            <span>Close</span>
          </button>
        </div>

        {/* Navigation groups */}
        <nav aria-label="Primary">
          {visibleGroups.map((group) => (
            <section key={group.id} className="app-nav-group">
              <h2 className="app-nav-group-label" aria-hidden={collapsed && !mobileOpen}>
                {group.label}
              </h2>

              {group.items.map((item) => {
                const isActive =
                  location.pathname === item.to ||
                  (item.matchChildren !== false && location.pathname.startsWith(item.to + "/") && item.to !== "/dashboard" && item.to !== "/admin/dashboard" && item.to !== "/transport/crew");

                return (
                  <NavLink
                    key={item.id}
                    to={item.to}
                    end={
                      item.to === "/dashboard" ||
                      item.to === "/admin/dashboard" ||
                      item.to === "/transport/crew"
                    }
                    className={({ isActive: routerActive }) =>
                      "app-nav-item" + (routerActive || isActive ? " is-active" : "")
                    }
                    aria-current={isActive ? "page" : undefined}
                    // Show label as tooltip when collapsed on desktop.
                    title={(collapsed && !mobileOpen) ? item.label : undefined}
                    data-tooltip={(collapsed && !mobileOpen) ? item.label : undefined}
                    aria-describedby={(collapsed && !mobileOpen) ? `nav-tooltip-${item.id}` : undefined}
                    onFocus={(event) => {
                      if (collapsed && !mobileOpen) {
                        const rect = event.currentTarget.getBoundingClientRect();
                        setTooltip({ id: item.id, label: item.label, left: rect.right + 8, top: rect.top + rect.height / 2 });
                      }
                    }}
                    onBlur={() => setTooltip(null)}
                    onMouseEnter={(event) => {
                      if (collapsed && !mobileOpen) {
                        const rect = event.currentTarget.getBoundingClientRect();
                        setTooltip({ id: item.id, label: item.label, left: rect.right + 8, top: rect.top + rect.height / 2 });
                      }
                    }}
                    onMouseLeave={() => setTooltip(null)}
                    aria-label={(collapsed && !mobileOpen) ? item.label : undefined}
                    onClick={() => closeDrawer(false)}
                  >
                    <span className="app-nav-icon" aria-hidden="true">
                      <Icon name={item.icon} size={18} />
                    </span>
                    <span className="app-nav-label">{item.label}</span>
                    {Number.isInteger(item.count) && item.count > 0 && (
                      <span className="app-nav-count" aria-label={`${item.count} pending`}>
                        {item.count > 99 ? "99+" : item.count}
                      </span>
                    )}
                  </NavLink>
                );
              })}
            </section>
          ))}
        </nav>
      </aside>
      {tooltip && collapsed && !mobileOpen && createPortal(
        <span
          id={`nav-tooltip-${tooltip.id}`}
          role="tooltip"
          className="app-nav-tooltip"
          style={{ left: tooltip.left, top: tooltip.top }}
        >
          {tooltip.label}
        </span>,
        document.body
      )}
    </>
  );
}
