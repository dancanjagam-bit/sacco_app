import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import api from "../api/axios";
import Notifications from "./Notifications";

jest.mock("../api/axios", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

jest.mock("../components/Layout", () => function MockLayout({ children }) {
  return <main>{typeof children === "function" ? children() : children}</main>;
});

beforeEach(() => jest.clearAllMocks());

test("failed request shows an error, not empty state, and retry can load empty result", async () => {
  api.get.mockRejectedValueOnce({ response: { status: 500 } })
    .mockResolvedValueOnce({ data: { unread_count: 0, notifications: [] } });
  render(<MemoryRouter><Notifications /></MemoryRouter>);

  expect(screen.getByText("Loading notifications…")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load notifications");
  expect(screen.queryByText("All caught up!")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("All caught up!")).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledTimes(2);
});

test("populated notifications show their own state and marking read does not say empty", async () => {
  api.get.mockResolvedValue({ data: {
    unread_count: 1,
    notifications: [{
      id: 7, type: "info", title: "Payment update", message: "A payment was confirmed.",
      is_read: false, link: "", created_at: "2026-11-11T08:00:00Z",
    }],
  } });
  api.post.mockResolvedValue({ data: {} });
  render(<MemoryRouter><Notifications /></MemoryRouter>);

  expect(await screen.findByText("Payment update")).toBeInTheDocument();
  expect(screen.getByText("1 unread notification")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Mark as read" }));
  await waitFor(() => expect(screen.getByText("No unread notifications.")).toBeInTheDocument());
  expect(screen.queryByText("All caught up!")).not.toBeInTheDocument();
  expect(api.post).toHaveBeenCalledWith("notifications/7/read/");
});

test("malformed response is presented as an error rather than an empty notification list", async () => {
  api.get.mockResolvedValue({ data: { notifications: null, unread_count: 0 } });
  render(<MemoryRouter><Notifications /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load notifications");
  expect(screen.queryByText("All caught up!")).not.toBeInTheDocument();
});
