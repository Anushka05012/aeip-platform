"use client";


import { useEffect, useState } from "react";
import { getOverview } from "@/lib/intelligenceApi";
import { addRepository, listRepositories } from "@/lib/ingestionApi";
import { Repository } from "@/types";



export default function RepositoriesPage() {
  const [repository, setRepository] = useState("");
  const [indexedDocuments, setIndexedDocuments] = useState<number | null>(null);
  const [error, setError] = useState("");

  const [repos, setRepos] = useState<Repository[]>([]);
  const [reposError, setReposError] = useState("");

  const [input, setInput] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");
  const [addSuccess, setAddSuccess] = useState("");

  function refreshRepositories() {
    listRepositories()
      .then(setRepos)
      .catch((reason: Error) => setReposError(reason.message));
  }

  useEffect(() => {
    getOverview()
      .then((data) => {
        setRepository(data.repository);
        setIndexedDocuments(data.indexedDocuments);
      })
      .catch((reason: Error) => setError(reason.message));

    refreshRepositories();
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAddError("");
    setAddSuccess("");

    const parts = input.trim().split("/");
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
      setAddError("Enter a repo as owner/repo, e.g. facebook/react");
      return;
    }
    const [owner, repo] = parts;

    setAdding(true);
    try {
      const result = await addRepository(owner, repo);
      setAddSuccess(
        `Added ${result.repository} — ${result.commitsIngested} commits, ${result.pullRequestsIngested} PRs ingested.`
      );
      setInput("");
      refreshRepositories();
    } catch (err) {
      setAddError((err as Error).message ?? "Something went wrong");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div>
      <h1 className="text-[19px] text-[#E7E9EC] mb-4">Repositories</h1>

      <form onSubmit={handleAdd} className="flex gap-2 mb-4 max-w-md">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="owner/repo (e.g. facebook/react)"
          disabled={adding}
          className="flex-1 bg-[#12151C] border border-[#232833] rounded-md px-3 py-2 text-[13px] text-[#E7E9EC] placeholder:text-[#565D6B] focus:outline-none focus:border-[#3A4150]"
        />
        <button
          type="submit"
          disabled={adding}
          className="bg-[#1B2030] border border-[#2A3040] rounded-md px-4 py-2 text-[13px] text-[#E7E9EC] disabled:opacity-50 hover:border-[#3A4150]"
        >
          {adding ? "Adding..." : "Add Repository"}
        </button>
      </form>
      {addError && <p className="text-[12px] text-[#E5484D] mb-4">{addError}</p>}
      {addSuccess && <p className="text-[12px] text-[#4CAF6D] mb-4">{addSuccess}</p>}

      <div className="bg-[#12151C] border border-[#232833] rounded-md p-5 text-[13px] text-[#8B93A1] mb-4">
        {error ? (
          error
        ) : repository ? (
          <>
            <span className="text-[#E7E9EC]">{repository}</span>
            <br />
            {indexedDocuments} documents indexed for repository-aware retrieval.
          </>
        ) : (
          "Loading repository intelligence..."
        )}
      </div>

      <div className="bg-[#12151C] border border-[#232833] rounded-md p-5 text-[13px] text-[#8B93A1]">
        <div className="text-[#E7E9EC] mb-3">Tracked Repositories</div>
        {reposError ? (
          <p className="text-[#E5484D]">{reposError}</p>
        ) : repos.length === 0 ? (
          <p>No repositories added yet.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {repos.map((r) => (
              <li key={r.id} className="flex justify-between border-b border-[#232833] pb-2 last:border-none">
                <span className="text-[#E7E9EC]">{r.fullName}</span>
                <span>
                  {r._count.commits} commits · {r._count.pullRequests} PRs
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}