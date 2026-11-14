import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { searchablePages } from "../navigation/routes";
import { useShell } from "./AppShell";
import Icon from "./ui/Icon";

// This search intentionally covers permitted navigation pages only. Sensitive
// member/identity/financial record search requires a separate audited API.
export default function SearchDialog() {
  const { searchOpen, setSearchOpen, searchTriggerRef } = useShell();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [focused, setFocused] = useState(0);
  const inputRef = useRef(null);
  const dialogRef = useRef(null);
  const listRef = useRef(null);
  const openedAtPath = useRef(null);
  const pages = useMemo(() => searchablePages(user), [user]);

  const search = useCallback((value) => {
    const term = value.trim().toLocaleLowerCase();
    const matching = term
      ? pages.filter((page) => page.label.toLocaleLowerCase().includes(term) || page.to.toLocaleLowerCase().includes(term))
      : pages;
    setResults(matching.slice(0, term ? 10 : 8));
  }, [pages]);

  const close = useCallback((restoreFocus = true) => {
    setSearchOpen(false);
    if (restoreFocus) window.requestAnimationFrame(() => searchTriggerRef.current?.focus());
  }, [searchTriggerRef, setSearchOpen]);

  useEffect(() => {
    if (!searchOpen) {
      openedAtPath.current = null;
      return;
    }
    setQuery("");
    search("");
    setFocused(0);
    openedAtPath.current = location.pathname;
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [searchOpen, location.pathname, search]);

  useEffect(() => {
    if (!searchOpen || openedAtPath.current === null || location.pathname === openedAtPath.current) return;
    close(false);
    window.requestAnimationFrame(() => document.getElementById("app-main-content")?.focus());
  }, [location.pathname, searchOpen, close]);

  useEffect(() => {
    if (!searchOpen) return undefined;
    const backgroundNodes = Array.from(document.querySelectorAll(
      ".app-layout > .app-topbar, .app-layout > .app-body > .app-sidebar, .app-layout > .app-body > .app-main"
    ));
    const previous = backgroundNodes.map((node) => ({
      node,
      inert: node.inert || node.hasAttribute("inert"),
      ariaHidden: node.getAttribute("aria-hidden"),
    }));
    backgroundNodes.forEach((node) => {
      node.inert = true;
      node.setAttribute("inert", "");
      node.setAttribute("aria-hidden", "true");
    });
    return () => previous.forEach(({ node, inert, ariaHidden }) => {
      node.inert = inert;
      if (inert) node.setAttribute("inert", "");
      else node.removeAttribute("inert");
      if (ariaHidden === null) node.removeAttribute("aria-hidden");
      else node.setAttribute("aria-hidden", ariaHidden);
    });
  }, [searchOpen]);

  useEffect(() => {
    if (!searchOpen) return undefined;
    function handleKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close(true);
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setFocused((index) => Math.min(index + 1, Math.max(results.length - 1, 0)));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setFocused((index) => Math.max(index - 1, 0));
      } else if (event.key === "Enter" && results[focused]) {
        event.preventDefault();
        navigate(results[focused].to);
        close(false);
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [searchOpen, results, focused, navigate, close]);

  useEffect(() => {
    if (!listRef.current) return;
    const items = listRef.current.querySelectorAll("[data-result]");
    items[focused]?.scrollIntoView?.({ block: "nearest" });
  }, [focused]);

  useEffect(() => {
    if (!searchOpen || !dialogRef.current) return undefined;
    function trap(event) {
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialogRef.current.querySelectorAll(
        'a[href], button:not([disabled]), input, [tabindex="0"]'
      )).filter((element) => element.getClientRects().length > 0);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", trap);
    return () => document.removeEventListener("keydown", trap);
  }, [searchOpen]);

  if (!searchOpen) return null;

  const updateQuery = (event) => {
    const value = event.target.value;
    setQuery(value);
    setFocused(0);
    search(value);
  };

  const selectPage = (page) => {
    navigate(page.to);
    close(false);
  };

  return (
    <div
      className="search-dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close(true);
      }}
    >
      <div
        ref={dialogRef}
        className="search-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Search navigation"
      >
        <div className="search-dialog-input-wrap">
          <Icon name="search" size={18} className="search-dialog-icon" />
          <input
            ref={inputRef}
            type="search"
            className="search-dialog-input"
            placeholder="Search permitted pages…"
            value={query}
            onChange={updateQuery}
            autoComplete="off"
            spellCheck="false"
            aria-label="Search permitted pages"
            aria-controls="search-results"
            aria-activedescendant={results[focused] ? `sr-${results[focused].id}` : undefined}
          />
          <button type="button" className="search-dialog-close" onClick={() => close(true)} aria-label="Close search">
            <span aria-hidden="true">Esc</span>
          </button>
        </div>

        {results.length > 0 && (
          <ul id="search-results" ref={listRef} className="search-dialog-results" role="listbox" aria-label="Permitted pages">
            {!query && <li className="search-dialog-category" role="presentation">Quick navigation</li>}
            {results.map((page, index) => (
              <li key={`${page.id}:${page.to}`} id={`sr-${page.id}`} role="option" aria-selected={index === focused} data-result>
                <button
                  type="button"
                  className={`search-dialog-result${index === focused ? " is-focused" : ""}`}
                  onClick={() => selectPage(page)}
                  onMouseEnter={() => setFocused(index)}
                >
                  <span className="search-result-icon" aria-hidden="true"><Icon name={page.icon} size={16} /></span>
                  <span className="search-result-label">{page.label}</span>
                  <span className="search-result-path" aria-hidden="true">{page.to}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {query && results.length === 0 && (
          <p className="search-dialog-empty">No permitted pages found for <strong>“{query}”</strong></p>
        )}

        <div className="search-dialog-footer" aria-hidden="true">
          <span><kbd>↑</kbd> <kbd>↓</kbd> navigate</span>
          <span><kbd>Enter</kbd> open</span>
          <span><kbd>Esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
