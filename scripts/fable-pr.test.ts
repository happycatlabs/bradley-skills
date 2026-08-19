import { describe, expect, test } from "bun:test";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  adoptExactPullRequest,
  applyLabels,
  createOrAdoptPullRequest,
  markDaemonPullRequestReady,
  markPullRequestReady,
  parseBrokerRequest,
  type BrokerDependencies,
  type ExactPullRequestAdoptionInput,
  type PullRequestInput,
  type PullRequestProof,
} from "./fable-pr";

const TOKEN = "installation-token-must-stay-private";
const SHA = "0123456789abcdef0123456789abcdef01234567";
const BASE_SHA = "89abcdef0123456789abcdef0123456789abcdef";
const FABLE_REPO_ID = 979_193_317;
const TASK_ID = "01900000-0000-7000-8000-000000000001";
const ATTESTATION_ID = "01900000-0000-7000-8000-000000000003";
const INPUT: PullRequestInput = {
  repo: "happycatlabs/fable",
  base: "master",
  head: "codex/fable-123",
  title: "Fix FABLE-123",
  body: "Closes FABLE-123.",
  labels: [],
  adopt: false,
};
const EXACT_INPUT: ExactPullRequestAdoptionInput = {
  repo: "happycatlabs/fable",
  number: 42,
  base: { ref: "master", sha: BASE_SHA },
  head: { ref: "codex/fable-123", sha: SHA },
};
const DAEMON_REPO = "happycatlabs/fable-incident-daemon";
const DAEMON_HEAD = "codex/fable-324-325-expected-denial-correlation";
const DAEMON_INPUT: PullRequestInput = {
  repo: DAEMON_REPO,
  base: "master",
  head: DAEMON_HEAD,
  title: "Fix FABLE-324 and FABLE-325",
  body: "Closes FABLE-324 and FABLE-325.",
  labels: [],
  adopt: false,
};

function pull(number = 42, overrides: Record<string, unknown> = {}) {
  return {
    number,
    node_id: "PR_kwDOExample",
    html_url: `https://github.com/happycatlabs/fable/pull/${number}`,
    state: "open",
    draft: true,
    user: { login: "dancer-automation[bot]", id: 266699010 },
    base: { ref: "master", sha: BASE_SHA },
    head: {
      ref: "codex/fable-123",
      sha: SHA,
      repo: { full_name: "happycatlabs/fable" },
    },
    ...overrides,
  };
}

function daemonPull(number = 42, overrides: Record<string, unknown> = {}) {
  return pull(number, {
    html_url: `https://github.com/${DAEMON_REPO}/pull/${number}`,
    head: {
      ref: DAEMON_HEAD,
      sha: SHA,
      repo: { full_name: DAEMON_REPO },
    },
    ...overrides,
  });
}

function exactPull(overrides: Record<string, unknown> = {}) {
  return pull(42, {
    merged: false,
    merged_at: null,
    base: {
      ref: EXACT_INPUT.base.ref,
      sha: EXACT_INPUT.base.sha,
      repo: { id: FABLE_REPO_ID, full_name: EXACT_INPUT.repo },
    },
    head: {
      ref: EXACT_INPUT.head.ref,
      sha: EXACT_INPUT.head.sha,
      repo: { id: FABLE_REPO_ID, full_name: EXACT_INPUT.repo },
    },
    ...overrides,
  });
}

function broker(
  options: {
    viewer?: unknown;
    openPulls?: unknown[];
    readback?: unknown;
  } = {},
) {
  const calls: Array<{
    token: string;
    method: string;
    path: string;
    body?: unknown;
  }> = [];
  const dependencies: BrokerDependencies = {
    mintToken: async () => TOKEN,
    graphql: async (token) => {
      calls.push({ token, method: "GRAPHQL", path: "viewer" });
      return (
        options.viewer ?? {
          viewer: { login: "dancer-automation[bot]", databaseId: 266699010 },
        }
      );
    },
    request: async (token, request) => {
      const method = request.method ?? "GET";
      calls.push({ token, method, path: request.path, body: request.body });
      if (request.path.includes("/git/ref/heads/")) return { object: { sha: SHA } };
      if (request.path.includes("/pulls?")) return options.openPulls ?? [];
      if (method === "POST") return { number: 42 };
      if (request.path.endsWith("/pulls/42")) return options.readback ?? pull();
      throw new Error("unexpected_test_request");
    },
  };
  return { dependencies, calls };
}

