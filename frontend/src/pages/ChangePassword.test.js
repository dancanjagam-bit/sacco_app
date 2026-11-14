import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ChangePassword from "./ChangePassword";
import api from "../api/axios";

jest.mock("../api/axios", () => ({ __esModule: true, default: { post: jest.fn() } }));
jest.mock("../components/Layout", () => function MockLayout({ children }) { return <main>{typeof children === "function" ? children() : children}</main>; });

test("password visibility controls stay inside and toggle their own fields", () => {
  render(<MemoryRouter><ChangePassword /></MemoryRouter>);
  const currentPassword = screen.getByLabelText("Current password");
  const currentControl = currentPassword.closest(".ui-password-control");
  expect(currentControl).toContainElement(screen.getByRole("button", { name: "Show current password" }));
  fireEvent.click(screen.getByRole("button", { name: "Show current password" }));
  expect(currentPassword).toHaveAttribute("type", "text");
  expect(screen.getByLabelText("New password")).toHaveAttribute("type", "password");
  expect(api.post).not.toHaveBeenCalled();
});
