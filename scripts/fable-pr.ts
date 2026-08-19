#!/usr/bin/env bun

import { closeSync, constants, existsSync, fstatSync, openSync, readFileSync } from "node:fs";
import { createPrivateKey, createSign } from "node:crypto";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

const EXPECTED_DANCER_LOGIN = "dancer-automation[bot]";
const EXPECTED_DANCER_ACTOR_ID = 266699010;
const FABLE_REPOSITORY = "happycatlabs/fable";
const FABLE_REPOSITORY_ID = 979193317;
const INCIDENT_DAEMON_REPOSITORY = "happycatlabs/fable-incident-daemon";
const ALLOWED_REPOSITORIES = new Set([FABLE_REPOSITORY, INCIDENT_DAEMON_REPOSITORY]);
const GITHUB_API = "https://api.github.com";
const GITHUB_GRAPHQL = `${GITHUB_API}/graphql`;
const USER_AGENT = "bradley-skills-fable-pr";
const OWNER_MARKER_PREFIX = "<!-- fable-pr-owner/v1\n";
const OWNER_MARKER_SUFFIX = "\n-->";
const SHA_PATTERN = /^[a-f0-9]{40}$/u;
const UUID_PATTERN = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/iu;
const LINEAR_TICKET_PATTERN = /^FABLE-[1-9][0-9]*$/u;

export interface PullRequestInput {
  repo: string;
  base: string;
  head: string;
  title: string;
  body: string;
  labels: string[];
  adopt: boolean;
}

export interface PullRequestIdentity {
  repo: string;
  number: number;
  url: string;
  author: {
    login: string;
    actorId: number;
  };
  base: string;
  baseSha: string;
  head: {
    ref: string;
    sha: string;
  };
  draft: boolean;
}

export interface PullRequestProof extends PullRequestIdentity {
  adopted: boolean;
}

export interface ExactPullRequestAdoptionInput {
  repo: typeof FABLE_REPOSITORY;
  number: number;
  base: {
    ref: string;
    sha: string;
  };
  head: {
    ref: string;
    sha: string;
  };
}

export interface ExactPullRequestAdoptionProof extends PullRequestIdentity {
  adopted: true;
  exactGenerationVerified: true;
}

export interface ReadyPullRequestInput {
  repo: string;
  number: number;
}

export interface ReadyPullRequestProof extends PullRequestIdentity {
  owner: {
    taskId: string;
    linearTicket: string;
    sequence: number;
    attestationId: string;
  };
  readyTransitioned: boolean;
}

export interface ReadyDaemonPullRequestInput {
  repo: typeof INCIDENT_DAEMON_REPOSITORY;
  number: number;
  headSha: string;
}

export interface ReadyDaemonPullRequestProof extends PullRequestIdentity {
  readyTransitioned: boolean;
  exactHeadVerified: true;
}

interface GitHubRequest {
  path: string;
  method?: "GET" | "POST";
  body?: unknown;
}

export interface BrokerDependencies {
  mintToken: () => Promise<string>;
  request: (token: string, request: GitHubRequest) => Promise<unknown>;
  graphql: (token: string, query: string, variables?: Record<string, unknown>) => Promise<unknown>;
}

interface OwnerComment {
  id: number;
  actorId: number;
  editorId: number | null;
  editActorIds: number[];
  editsComplete: boolean;
  body: string;
}

interface ReadyOwnerProof {
  taskId: string;
  linearTicket: string;
  sequence: number;
  attestationId: string;
}

export type BrokerRequest =
  | { action: "create"; input: PullRequestInput }
  | { action: "adopt-exact"; input: ExactPullRequestAdoptionInput }
  | { action: "ready"; input: ReadyPullRequestInput }
  | { action: "ready-daemon"; input: ReadyDaemonPullRequestInput };

export interface LabelDependencies {
  gh: (args: string[], stdin?: string) => Promise<string>;
}

export async function createOrAdoptPullRequest(
  input: PullRequestInput,
  dependencies: BrokerDependencies,
): Promise<PullRequestProof> {
  validateInput(input);
  const [owner] = input.repo.split("/") as [string, string];
  const token = await dependencies.mintToken();
  await requireDancerIdentity(token, dependencies);

  const headRef = record(
    await dependencies.request(token, {
      path: `/repos/${encodePath(input.repo)}/git/ref/heads/${encodePath(input.head)}`,
    }),
  );
  const expectedHeadSha = text(record(headRef?.object)?.sha);
  if (!isSha(expectedHeadSha)) throw new Error("head_ref_invalid");

  const query = new URLSearchParams({
    state: "open",
    head: `${owner}:${input.head}`,
    per_page: "10",
  });
  const openPulls = await dependencies.request(token, {
    path: `/repos/${encodePath(input.repo)}/pulls?${query.toString()}`,
  });
  if (!Array.isArray(openPulls)) throw new Error("open_pr_list_invalid");
  if (openPulls.length > 1) throw new Error("open_pr_ambiguous");
  if (openPulls.length === 1 && !input.adopt) throw new Error("open_pr_exists");

  let number: number;
  let adopted = false;
  if (openPulls.length === 1) {
    number = integer(record(openPulls[0])?.number, "open_pr_invalid");
    adopted = true;
  } else {
    const created = record(
      await dependencies.request(token, {
        method: "POST",
        path: `/repos/${encodePath(input.repo)}/pulls`,
        body: {
          base: input.base,
          head: input.head,
          title: input.title,
          body: input.body,
          draft: true,
        },
      }),
    );
    number = integer(created?.number, "created_pr_invalid");
  }

  const proof = parsePullRequestProof(
    input,
    expectedHeadSha,
    number,
    adopted,
    await dependencies.request(token, {
      path: `/repos/${encodePath(input.repo)}/pulls/${number}`,
    }),
  );
  if (
    proof.author.login !== EXPECTED_DANCER_LOGIN ||
    proof.author.actorId !== EXPECTED_DANCER_ACTOR_ID
  ) {
    throw new Error("pr_author_mismatch");
  }
  if (!adopted && !proof.draft) throw new Error("created_pr_not_draft");
  if (
    proof.base !== input.base ||
    proof.head.ref !== input.head ||
    proof.head.sha !== expectedHeadSha
  ) {
    throw new Error("pr_head_mismatch");
  }

  return proof;
}

