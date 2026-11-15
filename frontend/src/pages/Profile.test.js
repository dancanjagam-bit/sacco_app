import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Profile from "./Profile";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

jest.mock("../api/axios", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), put: jest.fn() } }));
jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../components/Layout", () => function MockLayout({ children }) { return <main>{typeof children === "function" ? children() : children}</main>; });

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ refreshUser: jest.fn() });
});

test("member profile renders returned account data and links password change", async () => {
  api.get.mockResolvedValue({ data: {
    first_name: "Test", last_name: "Member", email: "member@example.invalid",
    phone_number: "0700000001", county: "Nairobi", address: "Synthetic test account",
    recovery_email: "", recovery_phone: "",
  } });
  render(<MemoryRouter><Profile /></MemoryRouter>);
  expect(await screen.findByText("member@example.invalid")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Profile and security" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Change password/ })).toHaveAttribute("href", "/change-password");
  expect(api.get).toHaveBeenCalledWith("profile/");
});

test("profile load failure has a retry state instead of blank content", async () => {
  api.get.mockRejectedValueOnce(new Error("temporary failure"))
    .mockResolvedValueOnce({ data: { first_name: "Test", last_name: "Member" } });
  render(<MemoryRouter><Profile /></MemoryRouter>);
  expect(await screen.findByText("Profile unavailable")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("heading", { name: "Personal information" })).toBeInTheDocument();
});

test("member can upload a photo and load the authenticated preview", async () => {
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  URL.createObjectURL = jest.fn().mockReturnValue("blob:profile-photo");
  URL.revokeObjectURL = jest.fn();
  try {
    api.get.mockResolvedValueOnce({ data: { member_number: "TEST01", has_profile_photo: false } })
      .mockResolvedValueOnce({ data: new Blob(["photo"], { type: "image/jpeg" }) });
    api.post.mockResolvedValueOnce({ data: { has_profile_photo: true } });
    const { unmount } = render(<MemoryRouter><Profile /></MemoryRouter>);
    const file = new File(["test image"], "profile.png", { type: "image/png" });
    fireEvent.change(await screen.findByLabelText("Choose photo"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Save photo" }));
    expect(await screen.findByRole("img", { name: "Your member portrait" })).toHaveAttribute("src", "blob:profile-photo");
    expect(api.post.mock.calls[0][0]).toBe("profile/photo/");
    expect(api.post.mock.calls[0][1].get("photo")).toBe(file);
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:profile-photo");
  } finally {
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
  }
});