function exactAdoptionBroker(
  options: {
    readbacks?: unknown[];
    remoteHead?: unknown;
  } = {},
) {
  const calls: Array<{ token: string; method: string; path: string }> = [];
  const readbacks = [...(options.readbacks ?? [exactPull(), exactPull()])];
  const dependencies: BrokerDependencies = {
    mintToken: async () => TOKEN,
    graphql: async () => {
      throw new Error("unexpected_test_graphql");
    },
    request: async (token, request) => {
      const method = request.method ?? "GET";
      calls.push({ token, method, path: request.path });
      if (request.path.endsWith("/pulls/42")) return readbacks.shift();
      if (request.path.includes("/git/ref/heads/")) {
        return (
          options.remoteHead ?? {
            ref: `refs/heads/${EXACT_INPUT.head.ref}`,
            object: { type: "commit", sha: EXACT_INPUT.head.sha },
          }
        );
      }
      throw new Error("unexpected_test_request");
    },
  };
  return { dependencies, calls };
}

describe("createOrAdoptPullRequest", () => {
  test("verifies Dancer, creates, and reads back the exact head", async () => {
    const { dependencies, calls } = broker();
    const proof = await createOrAdoptPullRequest(INPUT, dependencies);

    expect(proof).toEqual({
      repo: "happycatlabs/fable",
      number: 42,
      url: "https://github.com/happycatlabs/fable/pull/42",
      author: { login: "dancer-automation[bot]", actorId: 266699010 },
      base: "master",
      baseSha: BASE_SHA,
      head: { ref: "codex/fable-123", sha: SHA },
      draft: true,
      adopted: false,
    });
    expect(calls.map(({ method, path }) => `${method} ${path}`)).toEqual([
      "GRAPHQL viewer",
      "GET /repos/happycatlabs/fable/git/ref/heads/codex/fable-123",
      "GET /repos/happycatlabs/fable/pulls?state=open&head=happycatlabs%3Acodex%2Ffable-123&per_page=10",
      "POST /repos/happycatlabs/fable/pulls",
      "GET /repos/happycatlabs/fable/pulls/42",
    ]);
    expect(calls.find((call) => call.method === "POST")?.body).toEqual({
      base: INPUT.base,
      head: INPUT.head,
      title: INPUT.title,
      body: INPUT.body,
      draft: true,
    });
    expect(JSON.stringify(proof)).not.toContain(TOKEN);
  });

  test("fails before repository access when the GraphQL actor is wrong", async () => {
    const { dependencies, calls } = broker({
      viewer: { viewer: { login: "ratley", databaseId: 1 } },
    });

    await expect(createOrAdoptPullRequest(INPUT, dependencies)).rejects.toThrow(
      "dancer_identity_mismatch",
    );
    expect(calls).toHaveLength(1);
  });

  test("refuses an existing open PR unless adoption is explicit", async () => {
    const { dependencies } = broker({ openPulls: [{ number: 42 }] });

    await expect(createOrAdoptPullRequest(INPUT, dependencies)).rejects.toThrow("open_pr_exists");
  });

  test("explicit adoption still requires Dancer authorship and exact head", async () => {
    const { dependencies, calls } = broker({ openPulls: [{ number: 42 }] });
    const proof = await createOrAdoptPullRequest({ ...INPUT, adopt: true }, dependencies);

    expect(proof.adopted).toBe(true);
    expect(calls.some((call) => call.method === "POST")).toBe(false);
  });

  test("fails closed when readback identity or head differs", async () => {
    const wrongAuthor = broker({
      readback: pull(42, { user: { login: "ratley", id: 1 } }),
    });
    await expect(createOrAdoptPullRequest(INPUT, wrongAuthor.dependencies)).rejects.toThrow(
      "pr_author_mismatch",
    );

    const wrongHead = broker({
      readback: pull(42, {
        head: {
          ref: "codex/other",
          sha: SHA,
          repo: { full_name: "happycatlabs/fable" },
        },
      }),
    });
    await expect(createOrAdoptPullRequest(INPUT, wrongHead.dependencies)).rejects.toThrow(
      "pr_head_mismatch",
    );

    const unexpectedlyReady = broker({
      readback: pull(42, { draft: false }),
    });
    await expect(createOrAdoptPullRequest(INPUT, unexpectedlyReady.dependencies)).rejects.toThrow(
      "created_pr_not_draft",
    );
  });

  test("creates an exact-head draft in the explicitly allowed incident daemon repo", async () => {
    const { dependencies, calls } = broker({ readback: daemonPull() });
    const proof = await createOrAdoptPullRequest(DAEMON_INPUT, dependencies);

    expect(proof).toMatchObject({
      repo: DAEMON_REPO,
      number: 42,
      url: `https://github.com/${DAEMON_REPO}/pull/42`,
      author: { login: "dancer-automation[bot]", actorId: 266699010 },
      base: "master",
      head: { ref: DAEMON_HEAD, sha: SHA },
      draft: true,
      adopted: false,
    });
    expect(calls.map(({ method, path }) => `${method} ${path}`)).toEqual([
      "GRAPHQL viewer",
      `GET /repos/${DAEMON_REPO}/git/ref/heads/${DAEMON_HEAD}`,
      `GET /repos/${DAEMON_REPO}/pulls?state=open&head=happycatlabs%3A${encodeURIComponent(DAEMON_HEAD)}&per_page=10`,
      `POST /repos/${DAEMON_REPO}/pulls`,
      `GET /repos/${DAEMON_REPO}/pulls/42`,
    ]);
  });

  test("rejects repositories outside the explicit allowlist before minting a token", async () => {
    const { dependencies, calls } = broker();
    await expect(
      createOrAdoptPullRequest({ ...INPUT, repo: "happycatlabs/other" }, dependencies),
    ).rejects.toThrow("repo_not_allowed");
    expect(calls).toHaveLength(0);
  });
});

