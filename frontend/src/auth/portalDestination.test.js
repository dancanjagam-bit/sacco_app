import { portalDestination, workspaceForPath } from "./portalDestination";

const member = { id: "member", path: "/dashboard", label: "Member" };
const owner = { id: "owner", path: "/transport/owner", label: "Owner" };

beforeEach(() => window.localStorage.clear());

test("shared member pages keep the selected authorized workspace context", () => {
  const user = {
    permissions: ["accounts.read_own", "transport.read_owned"],
    workspaces: [member, owner],
    default_workspace: "owner",
  };
  expect(workspaceForPath(user, "/dashboard")).toBe("owner");
  window.localStorage.setItem("sacco_workspace", "member");
  expect(workspaceForPath(user, "/dashboard")).toBe("member");
});

test("role removal clears remembered selection and cannot restore that workspace", () => {
  window.localStorage.setItem("sacco_workspace", "owner");
  const user = {
    permissions: ["accounts.read_own"],
    workspaces: [member],
    default_workspace: "member",
  };
  expect(portalDestination(user)).toBe("/dashboard");
  expect(window.localStorage.getItem("sacco_workspace")).toBeNull();
  expect(workspaceForPath(user, "/dashboard")).toBe("member");
});

test("shared loan review routes use only the workspaces authorized by the snapshot", () => {
  const user = {
    permissions: ["loans.appraise_assigned", "loans.approve_assigned"],
    workspaces: [
      { id: "credit_officer", path: "/staff/credit", label: "Credit" },
      { id: "chairman", path: "/staff/chairman", label: "Chairman" },
    ],
    default_workspace: "chairman",
  };
  expect(workspaceForPath(user, "/admin/loans")).toBe("chairman");
  window.localStorage.setItem("sacco_workspace", "credit_officer");
  expect(workspaceForPath(user, "/admin/loans")).toBe("credit_officer");
});
