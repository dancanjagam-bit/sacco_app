import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import RepayLoanModal from "./RepayLoanModal";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

jest.mock("../api/axios", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock("../context/AuthContext", () => ({ useAuth: jest.fn() }));

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { phone_number: "0712345678" } });
  api.post.mockResolvedValue({ data: { checkout_request_id: "checkout-test-1" } });
});

test("repayment starts the confirmed M-Pesa flow and request acceptance stays pending", async () => {
  render(<RepayLoanModal loan={{ id: 4, balance: "1000.00" }} onClose={jest.fn()} onUpdated={jest.fn()} />);
  fireEvent.change(screen.getByLabelText("Repayment amount (KES)"), { target: { value: "250" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue to M-Pesa" }));
  expect(screen.getByRole("dialog", { name: "Repay a loan" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Send M-Pesa request" }));

  expect(await screen.findByText("Waiting for provider confirmation")).toBeInTheDocument();
  expect(api.post).toHaveBeenCalledWith("payments/mpesa/stk/", {
    payment_type: "repayment", phone: "0712345678", amount: 250, loan_id: 4,
  });
  expect(screen.queryByText("Payment confirmed")).not.toBeInTheDocument();
});
