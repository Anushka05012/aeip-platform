"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DeployPoint } from "@/types";

export default function DeployChart({ data }: { data: DeployPoint[] }) {
    if (!data.length) {
        return <p className="text-[13px] text-muted py-16 text-center">No default-branch CI runs in this window.</p>;
    }
    return (
        <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -24 }} barCategoryGap="28%">
                <CartesianGrid vertical={false} stroke="#ece9e2" />
                <XAxis dataKey="d" tick={{ fill: "#7a776f", fontSize: 11.5 }} axisLine={{ stroke: "#cdc9bf" }} tickLine={false} interval="preserveStartEnd" />
                <YAxis allowDecimals={false} tick={{ fill: "#7a776f", fontSize: 11.5 }} axisLine={false} tickLine={false} />
                <Tooltip
                    cursor={{ fill: "#f1efe9" }}
                    formatter={(value) => [`${value} run${value === 1 ? "" : "s"}`, "CI runs"]}
                    contentStyle={{ background: "#fff", border: "1px solid #cdc9bf", borderRadius: 5, fontSize: 12.5, boxShadow: "0 2px 8px rgba(0,0,0,0.06)" }}
                    labelStyle={{ color: "#1d1c1a", fontWeight: 500 }}
                    itemStyle={{ color: "#4a4843" }}
                />
                <Bar dataKey="v" fill="#2350c8" radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
            </BarChart>
        </ResponsiveContainer>
    );
}
