import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import IDVerificationStatus from "./IDVerificationStatus";
import api from "../api/axios";

jest.mock("../api/axios", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock("../components/Layout", () => function MockLayout({ children }) { return <main>{typeof children === "function" ? children() : children}</main>; });

test("identity status failure leaves loading state and offers a retry", async () => {
  api.get.mockRejectedValueOnce(new Error("unavailable"))
    .mockResolvedValueOnce({ data: { status: "not_submitted", provider: "manual" } });
  render(<MemoryRouter><IDVerificationStatus /></MemoryRouter>);
  expect(await screen.findByText("Verification status could not be loaded")).toBeInTheDocument();
  expect(screen.queryByText("Loading verification status…")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("No documents submitted")).toBeInTheDocument();
  expect(screen.queryByText("Verification status could not be loaded")).not.toBeInTheDocument();
});
