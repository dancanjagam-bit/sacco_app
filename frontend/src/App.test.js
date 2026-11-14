import React from "react";
import { render, screen } from "@testing-library/react";
import App from "./App";

jest.mock("./context/SaccoContext", () => ({
  SaccoProvider: ({ children }) => children,
  useSacco: () => ({ name: "Nairobi West Transport Cooperative Society" }),
}));

test("public app navigation links sign-in and registration routes", async () => {
  render(<App />);
  expect(screen.getByRole("link", { name: "Nairobi West Transport Cooperative home" })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: "Register" })).toHaveAttribute("href", "/register");
  expect(await screen.findByText("Member and staff access")).toBeInTheDocument();
});
