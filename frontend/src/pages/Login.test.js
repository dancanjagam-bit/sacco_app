import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Login from "./Login";
import { authApi } from "../api/axios";
import { useAuth } from "../context/AuthContext";

jest.mock("../api/axios", () => ({
  __esModule: true,
  authApi: { post: jest.fn() },
}));

jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../context/SaccoContext", () => ({ useSacco: () => ({ name: "Test SACCO", address: "Test branch" }) }));

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/dashboard" element={<h1>Member dashboard</h1>} />
        <Route path="/admin/dashboard" element={<h1>Staff dashboard</h1>} />
        <Route path="/transport/crew" element={<h1>Crew portal</h1>} />
      </Routes>
    </MemoryRouter>
  );
}

function enterCredentials() {
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "test_user" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "LocalTestOnly123!" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign In →" }));
}

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  useAuth.mockReturnValue({ user: null, loading: false, refreshUser: jest.fn() });
});

test("member login loads one profile and opens the member dashboard", async () => {
  const profile = {
    username: "test_user",
    permissions: ["accounts.read_own"],
    workspaces: [{ id: "member", label: "Member services", short_label: "Member", path: "/dashboard" }],
    default_workspace: "member",
  };
  const refreshUser = jest.fn().mockResolvedValue(profile);
  useAuth.mockReturnValue({ user: null, loading: false, refreshUser });
  authApi.post.mockResolvedValueOnce({ data: { access: "member-access", refresh: "member-refresh" } });

  renderLogin();
  enterCredentials();

  expect(await screen.findByRole("heading", { name: "Member dashboard" })).toBeInTheDocument();
  expect(authApi.post).toHaveBeenCalledTimes(1);
  expect(refreshUser).toHaveBeenCalledTimes(1);
  expect(sessionStorage.getItem("access")).toBe("member-access");
});