export async function adoptExactPullRequest(
  input: ExactPullRequestAdoptionInput,
  dependencies: BrokerDependencies,
): Promise<ExactPullRequestAdoptionProof> {
  validateExactAdoptionInput(input);
  const token = await dependencies.mintToken();

  const pullPath = `/repos/${encodePath(input.repo)}/pulls/${input.number}`;
  const initial = parseExactPullRequestAdoption(
    input,
    await dependencies.request(token, { path: pullPath }),
  );

  const remoteHead = strictRecord(
    await dependencies.request(token, {
      path: `/repos/${encodePath(input.repo)}/git/ref/heads/${encodePath(input.head.ref)}`,
    }),
  );
  const remoteHeadObject = strictRecord(remoteHead?.object);
  if (
    remoteHead?.ref !== `refs/heads/${input.head.ref}` ||
    remoteHeadObject?.type !== "commit" ||
    remoteHeadObject.sha !== input.head.sha
  ) {
    throw new Error("remote_head_mismatch");
  }

  const readback = parseExactPullRequestAdoption(
    input,
    await dependencies.request(token, { path: pullPath }),
  );
  assertSamePullRequestGeneration(initial, readback);

  return { ...readback, adopted: true, exactGenerationVerified: true };
}

export async function markPullRequestReady(
  input: ReadyPullRequestInput,
  dependencies: BrokerDependencies,
): Promise<ReadyPullRequestProof> {
  validateReadyInput(input);
  const token = await dependencies.mintToken();
  await requireDancerIdentity(token, dependencies);

  const initial = parseCurrentPullRequest(
    input,
    await dependencies.request(token, {
      path: `/repos/${encodePath(input.repo)}/pulls/${input.number}`,
    }),
  );
  assertDancerProof(initial);

  const owner = requireReadyOwnerProof(
    input,
    initial,
    await listOwnerComments(token, input, dependencies),
  );

  const beforeMutationValue = await dependencies.request(token, {
    path: `/repos/${encodePath(input.repo)}/pulls/${input.number}`,
  });
  const beforeMutation = parseCurrentPullRequest(input, beforeMutationValue);
  assertSamePullRequestGeneration(initial, beforeMutation);
  if (!beforeMutation.draft) {
    return { ...beforeMutation, owner, readyTransitioned: false };
  }

  const pullNodeId = currentPullRequestNodeId(beforeMutationValue);
  await dependencies.graphql(
    token,
    `mutation FablePrMarkReady($pullRequestId: ID!) {
      markPullRequestReadyForReview(input: { pullRequestId: $pullRequestId }) {
        pullRequest { id }
      }
    }`,
    { pullRequestId: pullNodeId },
  );

  const ready = parseCurrentPullRequest(
    input,
    await dependencies.request(token, {
      path: `/repos/${encodePath(input.repo)}/pulls/${input.number}`,
    }),
  );
  assertSamePullRequestGeneration(initial, ready);
  if (ready.draft) throw new Error("ready_transition_failed");
  return { ...ready, owner, readyTransitioned: true };
}

export async function markDaemonPullRequestReady(
  input: ReadyDaemonPullRequestInput,
  dependencies: BrokerDependencies,
): Promise<ReadyDaemonPullRequestProof> {
  validateReadyDaemonInput(input);
  const token = await dependencies.mintToken();
  await requireDancerIdentity(token, dependencies);

  const pullInput = { repo: input.repo, number: input.number };
  const initialValue = await dependencies.request(token, {
    path: `/repos/${encodePath(input.repo)}/pulls/${input.number}`,
  });
  const initial = parseCurrentPullRequest(pullInput, initialValue);
  assertDancerProof(initial);
  assertDaemonPullRequestGeneration(input, initial);

  const beforeMutation = parseCurrentPullRequest(
    pullInput,
    await dependencies.request(token, {
      path: `/repos/${encodePath(input.repo)}/pulls/${input.number}`,
    }),
  );
  assertSamePullRequestGeneration(initial, beforeMutation);
  assertDaemonPullRequestGeneration(input, beforeMutation);
  if (!beforeMutation.draft) {
    return { ...beforeMutation, readyTransitioned: false, exactHeadVerified: true };
  }

  await dependencies.graphql(
    token,
    `mutation FablePrMarkReady($pullRequestId: ID!) {
      markPullRequestReadyForReview(input: { pullRequestId: $pullRequestId }) {
        pullRequest { id }
      }
    }`,
    { pullRequestId: currentPullRequestNodeId(initialValue) },
  );

  const ready = parseCurrentPullRequest(
    pullInput,
    await dependencies.request(token, {
      path: `/repos/${encodePath(input.repo)}/pulls/${input.number}`,
    }),
  );
  assertSamePullRequestGeneration(initial, ready);
  assertDaemonPullRequestGeneration(input, ready);
  if (ready.draft) throw new Error("ready_transition_failed");
  return { ...ready, readyTransitioned: true, exactHeadVerified: true };
}