describe("adoptExactPullRequest", () => {
  test("parses only the exact broker request schema", () => {
    const request = {
      action: "adopt-exact",
      input: {
        repo: EXACT_INPUT.repo,
        number: EXACT_INPUT.number,
        base: EXACT_INPUT.base,
        head: EXACT_INPUT.head,
      },
    };

    expect(parseBrokerRequest(request)).toEqual(request);
    expect(() =>
      parseBrokerRequest({
        ...request,
        input: { ...request.input, fallback: "create" },
      }),
    ).toThrow("broker_input_invalid");
    expect(() =>
      parseBrokerRequest({
        ...request,
        input: { ...request.input, head: { ...request.input.head, branchList: true } },
      }),
    ).toThrow("broker_input_invalid");
    expect(() =>
      parseBrokerRequest({
        ...INPUT,
        action: "adopt-excat",
      }),
    ).toThrow("broker_action_invalid");
  });

  test("adopts only the exact numbered Dancer draft and verifies its remote head", async () => {
    const { dependencies, calls } = exactAdoptionBroker();

    const proof = await adoptExactPullRequest(EXACT_INPUT, dependencies);

    expect(proof).toEqual({
      repo: EXACT_INPUT.repo,
      number: EXACT_INPUT.number,
      url: "https://github.com/happycatlabs/fable/pull/42",
      author: { login: "dancer-automation[bot]", actorId: 266699010 },
      base: EXACT_INPUT.base.ref,
      baseSha: EXACT_INPUT.base.sha,
      head: EXACT_INPUT.head,
      draft: true,
      adopted: true,
      exactGenerationVerified: true,
    });
    expect(calls.map(({ method, path }) => `${method} ${path}`)).toEqual([
      "GET /repos/happycatlabs/fable/pulls/42",
      "GET /repos/happycatlabs/fable/git/ref/heads/codex/fable-123",
      "GET /repos/happycatlabs/fable/pulls/42",
    ]);
    expect(calls.some((call) => call.method === "POST" || call.path.includes("/pulls?"))).toBe(
      false,
    );
    expect(JSON.stringify(proof)).not.toContain(TOKEN);
  });

  test("never falls back to a POST or branch-list adoption for missing, closed, mismatched, or ambiguous readback", async () => {
    const scenarios: Array<{ name: string; readback: unknown }> = [
      { name: "missing", readback: null },
      { name: "closed", readback: exactPull({ state: "closed" }) },
      { name: "merged", readback: exactPull({ merged: true, merged_at: "2026-08-15" }) },
      {
        name: "foreign author",
        readback: exactPull({ user: { login: "ratley", id: 1 } }),
      },
      {
        name: "mismatched",
        readback: exactPull({
          base: {
            ref: EXACT_INPUT.base.ref,
            sha: SHA,
            repo: { id: FABLE_REPO_ID, full_name: EXACT_INPUT.repo },
          },
        }),
      },
      { name: "ambiguous", readback: [exactPull(), exactPull()] },
    ];

    for (const scenario of scenarios) {
      const { dependencies, calls } = exactAdoptionBroker({ readbacks: [scenario.readback] });
      await expect(adoptExactPullRequest(EXACT_INPUT, dependencies)).rejects.toThrow(
        "exact_adoption_mismatch",
      );
      expect(
        calls.some((call) => call.method === "POST" || call.path.includes("/pulls?")),
        scenario.name,
      ).toBe(false);
    }
  });

  test("fails closed on repository identity, remote-head, or final-generation drift", async () => {
    const wrongRepository = exactAdoptionBroker({
      readbacks: [
        exactPull({
          head: {
            ref: EXACT_INPUT.head.ref,
            sha: EXACT_INPUT.head.sha,
            repo: { id: FABLE_REPO_ID + 1, full_name: EXACT_INPUT.repo },
          },
        }),
      ],
    });
    await expect(adoptExactPullRequest(EXACT_INPUT, wrongRepository.dependencies)).rejects.toThrow(
      "exact_adoption_mismatch",
    );

    const wrongRemoteHead = exactAdoptionBroker({
      remoteHead: {
        ref: `refs/heads/${EXACT_INPUT.head.ref}`,
        object: { type: "commit", sha: BASE_SHA },
      },
    });
    await expect(adoptExactPullRequest(EXACT_INPUT, wrongRemoteHead.dependencies)).rejects.toThrow(
      "remote_head_mismatch",
    );

    const finalGenerationDrift = exactAdoptionBroker({
      readbacks: [exactPull(), exactPull({ draft: false })],
    });
    await expect(
      adoptExactPullRequest(EXACT_INPUT, finalGenerationDrift.dependencies),
    ).rejects.toThrow("exact_adoption_mismatch");

    for (const { calls } of [wrongRepository, wrongRemoteHead, finalGenerationDrift]) {
      expect(calls.some((call) => call.method === "POST" || call.path.includes("/pulls?"))).toBe(
        false,
      );
    }
  });

  test("rejects non-Fable repositories before minting or requesting", async () => {
    const { dependencies, calls } = exactAdoptionBroker();
    let minted = false;
    dependencies.mintToken = async () => {
      minted = true;
      return TOKEN;
    };

    await expect(
      adoptExactPullRequest(
        { ...EXACT_INPUT, repo: DAEMON_REPO as ExactPullRequestAdoptionInput["repo"] },
        dependencies,
      ),
    ).rejects.toThrow("repo_not_fable");
    expect(minted).toBe(false);
    expect(calls).toHaveLength(0);
  });
});

