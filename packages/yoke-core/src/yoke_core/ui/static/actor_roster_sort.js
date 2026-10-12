// Actors roster ordering and grant wording. The roster is one full read, so
// ordering happens here, and this is the one list of sortable columns: the
// server saves the chosen sort under the "actors" screen checking only its shape.

export const ACTOR_SORT_COLUMNS = {
  Actor: "name", State: "status", "Org role": "org_role", "Project access": "project_access",
  Grants: "grants", "Member email": "email", "API keys": "api_keys",
};

export function normalizeActorSort(sort) {
  return Object.values(ACTOR_SORT_COLUMNS).includes(sort?.column) && ["asc", "desc"].includes(sort?.direction)
    ? { column: sort.column, direction: sort.direction }
    : { column: "name", direction: "asc" };
}

// Every org role a person holds reaches every project in the org, so a
// person's org role leads their access, then each project grant.
export function projectAccess(actor) {
  const orgWide = actor.kind === "human"
    ? (actor.roles?.org || []).map((row) => ({ project: "All projects", from: row.role })) : [];
  return [...orgWide, ...(actor.roles?.projects || []).map((row) => ({
    project: row.project, role: row.role,
  }))];
}

function projectAccessText(actor) {
  return projectAccess(actor).map((entry) => (entry.from
    ? `${entry.project} · from org ${entry.from}` : `${entry.project} · ${entry.role}`)).join(", ");
}

// A machine account's org and project grants as one list, org grants first.
export function actorGrants(actor) {
  return [
    ...(actor.roles?.org || []).map((row) => ({ scope: "Org", role: row.role })),
    ...(actor.roles?.projects || []).map((row) => ({ scope: `Project · ${row.project}`, role: row.role })),
  ];
}

const SORT_VALUES = {
  name: (actor) => actor.name || "",
  status: (actor) => actor.status || "active",
  org_role: (actor) => (actor.roles?.org || []).map((row) => row.role).join(", "),
  project_access: projectAccessText,
  grants: (actor) => actorGrants(actor).map((grant) => `${grant.scope} ${grant.role}`).join(", "),
  email: (actor) => actor.identity?.email || "",
  api_keys: (actor) => actor.tokens?.length || 0,
};

export function sortActors(rows, sort) {
  const value = SORT_VALUES[sort.column];
  const sign = sort.direction === "desc" ? -1 : 1;
  return [...rows].sort((left, right) => {
    const a = value(left);
    const b = value(right);
    const order = typeof a === "number"
      ? a - b : a.localeCompare(b, undefined, { sensitivity: "base", numeric: true });
    return sign * order || left.id - right.id;
  });
}