export async function applyLabels(
  proof: PullRequestProof,
  labels: string[],
  dependencies: LabelDependencies,
): Promise<void> {
  if (labels.length === 0) return;
  assertDancerProof(proof);

  const viewerOutput = await dependencies.gh([
    "api",
    "graphql",
    "-f",
    "query=query FablePrHumanViewer { viewer { login } }",
  ]);
  const viewer = record(record(parseJson(viewerOutput, "human_viewer_invalid"))?.data)?.viewer;
  const login = text(record(viewer)?.login);
  if (login === "" || login.endsWith("[bot]") || login === EXPECTED_DANCER_LOGIN) {
    throw new Error("ambient_gh_not_human");
  }

  await dependencies.gh(
    [
      "api",
      "--method",
      "POST",
      `/repos/${proof.repo}/issues/${proof.number}/labels`,
      "--input",
      "-",
    ],
    JSON.stringify({ labels }),
  );
}

function parsePullRequestProof(
  input: PullRequestInput,
  expectedHeadSha: string,
  number: number,
  adopted: boolean,
  value: unknown,
): PullRequestProof {
  const proof = parsePullRequestValue(input.repo, number, value);
  if (
    proof.base !== input.base ||
    proof.head.ref !== input.head ||
    proof.head.sha !== expectedHeadSha
  ) {
    throw new Error("pr_head_mismatch");
  }
  return { ...proof, adopted };
}

function parseCurrentPullRequest(
  input: ReadyPullRequestInput,
  value: unknown,
): PullRequestIdentity {
  return parsePullRequestValue(input.repo, input.number, value);
}

function parseExactPullRequestAdoption(
  input: ExactPullRequestAdoptionInput,
  value: unknown,
): PullRequestIdentity {
  const pull = strictRecord(value);
  const author = strictRecord(pull?.user);
  const base = strictRecord(pull?.base);
  const head = strictRecord(pull?.head);
  const baseRepo = strictRecord(base?.repo);
  const headRepo = strictRecord(head?.repo);
  const baseRepoId = baseRepo?.id;
  const headRepoId = headRepo?.id;
  const canonicalUrl = `https://github.com/${input.repo}/pull/${input.number}`;

  if (
    pull?.number !== input.number ||
    pull.html_url !== canonicalUrl ||
    pull.state !== "open" ||
    pull.merged !== false ||
    pull.merged_at !== null ||
    pull.draft !== true ||
    author?.login !== EXPECTED_DANCER_LOGIN ||
    author.id !== EXPECTED_DANCER_ACTOR_ID ||
    base?.ref !== input.base.ref ||
    base.sha !== input.base.sha ||
    head?.ref !== input.head.ref ||
    head.sha !== input.head.sha ||
    baseRepo?.full_name !== input.repo ||
    headRepo?.full_name !== input.repo ||
    baseRepoId !== FABLE_REPOSITORY_ID ||
    headRepoId !== FABLE_REPOSITORY_ID
  ) {
    throw new Error("exact_adoption_mismatch");
  }

  return {
    repo: input.repo,
    number: input.number,
    url: canonicalUrl,
    author: { login: EXPECTED_DANCER_LOGIN, actorId: EXPECTED_DANCER_ACTOR_ID },
    base: input.base.ref,
    baseSha: input.base.sha,
    head: { ref: input.head.ref, sha: input.head.sha },
    draft: true,
  };
}

function parsePullRequestValue(repo: string, number: number, value: unknown): PullRequestIdentity {
  const pull = record(value);
  const author = record(pull?.user);
  const base = record(pull?.base);
  const head = record(pull?.head);
  const headRepo = record(head?.repo);
  const url = text(pull?.html_url);
  const authorLogin = text(author?.login);
  const actorId = integer(author?.id, "pr_readback_invalid");
  const baseRef = text(base?.ref);
  const baseSha = text(base?.sha);
  const headRef = text(head?.ref);
  const headSha = text(head?.sha);
  if (
    pull?.number !== number ||
    url === "" ||
    pull?.state !== "open" ||
    authorLogin === "" ||
    baseRef === "" ||
    !isSha(baseSha) ||
    headRef === "" ||
    !isSha(headSha) ||
    typeof pull?.draft !== "boolean" ||
    headRepo?.full_name !== repo
  ) {
    throw new Error("pr_readback_invalid");
  }
  return {
    repo,
    number,
    url,
    author: { login: authorLogin, actorId },
    base: baseRef,
    baseSha,
    head: { ref: headRef, sha: headSha },
    draft: pull.draft,
  };
}

function currentPullRequestNodeId(value: unknown): string {
  const nodeId = text(record(value)?.node_id);
  if (nodeId === "") throw new Error("pr_node_id_invalid");
  return nodeId;
}

function assertSamePullRequestGeneration(
  expected: PullRequestIdentity,
  actual: PullRequestIdentity,
): void {
  if (
    actual.repo !== expected.repo ||
    actual.number !== expected.number ||
    actual.url !== expected.url ||
    actual.author.login !== expected.author.login ||
    actual.author.actorId !== expected.author.actorId ||
    actual.base !== expected.base ||
    actual.baseSha !== expected.baseSha ||
    actual.head.ref !== expected.head.ref ||
    actual.head.sha !== expected.head.sha
  ) {
    throw new Error("pr_generation_changed");
  }
}