function ownerMarker(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schemaVersion: "fable-pr-owner/v1",
    sequence: 2,
    writeNonce: "01900000-0000-7000-8000-000000000004",
    repository: "happycatlabs/fable",
    pullNumber: 42,
    taskId: TASK_ID,
    dispositionVersion: "fable-pr-disposition/v1",
    linearTicket: "FABLE-233",
    ownedHeadSha: SHA,
    baseRef: "master",
    baseSha: BASE_SHA,
    verification: {
      source: "originating_task",
      version: "fable-task-verification/v1",
      status: "passed",
      attestationId: ATTESTATION_ID,
      taskId: TASK_ID,
      linearTicket: "FABLE-233",
      pullNumber: 42,
      headSha: SHA,
      baseRef: "master",
      baseSha: BASE_SHA,
    },
    ...overrides,
  };
}

function ownerComment(
  marker: Record<string, unknown> = ownerMarker(),
  overrides: Record<string, unknown> = {},
) {
  return {
    databaseId: 101,
    body: `<!-- fable-pr-owner/v1\n${JSON.stringify(marker)}\n-->`,
    lastEditedAt: null,
    author: { databaseId: 266699010 },
    editor: null,
    userContentEdits: {
      nodes: [],
      pageInfo: { hasNextPage: false },
    },
    ...overrides,
  };
}

