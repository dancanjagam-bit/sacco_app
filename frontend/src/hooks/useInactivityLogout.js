/**
 * useInactivityLogout
 * ~~~~~~~~~~~~~~~~~~~~
 * Automatically logs the user out after a period of inactivity.
 *
 * - Default timeout: 15 minutes (ideal for cyber cafés / shared computers)
 * - "Remember me" users get 60 minutes (they're on their own device)
 * - Resets on any mouse move, key press, click, scroll, or touch
 * - Shows a 60-second warning before logging out so active users aren't
 *   surprised
 */
import { useEffect, useRef, useCallback, useState } from "react";

const EVENTS = ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "click"];

export function useInactivityLogout(logout, options = {}) {
  const isRemembered = localStorage.getItem("sacco_remember_session") === "true";

  // Remembered users (own device) get longer; cyber café users get shorter
  const timeoutMs  = options.timeoutMs  ?? (isRemembered ? 60 * 60 * 1000 : 15 * 60 * 1000);
  const warningMs  = options.warningMs  ?? 60 * 1000;   // warn 60 s before logout

  const [showWarning, setShowWarning] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);

  const logoutTimer  = useRef(null);
  const warningTimer = useRef(null);
  const countdownRef = useRef(null);

  const clearTimers = useCallback(() => {
    clearTimeout(logoutTimer.current);
    clearTimeout(warningTimer.current);
    clearInterval(countdownRef.current);
  }, []);

  const resetTimers = useCallback(() => {
    clearTimers();
    setShowWarning(false);

    warningTimer.current = setTimeout(() => {
      setShowWarning(true);
      setSecondsLeft(Math.round(warningMs / 1000));
      countdownRef.current = setInterval(() => {
        setSecondsLeft(s => {
          if (s <= 1) { clearInterval(countdownRef.current); return 0; }
          return s - 1;
        });
      }, 1000);
    }, timeoutMs - warningMs);

    logoutTimer.current = setTimeout(() => {
      logout();
    }, timeoutMs);
  }, [clearTimers, logout, timeoutMs, warningMs]);

  // Attach event listeners
  useEffect(() => {
    resetTimers();
    EVENTS.forEach(e => window.addEventListener(e, resetTimers, { passive: true }));
    return () => {
      clearTimers();
      EVENTS.forEach(e => window.removeEventListener(e, resetTimers));
    };
  }, [resetTimers, clearTimers]);

  return { showWarning, secondsLeft, stayLoggedIn: resetTimers };
}