function assertDaemonPullRequestGeneration(
  input: ReadyDaemonPullRequestInput,
  pull: PullRequestIdentity,
): void {
  if (
    pull.repo !== INCIDENT_DAEMON_REPOSITORY ||
    pull.base !== "master" ||
    pull.head.sha !== input.headSha
  ) {
    throw new Error("daemon_pr_generation_changed");
  }
}

async function requireDancerIdentity(
  token: string,
  dependencies: BrokerDependencies,
): Promise<void> {
  const viewer = record(
    record(await dependencies.graphql(token, "query FablePrViewer { viewer { login databaseId } }"))
      ?.viewer,
  );
  if (viewer?.login !== EXPECTED_DANCER_LOGIN || viewer.databaseId !== EXPECTED_DANCER_ACTOR_ID) {
    throw new Error("dancer_identity_mismatch");
  }
}

async function listOwnerComments(
  token: string,
  input: ReadyPullRequestInput,
  dependencies: BrokerDependencies,
): Promise<OwnerComment[]> {
  const [owner, repo] = input.repo.split("/") as [string, string];
  const comments: OwnerComment[] = [];
  let after: string | null = null;
  do {
    const response = record(
      await dependencies.graphql(
        token,
        `query FablePrOwnerComments(
          $owner: String!
          $repo: String!
          $number: Int!
          $after: String
        ) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $number) {
              comments(first: 100, after: $after) {
                nodes {
                  databaseId
                  body
                  lastEditedAt
                  author {
                    ... on User { databaseId }
                    ... on Bot { databaseId }
                  }
                  editor {
                    ... on User { databaseId }
                    ... on Bot { databaseId }
                  }
                  userContentEdits(first: 100) {
                    nodes {
                      editor {
                        ... on User { databaseId }
                        ... on Bot { databaseId }
                      }
                    }
                    pageInfo { hasNextPage }
                  }
                }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }`,
        { owner, repo, number: input.number, after },
      ),
    );
    const repository = record(response?.repository);
    const pullRequest = record(repository?.pullRequest);
    const connection = record(pullRequest?.comments);
    if (!Array.isArray(connection?.nodes)) throw new Error("owner_comments_invalid");
    for (const value of connection.nodes) {
      const comment = record(value);
      const edits = record(comment?.userContentEdits);
      const editPageInfo = record(edits?.pageInfo);
      comments.push({
        id: integer(comment?.databaseId, "owner_comment_invalid"),
        actorId: actorId(comment?.author),
        editorId: comment?.lastEditedAt === null ? null : actorId(comment?.editor),
        editActorIds: Array.isArray(edits?.nodes)
          ? edits.nodes.map((edit) => actorId(record(edit)?.editor))
          : [0],
        editsComplete: editPageInfo?.hasNextPage === false,
        body: text(comment?.body),
      });
    }
    const pageInfo = record(connection?.pageInfo);
    if (pageInfo?.hasNextPage !== true) return comments;
    after = text(pageInfo.endCursor);
    if (after === "") throw new Error("owner_comments_invalid");
  } while (after !== null);
  return comments;
}

function actorId(value: unknown): number {
  const databaseId = record(value)?.databaseId;
  return typeof databaseId === "number" && Number.isSafeInteger(databaseId) && databaseId > 0
    ? databaseId
    : 0;
}

function requireReadyOwnerProof(
  input: ReadyPullRequestInput,
  pull: PullRequestIdentity,
  comments: OwnerComment[],
): ReadyOwnerProof {
  const candidates = comments.filter(
    (comment) =>
      comment.actorId === EXPECTED_DANCER_ACTOR_ID && comment.body.includes(OWNER_MARKER_PREFIX),
  );
  if (candidates.length === 0) throw new Error("owner_marker_missing");
  if (candidates.length !== 1) throw new Error("owner_marker_ambiguous");

  const comment = candidates[0] as OwnerComment;
  if (
    !comment.editsComplete ||
    (comment.editorId !== null && comment.editorId !== EXPECTED_DANCER_ACTOR_ID) ||
    comment.editActorIds.some((id) => id !== EXPECTED_DANCER_ACTOR_ID)
  ) {
    throw new Error("owner_marker_untrusted");
  }

  const payloads = markerPayloads(comment.body);
  if (payloads.length !== 1 || payloads[0] === "") {
    throw new Error("owner_marker_malformed");
  }
  const marker = record(parseJson(payloads[0] as string, "owner_marker_malformed"));
  const verification = record(marker?.verification);
  const taskId = text(marker?.taskId);
  const linearTicket = text(marker?.linearTicket);
  const sequence = marker?.sequence;
  const attestationId = text(verification?.attestationId);

  if (
    marker?.schemaVersion !== "fable-pr-owner/v1" ||
    marker.repository !== input.repo ||
    marker.pullNumber !== input.number ||
    marker.dispositionVersion !== "fable-pr-disposition/v1" ||
    typeof sequence !== "number" ||
    !Number.isSafeInteger(sequence) ||
    sequence < 1 ||
    !UUID_PATTERN.test(text(marker.writeNonce)) ||
    !UUID_PATTERN.test(taskId) ||
    !LINEAR_TICKET_PATTERN.test(linearTicket) ||
    marker.ownedHeadSha !== pull.head.sha ||
    marker.baseRef !== pull.base ||
    marker.baseSha !== pull.baseSha ||
    verification?.source !== "originating_task" ||
    verification?.version !== "fable-task-verification/v1" ||
    verification?.status !== "passed" ||
    attestationId === "" ||
    verification?.taskId !== taskId ||
    verification?.linearTicket !== linearTicket ||
    verification?.pullNumber !== input.number ||
    verification?.headSha !== pull.head.sha ||
    verification?.baseRef !== pull.base ||
    verification?.baseSha !== pull.baseSha
  ) {
    throw new Error("owner_marker_not_ready");
  }
  return { taskId, linearTicket, sequence, attestationId };
}