function readyBroker(
  options: {
    comments?: unknown[];
    pullReadbacks?: unknown[];
    viewer?: unknown;
  } = {},
) {
  const calls: Array<{
    token: string;
    method: string;
    path: string;
    variables?: Record<string, unknown>;
  }> = [];
  const readbacks = options.pullReadbacks ?? [pull(), pull(), pull(42, { draft: false })];
  let pullRead = 0;
  const dependencies: BrokerDependencies = {
    mintToken: async () => TOKEN,
    request: async (token, request) => {
      calls.push({
        token,
        method: request.method ?? "GET",
        path: request.path,
      });
      if (request.path.endsWith("/pulls/42")) {
        return readbacks[pullRead++] ?? readbacks.at(-1);
      }
      throw new Error("unexpected_test_request");
    },
    graphql: async (token, query, variables) => {
      if (query.includes("FablePrViewer")) {
        calls.push({ token, method: "GRAPHQL", path: "viewer", variables });
        return (
          options.viewer ?? {
            viewer: {
              login: "dancer-automation[bot]",
              databaseId: 266699010,
            },
          }
        );
      }
      if (query.includes("FablePrOwnerComments")) {
        calls.push({
          token,
          method: "GRAPHQL",
          path: "owner-comments",
          variables,
        });
        return {
          repository: {
            pullRequest: {
              comments: {
                nodes: options.comments ?? [ownerComment()],
                pageInfo: { hasNextPage: false, endCursor: null },
              },
            },
          },
        };
      }
      if (query.includes("FablePrMarkReady")) {
        calls.push({
          token,
          method: "GRAPHQL",
          path: "mark-ready",
          variables,
        });
        return { markPullRequestReadyForReview: { pullRequest: { id: "PR_kwDOExample" } } };
      }
      throw new Error("unexpected_test_graphql");
    },
  };
  return { dependencies, calls };
}

