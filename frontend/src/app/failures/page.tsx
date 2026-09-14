import FailuresFeed from "@/components/dashboard/FailuresFeed";
import { failures } from "@/lib/mockData";

export default function FailuresPage() {
    return (
        <div>
            <h1 className="text-[19px] text-[#E7E9EC] mb-4">CI/CD Failures</h1>
            <FailuresFeed items={failures} />
        </div>
    );
}