function markerPayloads(body: string): string[] {
  const payloads: string[] = [];
  let cursor = 0;
  while (cursor < body.length) {
    const start = body.indexOf(OWNER_MARKER_PREFIX, cursor);
    if (start === -1) break;
    const contentStart = start + OWNER_MARKER_PREFIX.length;
    const end = body.indexOf(OWNER_MARKER_SUFFIX, contentStart);
    if (end === -1) {
      payloads.push("");
      break;
    }
    payloads.push(body.slice(contentStart, end));
    cursor = end + OWNER_MARKER_SUFFIX.length;
  }
  return payloads;
}

function assertDancerProof(proof: PullRequestIdentity, input?: PullRequestInput): void {
  if (
    proof.author.login !== EXPECTED_DANCER_LOGIN ||
    proof.author.actorId !== EXPECTED_DANCER_ACTOR_ID ||
    !isSha(proof.head.sha) ||
    !isSha(proof.baseSha) ||
    typeof proof.draft !== "boolean" ||
    !Number.isSafeInteger(proof.number) ||
    proof.number < 1 ||
    proof.url !== `https://github.com/${proof.repo}/pull/${proof.number}` ||
    (input !== undefined &&
      (proof.repo !== input.repo || proof.base !== input.base || proof.head.ref !== input.head))
  ) {
    throw new Error("dancer_proof_invalid");
  }
}

function assertReadyProof(proof: ReadyPullRequestProof, input: ReadyPullRequestInput): void {
  assertDancerProof(proof);
  if (
    proof.repo !== input.repo ||
    proof.number !== input.number ||
    proof.draft ||
    typeof proof.readyTransitioned !== "boolean" ||
    !UUID_PATTERN.test(proof.owner?.taskId ?? "") ||
    !LINEAR_TICKET_PATTERN.test(proof.owner?.linearTicket ?? "") ||
    !Number.isSafeInteger(proof.owner?.sequence) ||
    proof.owner.sequence < 1 ||
    text(proof.owner?.attestationId) === ""
  ) {
    throw new Error("ready_proof_invalid");
  }
}

function validateInput(input: PullRequestInput): void {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/u.test(input.repo)) {
    throw new Error("repo_invalid");
  }
  if (!ALLOWED_REPOSITORIES.has(input.repo)) throw new Error("repo_not_allowed");
  for (const [name, value] of [
    ["base", input.base],
    ["head", input.head],
  ] as const) {
    if (
      value === "" ||
      value.startsWith("-") ||
      value.includes("..") ||
      /[\s~^:?*[\]\\]/u.test(value)
    ) {
      throw new Error(`${name}_invalid`);
    }
  }
  if (input.title.trim() === "") throw new Error("title_required");
  if (typeof input.body !== "string") throw new Error("body_required");
  if (
    !Array.isArray(input.labels) ||
    input.labels.some((label) => label.trim() === "" || /[\r\n]/u.test(label))
  ) {
    throw new Error("labels_invalid");
  }
}

function validateReadyInput(input: ReadyPullRequestInput): void {
  if (input.repo !== FABLE_REPOSITORY) throw new Error("repo_not_fable");
  if (!Number.isSafeInteger(input.number) || input.number < 1) {
    throw new Error("pull_number_invalid");
  }
}

function validateReadyDaemonInput(input: ReadyDaemonPullRequestInput): void {
  if (input.repo !== INCIDENT_DAEMON_REPOSITORY) throw new Error("repo_not_incident_daemon");
  if (!Number.isSafeInteger(input.number) || input.number < 1) {
    throw new Error("pull_number_invalid");
  }
  if (!isSha(input.headSha)) throw new Error("head_sha_invalid");
}

function defaultBrokerDependencies(): BrokerDependencies {
  return {
    mintToken: mintInstallationToken,
    request: githubRequest,
    graphql: githubGraphql,
  };
}

async function mintInstallationToken(): Promise<string> {
  const configDir = resolve(
    process.env.FABLE_PR_DANCER_CONFIG_DIR ?? join(homedir(), ".config/fable-incident-daemon"),
  );
  const values = {
    ...readEnvFile(join(configDir, "config.env")),
    ...readEnvFile(join(configDir, "secrets.env")),
    ...process.env,
  };
  const appId = requiredConfig(values.FABLE_INCIDENT_GITHUB_APP_ID);
  const installationId = requiredConfig(values.FABLE_INCIDENT_GITHUB_INSTALLATION_ID);
  const keyPath = resolve(
    values.FABLE_INCIDENT_GITHUB_PRIVATE_KEY_PATH ?? join(configDir, "github-app-private-key.pem"),
  );
  const privateKey = readPrivateKey(keyPath);
  const now = Math.floor(Date.now() / 1000);
  const header = base64Url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = base64Url(JSON.stringify({ iat: now - 60, exp: now + 9 * 60, iss: appId }));
  const unsigned = `${header}.${payload}`;
  const signer = createSign("RSA-SHA256");
  signer.update(unsigned);
  signer.end();
  const signature = signer.sign(createPrivateKey(privateKey)).toString("base64url");
  const appJwt = `${unsigned}.${signature}`;
  const response = await fetch(
    `${GITHUB_API}/app/installations/${encodeURIComponent(installationId)}/access_tokens`,
    {
      method: "POST",
      headers: githubHeaders(appJwt),
      body: "{}",
      signal: AbortSignal.timeout(30_000),
    },
  );
  const result = record(await responseJson(response, "installation_token_request_failed"));
  const token = text(result?.token);
  if (token === "") throw new Error("installation_token_missing");
  return token;
}