describe("markPullRequestReady", () => {
  test("marks the exact attested draft ready with Dancer", async () => {
    const { dependencies, calls } = readyBroker();
    const proof = await markPullRequestReady({ repo: INPUT.repo, number: 42 }, dependencies);

    expect(proof).toMatchObject({
      repo: INPUT.repo,
      number: 42,
      base: INPUT.base,
      baseSha: BASE_SHA,
      head: { ref: INPUT.head, sha: SHA },
      draft: false,
      readyTransitioned: true,
      owner: {
        taskId: TASK_ID,
        linearTicket: "FABLE-233",
        sequence: 2,
        attestationId: ATTESTATION_ID,
      },
    });
    expect(calls.find((call) => call.path === "mark-ready")?.variables).toEqual({
      pullRequestId: "PR_kwDOExample",
    });
    expect(JSON.stringify(proof)).not.toContain(TOKEN);
  });

  test("fails closed for missing, ambiguous, malformed, or untrusted owner comments", async () => {
    await expect(
      markPullRequestReady(
        { repo: INPUT.repo, number: 42 },
        readyBroker({ comments: [] }).dependencies,
      ),
    ).rejects.toThrow("owner_marker_missing");

    await expect(
      markPullRequestReady(
        { repo: INPUT.repo, number: 42 },
        readyBroker({ comments: [ownerComment(), ownerComment()] }).dependencies,
      ),
    ).rejects.toThrow("owner_marker_ambiguous");

    await expect(
      markPullRequestReady(
        { repo: INPUT.repo, number: 42 },
        readyBroker({
          comments: [ownerComment(ownerMarker(), { body: "<!-- fable-pr-owner/v1\n{}\n-->" })],
        }).dependencies,
      ),
    ).rejects.toThrow("owner_marker_not_ready");

    await expect(
      markPullRequestReady(
        { repo: INPUT.repo, number: 42 },
        readyBroker({
          comments: [
            ownerComment(ownerMarker(), {
              lastEditedAt: "2026-07-27T08:00:00Z",
              editor: { databaseId: 1 },
            }),
          ],
        }).dependencies,
      ),
    ).rejects.toThrow("owner_marker_untrusted");

    await expect(
      markPullRequestReady(
        { repo: INPUT.repo, number: 42 },
        readyBroker({
          comments: [
            ownerComment(ownerMarker(), {
              userContentEdits: {
                nodes: [],
                pageInfo: { hasNextPage: true },
              },
            }),
          ],
        }).dependencies,
      ),
    ).rejects.toThrow("owner_marker_untrusted");
  });

  test("rejects stale generation and failed attestation", async () => {
    await expect(
      markPullRequestReady(
        { repo: INPUT.repo, number: 42 },
        readyBroker({
          comments: [ownerComment(ownerMarker({ ownedHeadSha: BASE_SHA }))],
        }).dependencies,
      ),
    ).rejects.toThrow("owner_marker_not_ready");

    await expect(
      markPullRequestReady(
        { repo: INPUT.repo, number: 42 },
        readyBroker({
          comments: [
            ownerComment(
              ownerMarker({
                verification: {
                  ...(ownerMarker().verification as Record<string, unknown>),
                  status: "failed",
                },
              }),
            ),
          ],
        }).dependencies,
      ),
    ).rejects.toThrow("owner_marker_not_ready");
  });

  test("stops if the PR generation changes before or during the ready transition", async () => {
    const changedHead = pull(42, {
      head: {
        ref: INPUT.head,
        sha: BASE_SHA,
        repo: { full_name: INPUT.repo },
      },
    });
    const beforeMutation = readyBroker({
      pullReadbacks: [pull(), changedHead],
    });
    await expect(
      markPullRequestReady({ repo: INPUT.repo, number: 42 }, beforeMutation.dependencies),
    ).rejects.toThrow("pr_generation_changed");
    expect(beforeMutation.calls.some((call) => call.path === "mark-ready")).toBe(false);

    const afterMutation = readyBroker({
      pullReadbacks: [pull(), pull(), changedHead],
    });
    await expect(
      markPullRequestReady({ repo: INPUT.repo, number: 42 }, afterMutation.dependencies),
    ).rejects.toThrow("pr_generation_changed");
    expect(afterMutation.calls.some((call) => call.path === "mark-ready")).toBe(true);
  });

  test("validates the owner marker before returning an already-ready PR", async () => {
    const alreadyReady = pull(42, { draft: false });
    const { dependencies, calls } = readyBroker({
      pullReadbacks: [alreadyReady, alreadyReady],
    });
    const proof = await markPullRequestReady({ repo: INPUT.repo, number: 42 }, dependencies);

    expect(proof.draft).toBe(false);
    expect(proof.readyTransitioned).toBe(false);
    expect(calls.some((call) => call.path === "mark-ready")).toBe(false);
  });
});

describe("markDaemonPullRequestReady", () => {
  test("marks only the exact daemon head ready without Fable owner metadata", async () => {
    const { dependencies, calls } = readyBroker({
      comments: [],
      pullReadbacks: [daemonPull(), daemonPull(), daemonPull(42, { draft: false })],
    });
    const proof = await markDaemonPullRequestReady(
      { repo: DAEMON_REPO, number: 42, headSha: SHA },
      dependencies,
    );

    expect(proof).toMatchObject({
      repo: DAEMON_REPO,
      number: 42,
      head: { ref: DAEMON_HEAD, sha: SHA },
      draft: false,
      readyTransitioned: true,
      exactHeadVerified: true,
    });
    expect(calls.some((call) => call.path === "owner-comments")).toBe(false);
    expect(calls.some((call) => call.path === "mark-ready")).toBe(true);
  });

  test("rejects a stale daemon head before the ready mutation", async () => {
    const { dependencies, calls } = readyBroker({
      comments: [],
      pullReadbacks: [daemonPull()],
    });
    await expect(
      markDaemonPullRequestReady(
        { repo: DAEMON_REPO, number: 42, headSha: BASE_SHA },
        dependencies,
      ),
    ).rejects.toThrow("daemon_pr_generation_changed");
    expect(calls.some((call) => call.path === "mark-ready")).toBe(false);
  });
});