test("staff receives no token until the OTP has been verified", async () => {
  const profile = {
    username: "test_user",
    permissions: ["staff.console"],
    workspaces: [
      { id: "member", label: "Member services", short_label: "Member", path: "/dashboard" },
      { id: "staff", label: "Staff operations", short_label: "Staff", path: "/admin/dashboard" },
    ],
    default_workspace: "staff",
  };
  const refreshUser = jest.fn().mockResolvedValue(profile);
  useAuth.mockReturnValue({ user: null, loading: false, refreshUser });
  authApi.post
    .mockResolvedValueOnce({ data: {
      requires_2fa: true,
      identifier: "test_user",
      masked_destination: "te***@example.invalid",
      delivery_status: "accepted",
      message: "The email provider accepted a request, but this does not confirm inbox delivery.",
      challenge_token: "signed-challenge",
      resend_after_seconds: 0,
    } })
    .mockResolvedValueOnce({ data: { access: "staff-access", refresh: "staff-refresh" } });

  renderLogin();
  enterCredentials();
  expect(await screen.findByRole("heading", { name: "Staff sign-in verification" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(/does not confirm inbox delivery/i);
  expect(screen.queryByText(/code was sent/i)).not.toBeInTheDocument();
  expect(sessionStorage.getItem("access")).toBeNull();
  expect(refreshUser).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText("Verification code"), { target: { value: "123456" } });
  fireEvent.click(screen.getByRole("button", { name: "Verify and sign in" }));
  expect(await screen.findByRole("heading", { name: "Staff dashboard" })).toBeInTheDocument();
  expect(authApi.post.mock.calls.map(([path]) => path)).toEqual(["token/", "login/2fa/"]);
  expect(refreshUser).toHaveBeenCalledTimes(1);
});

test("unavailable mail shows a retryable challenge without claiming dispatch", async () => {
  authApi.post.mockResolvedValueOnce({ data: {
    requires_2fa: true,
    identifier: "test_user",
    masked_destination: "te***@example.invalid",
    delivery_status: "unavailable",
    message: "Staff verification is required, but the email delivery service is not configured.",
    challenge_token: "signed-challenge",
    resend_after_seconds: 0,
  } });
  renderLogin();
  enterCredentials();
  expect(await screen.findByRole("alert")).toHaveTextContent(/not configured/i);
  expect(screen.queryByText(/sent/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Resend code" })).toBeEnabled();
  expect(sessionStorage.getItem("access")).toBeNull();
});

test("staff can resend through the challenge endpoint and the form actions are distinct", async () => {
  authApi.post
    .mockResolvedValueOnce({ data: {
      requires_2fa: true,
      identifier: "test_user",
      masked_destination: "te***@example.invalid",
      delivery_status: "accepted",
      message: "The email provider accepted a request; inbox delivery is not confirmed.",
      challenge_token: "first-challenge",
      resend_after_seconds: 0,
    } })
    .mockResolvedValueOnce({ data: {
      requires_2fa: true,
      identifier: "test_user",
      masked_destination: "te***@example.invalid",
      delivery_status: "accepted",
      message: "The email provider accepted a new request; inbox delivery is not confirmed.",
      challenge_token: "next-challenge",
      resend_after_seconds: 60,
    } });
  const { container } = renderLogin();
  enterCredentials();
  await screen.findByRole("heading", { name: "Staff sign-in verification" });
  const actions = container.querySelector(".auth-twofa-actions");
  expect(actions.querySelectorAll("button")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "Resend code" }));
  await waitFor(() => expect(authApi.post).toHaveBeenCalledWith("login/2fa/resend/", {
    identifier: "test_user",
    challenge_token: "first-challenge",
  }));
  expect(await screen.findByRole("button", { name: "Resend code in 60s" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Back to sign in" })).toBeInTheDocument();
});

test("transport crew role opens the crew portal", async () => {
  const profile = {
    username: "test_user",
    permissions: ["transport.read_assigned"],
    workspaces: [{ id: "crew", label: "Transport crew", short_label: "Crew", path: "/transport/crew" }],
    default_workspace: "crew",
  };
  useAuth.mockReturnValue({ user: null, loading: false, refreshUser: jest.fn().mockResolvedValue(profile) });
  authApi.post.mockResolvedValueOnce({ data: { access: "crew-access", refresh: "crew-refresh" } });

  renderLogin();
  enterCredentials();

  expect(await screen.findByRole("heading", { name: "Crew portal" })).toBeInTheDocument();
});

test("application admin flag opens the staff portal", async () => {
  const profile = {
    username: "test_user",
    permissions: ["staff.console"],
    workspaces: [{ id: "staff", label: "Staff operations", short_label: "Staff", path: "/admin/dashboard" }],
    default_workspace: "staff",
  };
  useAuth.mockReturnValue({ user: null, loading: false, refreshUser: jest.fn().mockResolvedValue(profile) });
  authApi.post.mockResolvedValueOnce({ data: { access: "admin-access", refresh: "admin-refresh" } });

  renderLogin();
  enterCredentials();

  expect(await screen.findByRole("heading", { name: "Staff dashboard" })).toBeInTheDocument();
});

test("failed credentials show a readable error", async () => {
  authApi.post.mockRejectedValueOnce({ response: { status: 401 } });
  renderLogin();
  enterCredentials();
  expect(await screen.findByText(/invalid username or password/i)).toBeInTheDocument();
});

test("accepted login with a temporary profile failure preserves tokens and explains recovery", async () => {
  useAuth.mockReturnValue({ user: null, loading: false, refreshUser: jest.fn().mockResolvedValue(null) });
  authApi.post.mockResolvedValueOnce({ data: { access: "member-access", refresh: "member-refresh" } });
  renderLogin();
  enterCredentials();
  await waitFor(() => expect(screen.getByText(/sign-in was accepted/i)).toBeInTheDocument());
  expect(sessionStorage.getItem("access")).toBe("member-access");
  expect(screen.queryByRole("heading", { name: "Member dashboard" })).not.toBeInTheDocument();
});
