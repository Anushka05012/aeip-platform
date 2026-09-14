import MetricCard from "@/components/dashboard/MetricCard";
import DeployChart from "@/components/dashboard/DeployChart";
import RiskList from "@/components/dashboard/RiskList";
import FailuresFeed from "@/components/dashboard/FailuresFeed";
import { metrics, deployTrend, riskItems, failures } from "@/lib/mockData";

export default function OverviewPage() {
  return (
    <div className="flex flex-col gap-7">
      <div>
        <h1 className="text-[19px] text-[#E7E9EC] mb-4">Engineering overview</h1>
        <div className="grid grid-cols-4 gap-4">
          {metrics.map((m) => (
            <MetricCard key={m.label} m={m} />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-5">
        <div className="col-span-2">
          <DeployChart data={deployTrend} />
        </div>
        <RiskList items={riskItems} />
      </div>

      <div className="grid grid-cols-3 gap-5">
        <div className="col-span-2">
          <FailuresFeed items={failures} />
        </div>
        <div className="h-[280px]">
          {/* Small assistant preview on overview — full chat lives on /assistant */}
        </div>
      </div>
    </div>
  );
}