import { Octokit } from "octokit";
import prisma from "./prisma-client";

export async function ingestRepository(owner: string, repo: string) {
  const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });

  // 1. Get repo metadata, create/find it in DB
  const { data: repoData } = await octokit.rest.repos.get({ owner, repo });

  const repository = await prisma.repository.upsert({
    where: { fullName: repoData.full_name },
    update: {},
    create: {
      name: repoData.name,
      owner: repoData.owner.login,
      fullName: repoData.full_name,
      url: repoData.html_url,
    },
  });

  // 2. Ingest commits
  const { data: commits } = await octokit.rest.repos.listCommits({
    owner,
    repo,
    per_page: 50,
  });

  let commitCount = 0;
  for (const c of commits) {
    if (!c.commit.author?.date) continue;
    await prisma.commit.upsert({
      where: { sha: c.sha },
      update: {},
      create: {
        repositoryId: repository.id,
        sha: c.sha,
        authorName: c.commit.author.name ?? "unknown",
        authorEmail: c.commit.author.email ?? "unknown",
        message: c.commit.message,
        committedAt: new Date(c.commit.author.date),
      },
    });
    commitCount++;
  }

  // 3. Ingest pull requests
  const { data: prs } = await octokit.rest.pulls.list({
    owner,
    repo,
    state: "all",
    per_page: 50,
  });

  let prCount = 0;
  for (const pr of prs) {
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
        authorName: pr.user?.login ?? "unknown",
        state: pr.merged_at ? "merged" : pr.state,
        baseBranch: pr.base.ref,
        headBranch: pr.head.ref,
        createdAt: new Date(pr.created_at),
        mergedAt: pr.merged_at ? new Date(pr.merged_at) : null,
        closedAt: pr.closed_at ? new Date(pr.closed_at) : null,
      },
    });
    prCount++;
  }

  return {
    repository: repository.fullName,
    repositoryId: repository.id,
    commitsIngested: commitCount,
    pullRequestsIngested: prCount,
  };
}

export async function listRepositories() {
  return prisma.repository.findMany({
    include: {
      _count: { select: { commits: true, pullRequests: true } },
    },
  });
}