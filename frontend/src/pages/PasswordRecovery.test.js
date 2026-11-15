import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import api from "../api/axios";
import ForgotPassword from "./ForgotPassword";
import VerifyOTP from "./VerifyOTP";

jest.mock("../api/axios", () => ({ __esModule: true, default: { post: jest.fn() } }));

test("selects registered SMS recovery and resends using the same method", async () => {
  const message = "If this account can receive a code by the selected method, look for it in your email or text messages.";
  api.post.mockResolvedValue({ data: { message } });
  render(
    <MemoryRouter initialEntries={["/forgot-password"]}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/verify-otp" element={<VerifyOTP />} />
      </Routes>
    </MemoryRouter>
  );

  const identifier = "registered@example.invalid";
  fireEvent.change(screen.getByLabelText("Username or registered email"), { target: { value: identifier } });
  fireEvent.change(screen.getByLabelText("Send code via"), { target: { value: "phone" } });
  fireEvent.click(screen.getByRole("button", { name: /send otp/i }));

  expect(await screen.findByText("Enter the 6-digit code you receive by SMS.")).toBeInTheDocument();
  expect(screen.getByText(message)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Resend OTP" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
  expect(api.post.mock.calls).toEqual([
    ["forgot-password/", { identifier, method: "phone" }],
    ["forgot-password/", { identifier, method: "phone" }],
  ]);
  expect(await screen.findByRole("status")).toHaveTextContent(message);
  expect(screen.queryByText("New OTP sent!")).not.toBeInTheDocument();
});