async function githubRequest(token: string, request: GitHubRequest): Promise<unknown> {
  const method = request.method ?? "GET";
  const response = await fetch(`${GITHUB_API}${request.path}`, {
    method,
    headers: githubHeaders(token),
    body: method === "POST" ? JSON.stringify(request.body ?? {}) : undefined,
    signal: AbortSignal.timeout(30_000),
  });
  return responseJson(response, `github_${method.toLowerCase()}_failed`);
}

async function githubGraphql(
  token: string,
  query: string,
  variables: Record<string, unknown> = {},
): Promise<unknown> {
  const response = await fetch(GITHUB_GRAPHQL, {
    method: "POST",
    headers: githubHeaders(token),
    body: JSON.stringify({ query, variables }),
    signal: AbortSignal.timeout(30_000),
  });
  const result = record(await responseJson(response, "github_graphql_failed"));
  if (Array.isArray(result?.errors) && result.errors.length > 0) {
    throw new Error("github_graphql_failed");
  }
  return result?.data;
}

async function responseJson(response: Response, errorCode: string): Promise<unknown> {
  if (!response.ok) throw new Error(`${errorCode}_${response.status}`);
  try {
    return await response.json();
  } catch {
    throw new Error(`${errorCode}_invalid_json`);
  }
}

function githubHeaders(token: string): Record<string, string> {
  return {
    accept: "application/vnd.github+json",
    authorization: `Bearer ${token}`,
    "content-type": "application/json",
    "user-agent": USER_AGENT,
    "x-github-api-version": "2022-11-28",
  };
}

function readPrivateKey(path: string): string {
  let descriptor: number | null = null;
  try {
    descriptor = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW);
    const metadata = fstatSync(descriptor);
    if (
      !metadata.isFile() ||
      metadata.nlink !== 1 ||
      (metadata.mode & 0o077) !== 0 ||
      (typeof process.getuid === "function" && metadata.uid !== process.getuid())
    ) {
      throw new Error("dancer_private_key_unsafe");
    }
    return readFileSync(descriptor, "utf8").replaceAll("\\n", "\n");
  } catch (error) {
    if (error instanceof Error && error.message === "dancer_private_key_unsafe") throw error;
    throw new Error("dancer_private_key_unavailable");
  } finally {
    if (descriptor !== null) closeSync(descriptor);
  }
}

function readEnvFile(path: string): Record<string, string> {
  if (!existsSync(path)) return {};
  const values: Record<string, string> = {};
  for (const rawLine of readFileSync(path, "utf8").split(/\r?\n/u)) {
    const line = rawLine.trim();
    if (line === "" || line.startsWith("#")) continue;
    const match = /^(?:export\s+)?([A-Z0-9_]+)=(.*)$/u.exec(line);
    if (match === null) continue;
    const value = match[2]?.trim() ?? "";
    values[match[1] as string] =
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
        ? value.slice(1, -1)
        : value;
  }
  return values;
}

function requiredConfig(value: string | undefined): string {
  const normalized = value?.trim() ?? "";
  if (normalized === "") throw new Error("dancer_app_not_configured");
  return normalized;
}

function base64Url(value: string): string {
  return Buffer.from(value, "utf8").toString("base64url");
}

