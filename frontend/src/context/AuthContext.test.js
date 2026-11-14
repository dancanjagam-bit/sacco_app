import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AuthProvider, useAuth } from "./AuthContext";
import api, { authApi } from "../api/axios";

jest.mock("../api/axios", () => ({
  __esModule: true,
  default: { get: jest.fn() },
  authApi: { post: jest.fn() },
}));

function AuthProbe() {
  const { user, loading, authError, logout } = useAuth();
  return (
    <div>
      <span>{loading ? "loading" : user?.username || "signed out"}</span>
      {authError && <span role="alert">{authError}</span>}
      <button type="button" onClick={logout}>Log out test session</button>
    </div>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

test("a valid session stored in this tab is restored after a page refresh", async () => {
  sessionStorage.setItem("access", "valid-access");
  sessionStorage.setItem("refresh", "valid-refresh");
  api.get.mockResolvedValue({ data: { username: "member_one", is_admin: false } });

  render(<AuthProvider><AuthProbe /></AuthProvider>);

  expect(await screen.findByText("member_one")).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledWith("dashboard/");
});

test("temporary API outage keeps the stored session available for retry", async () => {
  sessionStorage.setItem("access", "valid-access");
  sessionStorage.setItem("refresh", "valid-refresh");
  api.get.mockRejectedValue({ code: "ERR_NETWORK" });

  render(<AuthProvider><AuthProbe /></AuthProvider>);

  expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach the SACCO service/i);
  expect(sessionStorage.getItem("access")).toBe("valid-access");
  expect(sessionStorage.getItem("refresh")).toBe("valid-refresh");
});

test("logout clears both token stores and asks Django to revoke the refresh token", async () => {
  localStorage.setItem("access", "remembered-access");
  localStorage.setItem("refresh", "remembered-refresh");
  localStorage.setItem("sacco_remember_session", "true");
  api.get.mockResolvedValue({ data: { username: "member_one" } });
  authApi.post.mockResolvedValue({ data: { message: "Logged out successfully." } });

  render(<AuthProvider><AuthProbe /></AuthProvider>);
  expect(await screen.findByText("member_one")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Log out test session" }));

  await waitFor(() => expect(screen.getByText("signed out")).toBeInTheDocument());
  expect(authApi.post).toHaveBeenCalledWith(
    "logout/",
    { refresh: "remembered-refresh" },
    { headers: { Authorization: "Bearer remembered-access" } }
  );
  expect(localStorage.getItem("access")).toBeNull();
  expect(localStorage.getItem("refresh")).toBeNull();
  expect(sessionStorage.getItem("access")).toBeNull();
  expect(sessionStorage.getItem("refresh")).toBeNull();
  expect(localStorage.getItem("sacco_remember_session")).toBeNull();
});
