import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import api from "../api/axios";
import TreasuryWelfareQueue from "./TreasuryWelfareQueue";
import WelfarePolicy from "./WelfarePolicy";

jest.mock("../api/axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("../components/Layout", () => ({ children }) => <>{children}</>);
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ user: { permissions: ["staff.manage"] } }) }));

beforeEach(() => { jest.resetAllMocks(); });

function fill(label, value) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

test("the welfare policy submits approved limits entered in structured fields", async () => {
  api.get.mockResolvedValue({ data: { active_policy: null, policies: [] } });
  api.post.mockResolvedValue({ data: { id: 4 } });
  render(<WelfarePolicy />);
  await screen.findByLabelText("Version");
  fill("Version", "November");
  fill("Approval reference (board resolution number)", "RES-24");
  fill("Category name", "medical");
  fill("Maximum benefit (KES)", "500.00");
  fill("Minimum posted contributions (KES)", "25.00");
  fireEvent.click(screen.getByRole("checkbox", { name: /Activate this policy/ }));
  fireEvent.click(screen.getByRole("button", { name: "Create policy" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("welfare/policy/", {
    version: "November", approval_reference: "RES-24", benefits: { medical: { maximum_benefit: "500.00", minimum_contributions: "25.00" } }, activate: true,
  }));
  expect(await screen.findByText("Policy created successfully.")).toBeInTheDocument();
});

test("Treasury confirms the payout destination and waits for a provider status", async () => {
  const approved = { id: 4, member_name: "Member One", approved_amount: "500.00", category: "medical" };
  api.get.mockResolvedValueOnce({ data: { payouts: [{ ...approved, payout_status: "awaiting_provider", can_start_payout: true }], provider_available: true } })
    .mockResolvedValueOnce({ data: { payouts: [{ ...approved, payout_status: "pending", can_refresh_payout: true }], provider_available: true } })
    .mockResolvedValueOnce({ data: { payouts: [{ ...approved, payout_status: "confirmed" }], provider_available: true } });
  api.post.mockResolvedValueOnce({ data: { status: "pending" } }).mockResolvedValueOnce({ data: { status: "confirmed" } });
  render(<TreasuryWelfareQueue />);
  fireEvent.click(await screen.findByRole("button", { name: "Send M-Pesa payout" }));
  expect(screen.getByRole("alertdialog")).toHaveTextContent("their registered M-Pesa number");
  fireEvent.click(screen.getByRole("button", { name: "Send payout" }));
  expect(await screen.findByText("Payout status: Pending confirmation.")).toBeInTheDocument();
  expect(api.post).toHaveBeenCalledWith("welfare/requests/4/payout/start/", {});
  fireEvent.click(await screen.findByRole("button", { name: "Check payout status" }));
  expect(await screen.findByText("Payout status: Confirmed.")).toBeInTheDocument();
  expect(api.post).toHaveBeenCalledWith("welfare/requests/4/payout/status/", {});
});

test("Treasury can link a posted welfare credit by member and journal line", async () => {
  api.get.mockImplementation((path) => Promise.resolve({ data: path.includes("/attribution/") ? {
    members: [{ id: 7, name: "Member One", member_number: "M-7" }],
    credits: [{ id: 12, amount: "150.00", posted_at: "2026-11-13T08:00:00Z", source_reference: "TR-10" }],
  } : { payouts: [], can_attribute: true } }));
  api.post.mockResolvedValue({ data: {} });
  render(<TreasuryWelfareQueue />);
  await screen.findByLabelText("Member name or number");
  fill("Member name or number", "M-7");
  fireEvent.click(screen.getByRole("button", { name: "Find attribution records" }));
  expect(await screen.findByRole("option", { name: "Member One · M-7" })).toBeInTheDocument();
  fill("Member", "7");
  fill("Posted welfare credit", "12");
  fill("Reason for linking the contribution", "Verified transport receipt and member number");
  fireEvent.click(screen.getByRole("button", { name: "Link posted contribution" }));
  expect(await screen.findByText("Posted contribution linked to the member.")).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledWith("welfare/contributions/attribution/?q=M-7");
  expect(api.post).toHaveBeenCalledWith("welfare/contributions/attribute/", { member: 7, journal_line: 12, reason: "Verified transport receipt and member number" });
});
