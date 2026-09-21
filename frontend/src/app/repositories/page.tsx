"use client";

import { useEffect, useState } from "react";
import { getOverview } from "@/lib/intelligenceApi";

export default function RepositoriesPage() {
  const [repository, setRepository] = useState("");
  const [indexedDocuments, setIndexedDocuments] = useState<number | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getOverview().then((data) => { setRepository(data.repository); setIndexedDocuments(data.indexedDocuments); }).catch((reason: Error) => setError(reason.message));
  }, []);
  return <div>
    <h1 className="text-[19px] text-[#E7E9EC] mb-4">Repositories</h1>
    <div className="bg-[#12151C] border border-[#232833] rounded-md p-5 text-[13px] text-[#8B93A1]">
      {error ? error : repository ? <><span className="text-[#E7E9EC]">{repository}</span><br />{indexedDocuments} documents indexed for repository-aware retrieval.</> : "Loading repository intelligence..."}
    </div>
  </div>;
}
