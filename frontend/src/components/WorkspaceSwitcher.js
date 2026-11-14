import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { availableWorkspaces } from "../auth/portalDestination";

export default function WorkspaceSwitcher({ user }) {
  const navigate = useNavigate();
  const location = useLocation();
  const workspaces = availableWorkspaces(user);
  if (workspaces.length < 2) return null;

  const current = location.pathname.startsWith("/admin/")
    ? "staff"
    : location.pathname.startsWith("/transport/owner")
      ? "owner"
      : location.pathname.startsWith("/transport/")
        ? "crew"
      : "member";

  return (
    <label className="workspace-switcher">
      <span>Workspace</span>
      <select
        aria-label="Switch workspace"
        value={workspaces.some((workspace) => workspace.id === current) ? current : "member"}
        onChange={(event) => {
          const next = workspaces.find((workspace) => workspace.id === event.target.value);
          if (next) navigate(next.path);
        }}
      >
        {workspaces.map((workspace) => (
          <option key={workspace.id} value={workspace.id} title={workspace.label}>{workspace.shortLabel || workspace.label}</option>
        ))}
      </select>
    </label>
  );
}
