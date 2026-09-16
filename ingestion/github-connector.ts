import { Octokit } from "octokit";
import { PrismaClient } from "@prisma/client";
import "dotenv/config";

const prisma = new PrismaClient();
const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });

const OWNER = "SnehalBawanthade"; // <-- replace with your actual GitHub username
const REPO = "aeip-platform";

async function upsertRepository() {
  const { data } = await octokit.rest.repos.get({ owner: OWNER, repo: REPO });

  const repository = await prisma.repository.upsert({
    where: { fullName: data.full_name },
    update: {},
    create: {
      name: data.name,
      owner: data.owner.login,
      fullName: data.full_name,
      url: data.html_url,
    },
  });

  return repository;
}

async function ingestCommits(repositoryId: string) {
  const { data: commits } = await octokit.rest.repos.listCommits({
    owner: OWNER,
    repo: REPO,
    per_page: 50,
  });

  for (const c of commits) {
    if (!c.commit.author?.date) continue;

    await prisma.commit.upsert({
      where: { sha: c.sha },
      update: {},
      create: {
        repositoryId,
        sha: c.sha,
        authorName: c.commit.author.name ?? "unknown",
        authorEmail: c.commit.author.email ?? "unknown",
        message: c.commit.message,
        committedAt: new Date(c.commit.author.date),
      },
    });
  }

  console.log(`Ingested ${commits.length} commits.`);
}

async function ingestPullRequests(repositoryId: string) {
  const { data: prs } = await octokit.rest.pulls.list({
    owner: OWNER,
    repo: REPO,
    state: "all",
    per_page: 50,
  });

  for (const pr of prs) {
    await prisma.pullRequest.upsert({
      where: { repositoryId_number: { repositoryId, number: pr.number } },
      update: {
        state: pr.merged_at ? "merged" : pr.state,
        mergedAt: pr.merged_at ? new Date(pr.merged_at) : null,
        closedAt: pr.closed_at ? new Date(pr.closed_at) : null,
      },
      create: {
        repositoryId,
        number: pr.number,
        title: pr.title,
        authorName: pr.user?.login ?? "unknown",
        state: pr.merged_at ? "merged" : pr.state,
        baseBranch: pr.base.ref,
        headBranch: pr.head.ref,
        createdAt: new Date(pr.created_at),
        mergedAt: pr.merged_at ? new Date(pr.merged_at) : null,
        closedAt: pr.closed_at ? new Date(pr.closed_at) : null,
      },
    });
  }

  console.log(`Ingested ${prs.length} pull requests.`);
}

async function main() {
  console.log("Starting GitHub ingestion...");
  const repository = await upsertRepository();
  console.log(`Repository upserted: ${repository.fullName}`);

  await ingestCommits(repository.id);
  await ingestPullRequests(repository.id);

  console.log("Ingestion complete.");
}

main()
  .catch((e) => {
    console.error("Ingestion failed:", e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });