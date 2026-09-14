import RiskList from "@/components/dashboard/RiskList";
import { riskItems } from "@/lib/mockData";

export default function RiskPage() {
    return (
        <div>
            <h1 className="text-[19px] text-[#E7E9EC] mb-4">Risk Intelligence</h1>
            <div className="max-w-md">
                <RiskList items={riskItems} />
            </div>
        </div>
    );
}