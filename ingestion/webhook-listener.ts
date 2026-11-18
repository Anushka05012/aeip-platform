import express from "express";
import "dotenv/config";
import { ingestRepository, listRepositories } from "./github-service";
import cors from "cors";
import prisma from "./prisma-client";
import { verifySignature } from "./signature";

const app = express();

// The dashboard's origin(s); add deployed URLs with AEIP_ALLOWED_ORIGINS (comma-separated).
const allowedOrigins = ["http://localhost:3000", "http://127.0.0.1:3000",
  ...(process.env.AEIP_ALLOWED_ORIGINS ?? "").split(",").map((origin) => origin.trim()).filter(Boolean)];
app.use(cors({ origin: allowedOrigins }));

app.use(
  express.json({
    verify: (req: any, _res, buf) => {
      req.rawBody = buf;
    },
  })
);

const REPO_PART = /^[A-Za-z0-9._-]{1,100}$/;

async function getOrCreateRepository(repoPayload: any) {
  return prisma.repository.upsert({
    where: { fullName: repoPayload.full_name },
    update: {},
    create: {
      name: repoPayload.name,
      owner: repoPayload.owner.login ?? repoPayload.owner.name,
      fullName: repoPayload.full_name,
      url: repoPayload.html_url,
    },
  });
}

async function handlePushEvent(body: any) {
  const repository = await getOrCreateRepository(body.repository);

  for (const c of body.commits ?? []) {
    await prisma.commit.upsert({
      where: { sha: c.id },
      update: {},
      create: {
        repositoryId: repository.id,
        sha: c.id,
        authorName: c.author.name,
        authorEmail: c.author.email,
        message: c.message,
        committedAt: new Date(c.timestamp),
      },
    });
  }

  console.log(`Normalized ${body.commits?.length ?? 0} commits from push event.`);
}

async function handlePullRequestEvent(body: any) {
  const repository = await getOrCreateRepository(body.repository);
  const pr = body.pull_request;

  await prisma.pullRequest.upsert({
    where: { repositoryId_number: { repositoryId: repository.id, number: pr.number } },
    update: {
      state: pr.merged_at ? "merged" : pr.state,
      mergedAt: pr.merged_at ? new Date(pr.merged_at) : null,
      closedAt: pr.closed_at ? new Date(pr.closed_at) : null,
    },
    create: {
      repositoryId: repository.id,
      number: pr.number,
      title: pr.title,
      authorName: pr.user.login,
      state: pr.merged_at ? "merged" : pr.state,
      baseBranch: pr.base.ref,
      headBranch: pr.head.ref,
      createdAt: new Date(pr.created_at),
      mergedAt: pr.merged_at ? new Date(pr.merged_at) : null,
      closedAt: pr.closed_at ? new Date(pr.closed_at) : null,
    },
  });

  console.log(`Normalized PR #${pr.number} (${body.action})`);
}

app.post("/api/repositories", async (req, res) => {
  const { owner, repo } = req.body ?? {};

  if (typeof owner !== "string" || typeof repo !== "string" || !REPO_PART.test(owner) || !REPO_PART.test(repo)) {
    return res.status(400).json({ error: "owner and repo are required, e.g. { owner: 'facebook', repo: 'react' }" });
  }

  try {
    const result = await ingestRepository(owner, repo);
    res.status(200).json(result);
  } catch (err: any) {
    console.error("Failed to ingest repository:", err.message);
    // Octokit errors carry the GitHub HTTP status; surface the useful ones instead of a blanket 500.
    if (err.status === 404) return res.status(404).json({ error: "Repository not found or not accessible with GITHUB_TOKEN" });
    if (err.status === 403 || err.status === 429) return res.status(429).json({ error: "GitHub rate limit reached; set GITHUB_TOKEN" });
    res.status(500).json({ error: "Failed to ingest repository", details: err.message });
  }
});

app.get("/api/repositories", async (_req, res) => {
  try {
    const repos = await listRepositories();
    res.status(200).json(repos);
  } catch (err: any) {
    res.status(500).json({ error: "Failed to fetch repositories" });
  }
});

app.post("/webhooks/github", async (req: any, res) => {
  if (!verifySignature(req.rawBody, req.headers["x-hub-signature-256"], process.env.GITHUB_WEBHOOK_SECRET)) {
    console.warn("Rejected webhook: invalid signature");
    return res.status(401).send("Invalid signature");
  }

  const event = req.headers["x-github-event"];
  console.log(`Received verified GitHub event: ${event}`);

  try {
    switch (event) {
      case "push":
        await handlePushEvent(req.body);
        break;
      case "pull_request":
        await handlePullRequestEvent(req.body);
        break;
      case "ping":
        console.log("Ping received — webhook connected successfully.");
        break;
      default:
        console.log(`Unhandled event type: ${event}`);
    }
    res.status(200).send("OK");
  } catch (err) {
    console.error("Error processing webhook:", err);
    res.status(500).send("Internal error");
  }
});

const PORT = Number(process.env.PORT ?? 4000);
app.listen(PORT, () => {
  console.log(`Webhook listener running on http://localhost:${PORT}`);
});