describe("applyLabels", () => {
  test("uses ambient gh only after a complete Dancer proof", async () => {
    const proof = (await createOrAdoptPullRequest(
      INPUT,
      broker().dependencies,
    )) as PullRequestProof;
    const calls: Array<{ args: string[]; stdin?: string }> = [];

    await applyLabels(proof, ["Client Release"], {
      gh: async (args, stdin) => {
        calls.push({ args, stdin });
        if (args.includes("graphql")) {
          return JSON.stringify({ data: { viewer: { login: "ratley" } } });
        }
        return "{}";
      },
    });

    expect(calls).toHaveLength(2);
    expect(calls[1]?.args).toEqual([
      "api",
      "--method",
      "POST",
      "/repos/happycatlabs/fable/issues/42/labels",
      "--input",
      "-",
    ]);
    expect(calls[1]?.stdin).toBe(JSON.stringify({ labels: ["Client Release"] }));
    expect(JSON.stringify(calls)).not.toContain(TOKEN);
  });

  test("does not invoke gh for an invalid proof", async () => {
    let invoked = false;
    await expect(
      applyLabels(
        {
          ...pull(),
          repo: "happycatlabs/fable",
          url: "https://github.com/happycatlabs/fable/pull/42",
          author: { login: "ratley", actorId: 1 },
          base: "master",
          baseSha: BASE_SHA,
          head: { ref: INPUT.head, sha: SHA },
          draft: true,
          adopted: false,
        } as unknown as PullRequestProof,
        ["Client Release"],
        {
          gh: async () => {
            invoked = true;
            return "";
          },
        },
      ),
    ).rejects.toThrow("dancer_proof_invalid");
    expect(invoked).toBe(false);
  });

  test("refuses a bot ambient gh identity before applying labels", async () => {
    const proof = await createOrAdoptPullRequest(INPUT, broker().dependencies);
    let labelMutationAttempted = false;

    await expect(
      applyLabels(proof, ["Client Release"], {
        gh: async (args) => {
          if (args.includes("graphql")) {
            return JSON.stringify({
              data: { viewer: { login: "dancer-automation[bot]" } },
            });
          }
          labelMutationAttempted = true;
          return "{}";
        },
      }),
    ).rejects.toThrow("ambient_gh_not_human");
    expect(labelMutationAttempted).toBe(false);
  });
});

