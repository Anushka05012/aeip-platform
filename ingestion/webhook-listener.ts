import express from "express";
import crypto from "crypto";
import { PrismaClient } from "@prisma/client";
import "dotenv/config";
import { ingestRepository, listRepositories } from "./github-service";

const app = express();
const prisma = new PrismaClient();

app.use(
  express.json({
    verify: (req: any, _res, buf) => {
      req.rawBody = buf;
    },
  })
);

function verifySignature(req: any): boolean {
  const signature = req.headers["x-hub-signature-256"] as string | undefined;
  if (!signature) return false;

  const secret = process.env.GITHUB_WEBHOOK_SECRET!;
  const hmac = crypto.createHmac("sha256", secret);
  const digest = "sha256=" + hmac.update(req.rawBody).digest("hex");

  return crypto.timingSafeEqual(Buffer.from(digest), Buffer.from(signature));
}

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

app.post("/api/repositories", express.json(), async (req, res) => {
  const { owner, repo } = req.body;

  if (!owner || !repo) {
    return res.status(400).json({ error: "owner and repo are required" });
  }

  try {
    const result = await ingestRepository(owner, repo);
    res.status(200).json(result);
  } catch (err: any) {
    console.error("Failed to ingest repository:", err.message);
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
  if (!verifySignature(req)) {
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

const PORT = 4000;
app.listen(PORT, () => {
  console.log(`Webhook listener running on http://localhost:${PORT}`);
});