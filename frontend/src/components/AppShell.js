import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

// ── Shell context ───────────────────────────────────────────────────────────
// Shares sidebar state so AppTopbar, Sidebar, and the main content area
// all stay in sync without prop-drilling.

const ShellContext = createContext({
  collapsed: false,
  setCollapsed: () => {},
  mobileOpen: false,
  setMobileOpen: () => {},
  menuTriggerRef: { current: null },
  searchTriggerRef: { current: null },
  searchOpen: false,
  setSearchOpen: () => {},
});

export function useShell() {
  return useContext(ShellContext);
}

// ── Sidebar-width CSS custom property ──────────────────────────────────────
// The reference uses a compact 256 px rail and an 80 px collapsed icon rail.
const EXPANDED_WIDTH  = "256px";
const COLLAPSED_WIDTH = "80px";

export function AppShell({ children }) {
  const [collapsed, setCollapsed]   = useState(() => {
    // Persist the user's last preference.
    try { return localStorage.getItem("sacco_nav_collapsed") === "1"; }
    catch { return false; }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const menuTriggerRef = React.useRef(null);
  const searchTriggerRef = React.useRef(null);

  // Persist the preference; the CSS width itself is scoped to the shared shell
  // parent below, keeping the sidebar and main content in the same layout.
  useEffect(() => {
    try { localStorage.setItem("sacco_nav_collapsed", collapsed ? "1" : "0"); }
    catch { /* storage unavailable */ }
  }, [collapsed]);

  // Ctrl+K / Cmd+K → open search.
  useEffect(() => {
    function handleKey(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  // Lock page scrolling and make all background content inert while the
  // mobile drawer is modal. Preserve pre-existing values when it closes.
  // Use broad selectors so this works in both the production layout
  // (.app-content-region parent) and the test harness (flat .app-layout).
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const backgroundNodes = Array.from(document.querySelectorAll(
      ".app-topbar, #app-main-content"
    ));
    const previousStates = backgroundNodes.map((node) => ({
      node,
      inert: node.inert || node.hasAttribute("inert"),
      ariaHidden: node.getAttribute("aria-hidden"),
    }));
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
      backgroundNodes.forEach((node) => {
        node.inert = true;
        node.setAttribute("inert", "");
        node.setAttribute("aria-hidden", "true");
      });
    }
    return () => {
      document.body.style.overflow = previousOverflow;
      previousStates.forEach(({ node, inert, ariaHidden }) => {
        node.inert = inert;
        if (inert) node.setAttribute("inert", "");
        else node.removeAttribute("inert");
        if (ariaHidden === null) node.removeAttribute("aria-hidden");
        else node.setAttribute("aria-hidden", ariaHidden);
      });
    };
  }, [mobileOpen]);

  const toggleCollapsed = useCallback(() => setCollapsed((v) => !v), []);

  const value = {
    collapsed, setCollapsed, toggleCollapsed,
    mobileOpen, setMobileOpen,
    menuTriggerRef,
    searchTriggerRef,
    searchOpen, setSearchOpen,
  };

  return (
    <ShellContext.Provider value={value}>
      <div
        className="app-shell-root"
        data-sidebar-collapsed={collapsed ? "true" : "false"}
        style={{ "--sidebar-width": collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH }}
      >
        {children}
      </div>
    </ShellContext.Provider>
  );
}
