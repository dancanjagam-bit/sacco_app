import { navigationFor } from "../navigation/routes";

export function portalDestination(user) {
  const workspaces = availableWorkspaces(user);
  const rememberedId = safeStorageGet("sacco_workspace");
  const remembered = workspaces.find((workspace) => workspace.id === rememberedId);
  if (remembered) return remembered.path;
  if (rememberedId) safeStorageRemove("sacco_workspace");
  const preferred = workspaces.find((workspace) => workspace.id === user?.default_workspace);
  return preferred?.path || workspaces[0]?.path || "/dashboard";
}

export function workspaceForPath(user, pathname) {
  const workspaces = availableWorkspaces(user);
  const byId = (id) => workspaces.find((workspace) => workspace.id === id)?.id;
  // Determine context from the routes this server-authorized workspace can
  // actually navigate to. This keeps shared member pages inside the selected
  // owner/crew/staff workspace without treating the switcher as permission.
  const candidates = workspaces.filter((workspace) => navigationFor(user, workspace.id)
    .flatMap((group) => group.items)
    .some((item) => pathname === item.to || pathname.startsWith(`${item.to}/`)))
    .map((workspace) => workspace.id);
  if (!candidates.length) return null;
  const rememberedId = safeStorageGet("sacco_workspace");
  if (rememberedId && !byId(rememberedId)) safeStorageRemove("sacco_workspace");
  if (candidates.includes(rememberedId) && byId(rememberedId)) return rememberedId;
  const preferred = candidates.find((id) => id === user?.default_workspace);
  return preferred || candidates[0] || null;
}

export function availableWorkspaces(user) {
  if (!Array.isArray(user?.workspaces)) return [];
  return user.workspaces.filter((workspace) =>
    workspace && typeof workspace.id === "string" && typeof workspace.path === "string"
  ).map((workspace) => ({
    ...workspace,
    shortLabel: workspace.shortLabel || workspace.short_label || workspace.label || workspace.id,
  }));
}

function safeStorageGet(key) {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

function safeStorageRemove(key) {
  try { window.localStorage.removeItem(key); } catch { /* storage is optional */ }
}
