/**
 * What a host passes the shared GitHub page under
 * `capabilities.data.github`.
 *
 * The page renders the same sections in every mode. It reads installations
 * and project mappings from the engine itself; a host adds only the facts and
 * controls the engine cannot hold. A hosted shell passes its organization's
 * GitHub connection and the actions that change it. The local `yoke ui`
 * server passes this machine's GitHub App user authorization.
 */
import type { UniverseAction } from "./universe-app.js";
/** The GitHub account a person (hosted) or this machine (local) authorized. */
export interface UniverseGitHubAuthorization {
    readonly login: string;
    /** For example `authorized`, `pending`, or `revoked`. */
    readonly status: string;
}
/** One line the Personal panel shows above the account. */
export interface UniverseGitHubNotice {
    readonly kind: "error" | "status";
    readonly message: string;
}
/**
 * One App installation the host's organization holds, bound to a project
 * or not. Passed by a hosted shell, whose list is the organization's whole
 * set; the page otherwise derives installations from project bindings.
 */
export interface UniverseGitHubInstallation {
    readonly installationId: string;
    readonly accountLogin: string;
    /** `Organization` or `User`. */
    readonly accountType: string;
    /** For example `active`, `suspended`, or `deleted`. */
    readonly status: string;
    /** `all` or `selected`. */
    readonly repositorySelection: string;
    /** GitHub's page for this installation's repository access. */
    readonly settingsUrl: string;
    /** Projects bound through this installation; detaching needs zero. */
    readonly boundProjects: number;
    readonly missingPermissions?: readonly string[];
}
export interface UniverseGitHubHost {
    /**
     * Present means the Personal panel renders; `null` renders it as not
     * connected. Absent means the host has no such fact and the panel is
     * omitted.
     */
    readonly authorization?: UniverseGitHubAuthorization | null;
    readonly notices?: readonly UniverseGitHubNotice[];
    readonly installations?: readonly UniverseGitHubInstallation[];
    /** Starts or extends the GitHub connection; its label is the button's. */
    readonly connect?: UniverseAction;
    /** Shown only while `authorization` names an account. */
    readonly disconnectIdentity?: UniverseAction;
    /**
     * Invoked with the option `{ id: installationId, label: "Detach" }`;
     * disabled on a row whose `boundProjects` is above zero.
     */
    readonly detachInstallation?: UniverseAction;
}