describe("Fable PR CLI", () => {
  test("routes laptop calls through the Eve broker and reads back its proof", async () => {
    const fakeBin = mkdtempSync(join(tmpdir(), "fable-pr-test-"));
    const fakeSsh = join(fakeBin, "ssh");
    writeFileSync(
      fakeSsh,
      `#!/bin/sh
cat >/dev/null
printf '%s\\n' '${JSON.stringify({
        repo: INPUT.repo,
        number: 42,
        url: "https://github.com/happycatlabs/fable/pull/42",
        author: { login: "dancer-automation[bot]", actorId: 266699010 },
        base: INPUT.base,
        baseSha: BASE_SHA,
        head: { ref: INPUT.head, sha: SHA },
        draft: true,
        adopted: false,
      })}'
`,
    );
    chmodSync(fakeSsh, 0o755);

    try {
      const child = Bun.spawn(
        [
          process.execPath,
          "scripts/fable-pr.ts",
          "--repo",
          INPUT.repo,
          "--base",
          INPUT.base,
          "--head",
          INPUT.head,
          "--title",
          INPUT.title,
          "--body",
          INPUT.body,
        ],
        {
          cwd: process.cwd(),
          env: {
            ...process.env,
            FABLE_PR_TOKEN_MODE: "eve",
            PATH: `${fakeBin}:${process.env.PATH ?? ""}`,
          },
          stdout: "pipe",
          stderr: "pipe",
        },
      );
      const [exitCode, stdout, stderr] = await Promise.all([
        child.exited,
        new Response(child.stdout).text(),
        new Response(child.stderr).text(),
      ]);

      expect(exitCode).toBe(0);
      expect(stderr).toBe("");
      expect(JSON.parse(stdout)).toMatchObject({
        number: 42,
        author: { login: "dancer-automation[bot]", actorId: 266699010 },
        head: { ref: INPUT.head, sha: SHA },
      });
    } finally {
      rmSync(fakeBin, { recursive: true, force: true });
    }
  });

  test("routes the ready transition through Eve with a bounded broker request", async () => {
    const fakeBin = mkdtempSync(join(tmpdir(), "fable-pr-ready-test-"));
    const fakeSsh = join(fakeBin, "ssh");
    const capture = join(fakeBin, "broker-input.json");
    writeFileSync(
      fakeSsh,
      `#!/bin/sh
cat >"$FABLE_PR_CAPTURE"
printf '%s\\n' '${JSON.stringify({
        repo: INPUT.repo,
        number: 42,
        url: "https://github.com/happycatlabs/fable/pull/42",
        author: { login: "dancer-automation[bot]", actorId: 266699010 },
        base: INPUT.base,
        baseSha: BASE_SHA,
        head: { ref: INPUT.head, sha: SHA },
        draft: false,
        owner: {
          taskId: TASK_ID,
          linearTicket: "FABLE-233",
          sequence: 2,
          attestationId: ATTESTATION_ID,
        },
        readyTransitioned: true,
      })}'
`,
    );
    chmodSync(fakeSsh, 0o755);

    try {
      const child = Bun.spawn(
        [process.execPath, "scripts/fable-pr.ts", "ready", "--repo", INPUT.repo, "--pr", "42"],
        {
          cwd: process.cwd(),
          env: {
            ...process.env,
            FABLE_PR_CAPTURE: capture,
            FABLE_PR_TOKEN_MODE: "eve",
            PATH: `${fakeBin}:${process.env.PATH ?? ""}`,
          },
          stdout: "pipe",
          stderr: "pipe",
        },
      );
      const [exitCode, stdout, stderr] = await Promise.all([
        child.exited,
        new Response(child.stdout).text(),
        new Response(child.stderr).text(),
      ]);

      expect(exitCode).toBe(0);
      expect(stderr).toBe("");
      expect(JSON.parse(readFileSync(capture, "utf8"))).toEqual({
        action: "ready",
        input: { repo: INPUT.repo, number: 42 },
      });
      expect(JSON.parse(stdout)).toMatchObject({
        number: 42,
        draft: false,
        owner: { linearTicket: "FABLE-233" },
      });
    } finally {
      rmSync(fakeBin, { recursive: true, force: true });
    }
  });

  test("routes an exact daemon ready transition through Eve", async () => {
    const fakeBin = mkdtempSync(join(tmpdir(), "fable-pr-daemon-ready-test-"));
    const fakeSsh = join(fakeBin, "ssh");
    const capture = join(fakeBin, "broker-input.json");
    writeFileSync(
      fakeSsh,
      `#!/bin/sh
cat >"$FABLE_PR_CAPTURE"
printf '%s\\n' '${JSON.stringify({
        repo: DAEMON_REPO,
        number: 42,
        url: `https://github.com/${DAEMON_REPO}/pull/42`,
        author: { login: "dancer-automation[bot]", actorId: 266699010 },
        base: "master",
        baseSha: BASE_SHA,
        head: { ref: DAEMON_HEAD, sha: SHA },
        draft: false,
        readyTransitioned: true,
        exactHeadVerified: true,
      })}'
`,
    );
    chmodSync(fakeSsh, 0o755);

    try {
      const child = Bun.spawn(
        [
          process.execPath,
          "scripts/fable-pr.ts",
          "ready-daemon",
          "--repo",
          DAEMON_REPO,
          "--pr",
          "42",
          "--head",
          SHA,
        ],
        {
          cwd: process.cwd(),
          env: {
            ...process.env,
            FABLE_PR_CAPTURE: capture,
            FABLE_PR_TOKEN_MODE: "eve",
            PATH: `${fakeBin}:${process.env.PATH ?? ""}`,
          },
          stdout: "pipe",
          stderr: "pipe",
        },
      );
      const [exitCode, stdout, stderr] = await Promise.all([
        child.exited,
        new Response(child.stdout).text(),
        new Response(child.stderr).text(),
      ]);

      expect(exitCode).toBe(0);
      expect(stderr).toBe("");
      expect(JSON.parse(readFileSync(capture, "utf8"))).toEqual({
        action: "ready-daemon",
        input: { repo: DAEMON_REPO, number: 42, headSha: SHA },
      });
      expect(JSON.parse(stdout)).toMatchObject({
        repo: DAEMON_REPO,
        number: 42,
        draft: false,
        exactHeadVerified: true,
      });
    } finally {
      rmSync(fakeBin, { recursive: true, force: true });
    }
  });
});