function encodePath(value: string): string {
  return value.split("/").map(encodeURIComponent).join("/");
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function strictRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function exactRecord(value: unknown, keys: string[]): Record<string, unknown> | null {
  const candidate = strictRecord(value);
  if (candidate === null) return null;
  const actualKeys = Object.keys(candidate).sort();
  const expectedKeys = [...keys].sort();
  return JSON.stringify(actualKeys) === JSON.stringify(expectedKeys) ? candidate : null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function integer(value: unknown, errorCode: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) {
    throw new Error(errorCode);
  }
  return value;
}

function isSha(value: string): boolean {
  return SHA_PATTERN.test(value);
}

function parseJson(value: string, errorCode: string): unknown {
  try {
    return JSON.parse(value) as unknown;
  } catch {
    throw new Error(errorCode);
  }
}

export function parseBrokerRequest(value: unknown): BrokerRequest {
  const request = record(value);
  if (request?.action === "adopt-exact") {
    return { action: "adopt-exact", input: parseExactAdoptionInput(request.input) };
  }
  if (request?.action === "ready-daemon") {
    const input = record(request.input);
    const readyInput = {
      repo: text(input?.repo),
      number: input?.number,
      headSha: text(input?.headSha),
    } as ReadyDaemonPullRequestInput;
    validateReadyDaemonInput(readyInput);
    return { action: "ready-daemon", input: readyInput };
  }
  if (request?.action === "ready") {
    const input = record(request.input);
    const readyInput = {
      repo: text(input?.repo),
      number: input?.number,
    } as ReadyPullRequestInput;
    validateReadyInput(readyInput);
    return { action: "ready", input: readyInput };
  }
  if (request?.action === "create") {
    return { action: "create", input: parseBrokerPullRequestInput(request.input) };
  }
  if (request !== null && Object.prototype.hasOwnProperty.call(request, "action")) {
    throw new Error("broker_action_invalid");
  }

  return { action: "create", input: parseBrokerPullRequestInput(value) };
}

function parseExactAdoptionInput(value: unknown): ExactPullRequestAdoptionInput {
  const input = exactRecord(value, ["repo", "number", "base", "head"]);
  const base = exactRecord(input?.base, ["ref", "sha"]);
  const head = exactRecord(input?.head, ["ref", "sha"]);
  if (input === null || base === null || head === null) {
    throw new Error("broker_input_invalid");
  }
  const parsed = {
    repo: text(input?.repo),
    number: input?.number,
    base: { ref: text(base?.ref), sha: text(base?.sha) },
    head: { ref: text(head?.ref), sha: text(head?.sha) },
  } as ExactPullRequestAdoptionInput;
  validateExactAdoptionInput(parsed);
  return parsed;
}

function parseBrokerPullRequestInput(value: unknown): PullRequestInput {
  const input = record(value);
  if (input === null || typeof input.body !== "string" || typeof input.adopt !== "boolean") {
    throw new Error("broker_input_invalid");
  }
  const parsed: PullRequestInput = {
    repo: text(input.repo),
    base: text(input.base),
    head: text(input.head),
    title: text(input.title),
    body: input.body,
    labels: Array.isArray(input.labels) ? input.labels.map(text) : [],
    adopt: input.adopt,
  };
  validateInput(parsed);
  return parsed;
}

function parseArguments(args: string[]): PullRequestInput {
  const values = new Map<string, string>();
  const labels: string[] = [];
  let adopt = false;
  for (let index = 0; index < args.length; index += 1) {
    const name = args[index];
    if (name === "--adopt") {
      adopt = true;
      continue;
    }
    if (!["--repo", "--base", "--head", "--title", "--body", "--label"].includes(name ?? "")) {
      throw new Error("arguments_invalid");
    }
    const value = args[index + 1];
    if (value === undefined) throw new Error("arguments_invalid");
    index += 1;
    if (name === "--label") labels.push(value);
    else {
      if (values.has(name as string)) throw new Error("arguments_invalid");
      values.set(name as string, value);
    }
  }
  for (const required of ["--repo", "--base", "--head", "--title", "--body"]) {
    if (!values.has(required)) throw new Error("arguments_invalid");
  }
  const input: PullRequestInput = {
    repo: values.get("--repo") ?? "",
    base: values.get("--base") ?? "",
    head: values.get("--head") ?? "",
    title: values.get("--title") ?? "",
    body: values.get("--body") ?? "",
    labels: [...new Set(labels)],
    adopt,
  };
  validateInput(input);
  return input;
}

function parseReadyArguments(args: string[]): ReadyPullRequestInput {
  const values = new Map<string, string>();
  for (let index = 0; index < args.length; index += 1) {
    const name = args[index];
    if (!["--repo", "--pr"].includes(name ?? "")) {
      throw new Error("arguments_invalid");
    }
    const value = args[index + 1];
    if (value === undefined || values.has(name as string)) {
      throw new Error("arguments_invalid");
    }
    values.set(name as string, value);
    index += 1;
  }
  if (!values.has("--repo") || !values.has("--pr")) {
    throw new Error("arguments_invalid");
  }
  const input = {
    repo: values.get("--repo") ?? "",
    number: Number(values.get("--pr")),
  };
  validateReadyInput(input);
  return input;
}

function parseReadyDaemonArguments(args: string[]): ReadyDaemonPullRequestInput {
  const values = new Map<string, string>();
  for (let index = 0; index < args.length; index += 1) {
    const name = args[index];
    if (!["--repo", "--pr", "--head"].includes(name ?? "")) {
      throw new Error("arguments_invalid");
    }
    const value = args[index + 1];
    if (value === undefined || values.has(name as string)) {
      throw new Error("arguments_invalid");
    }
    values.set(name as string, value);
    index += 1;
  }
  if (!values.has("--repo") || !values.has("--pr") || !values.has("--head")) {
    throw new Error("arguments_invalid");
  }
  const input = {
    repo: values.get("--repo") ?? "",
    number: Number(values.get("--pr")),
    headSha: values.get("--head") ?? "",
  } as ReadyDaemonPullRequestInput;
  validateReadyDaemonInput(input);
  return input;
}

function validateExactAdoptionInput(input: ExactPullRequestAdoptionInput): void {
  const candidate = strictRecord(input);
  const base = strictRecord(candidate?.base);
  const head = strictRecord(candidate?.head);
  if (candidate?.repo !== FABLE_REPOSITORY) throw new Error("repo_not_fable");
  if (
    typeof candidate.number !== "number" ||
    !Number.isSafeInteger(candidate.number) ||
    candidate.number < 1
  ) {
    throw new Error("pull_number_invalid");
  }
  for (const [name, value] of [
    ["base_ref", text(base?.ref)],
    ["head_ref", text(head?.ref)],
  ] as const) {
    if (
      value === "" ||
      value.startsWith("-") ||
      value.includes("..") ||
      /[\s~^:?*[\]\\]/u.test(value)
    ) {
      throw new Error(`${name}_invalid`);
    }
  }
  if (!isSha(text(base?.sha))) throw new Error("base_sha_invalid");
  if (!isSha(text(head?.sha))) throw new Error("head_sha_invalid");
}

async function runGh(args: string[], stdin?: string): Promise<string> {
  const process = Bun.spawn(["gh", ...args], {
    stdin: stdin === undefined ? undefined : "pipe",
    stdout: "pipe",
    stderr: "pipe",
  });
  if (stdin !== undefined) {
    process.stdin.write(stdin);
    await process.stdin.end();
  }
  const [exitCode, stdout] = await Promise.all([
    process.exited,
    new Response(process.stdout).text(),
    new Response(process.stderr).text(),
  ]);
  if (exitCode !== 0) throw new Error("ambient_gh_failed");
  return stdout;
}

async function runRemoteBroker(request: BrokerRequest): Promise<unknown> {
  const host = process.env.FABLE_PR_EVE_HOST ?? "eve";
  if (!/^[A-Za-z0-9._-]+$/u.test(host)) throw new Error("eve_host_invalid");
  const command =
    'exec "$HOME/.bun/bin/bun" "$HOME/code/bradley-skills/scripts/fable-pr.ts" --broker';
  const child = Bun.spawn(["ssh", host, command], {
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
  });
  child.stdin.write(JSON.stringify(request));
  await child.stdin.end();
  const [exitCode, stdout] = await Promise.all([
    child.exited,
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
  ]);
  if (exitCode !== 0) throw new Error("remote_broker_failed");
  return parseJson(stdout, "remote_broker_invalid");
}

function canMintLocally(): boolean {
  if (process.env.FABLE_PR_TOKEN_MODE === "local") return true;
  if (process.env.FABLE_PR_TOKEN_MODE === "eve") return false;

  const configDir = resolve(
    process.env.FABLE_PR_DANCER_CONFIG_DIR ?? join(homedir(), ".config/fable-incident-daemon"),
  );
  const values = {
    ...readEnvFile(join(configDir, "config.env")),
    ...readEnvFile(join(configDir, "secrets.env")),
    ...process.env,
  };
  const keyPath = resolve(
    values.FABLE_INCIDENT_GITHUB_PRIVATE_KEY_PATH ?? join(configDir, "github-app-private-key.pem"),
  );
  return (
    (values.FABLE_INCIDENT_GITHUB_APP_ID?.trim() ?? "") !== "" &&
    (values.FABLE_INCIDENT_GITHUB_INSTALLATION_ID?.trim() ?? "") !== "" &&
    existsSync(keyPath)
  );
}

async function readStdin(): Promise<string> {
  return new Response(Bun.stdin.stream()).text();
}

async function main(): Promise<void> {
  if (process.argv[2] === "--broker") {
    const request = parseBrokerRequest(parseJson(await readStdin(), "broker_input_invalid"));
    const proof =
      request.action === "adopt-exact"
        ? await adoptExactPullRequest(request.input, defaultBrokerDependencies())
        : request.action === "ready-daemon"
          ? await markDaemonPullRequestReady(request.input, defaultBrokerDependencies())
          : request.action === "ready"
            ? await markPullRequestReady(request.input, defaultBrokerDependencies())
            : await createOrAdoptPullRequest(request.input, defaultBrokerDependencies());
    process.stdout.write(`${JSON.stringify(proof)}\n`);
    return;
  }

  const args = process.argv.slice(2);
  if (args[0] === "ready-daemon") {
    const input = parseReadyDaemonArguments(args.slice(1));
    const proof = canMintLocally()
      ? await markDaemonPullRequestReady(input, defaultBrokerDependencies())
      : ((await runRemoteBroker({
          action: "ready-daemon",
          input,
        })) as ReadyDaemonPullRequestProof);
    assertDancerProof(proof);
    assertDaemonPullRequestGeneration(input, proof);
    if (proof.draft || proof.exactHeadVerified !== true) throw new Error("dancer_proof_invalid");
    process.stdout.write(`${JSON.stringify(proof)}\n`);
    return;
  }
  if (args[0] === "ready") {
    const input = parseReadyArguments(args.slice(1));
    const proof = canMintLocally()
      ? await markPullRequestReady(input, defaultBrokerDependencies())
      : ((await runRemoteBroker({
          action: "ready",
          input,
        })) as ReadyPullRequestProof);
    assertReadyProof(proof, input);
    process.stdout.write(`${JSON.stringify(proof)}\n`);
    return;
  }

  const input = parseArguments(args[0] === "create" ? args.slice(1) : args);
  const proof = canMintLocally()
    ? await createOrAdoptPullRequest(input, defaultBrokerDependencies())
    : ((await runRemoteBroker({
        action: "create",
        input,
      })) as PullRequestProof);
  assertDancerProof(proof, input);
  await applyLabels(proof, input.labels, { gh: runGh });
  process.stdout.write(
    `${JSON.stringify({
      ...proof,
      labels: input.labels,
      labelsAppliedBy: input.labels.length > 0 ? "ambient-gh" : null,
    })}\n`,
  );
}

if (import.meta.main) {
  main().catch((error: unknown) => {
    const code =
      error instanceof Error && /^[a-z0-9_]+(?:_[0-9]{3})?$/u.test(error.message)
        ? error.message
        : "failed";
    process.stderr.write(`fable-pr: ${code}\n`);
    process.exitCode = 1;
  });
}
