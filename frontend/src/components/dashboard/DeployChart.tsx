"use client";

import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { DeployPoint } from "@/types";

export default function DeployChart({ data }: { data: DeployPoint[] }) {
    return (
        <div className="bg-[#12151C] border border-[#232833] rounded-md p-5">
            <div className="flex items-center justify-between mb-4">
                <span className="text-[13px] text-[#B4B9C2]">Deployment activity, last 8 days</span>
                <span className="font-mono text-[11px] text-[#5B6270]">DAILY DEPLOYS</span>
            </div>
            <ResponsiveContainer width="100%" height={180}>
                <LineChart data={data}>
                    <XAxis dataKey="d" tick={{ fill: "#5B6270", fontSize: 11 }} axisLine={{ stroke: "#232833" }} tickLine={false} />
                    <YAxis hide />
                    <Tooltip
                        contentStyle={{ background: "#171A21", border: "1px solid #232833", borderRadius: 6, fontSize: 12 }}
                        labelStyle={{ color: "#8B93A1" }}
                    />
                    <Line type="monotone" dataKey="v" stroke="#3FD6B0" strokeWidth={2} dot={{ r: 3, fill: "#3FD6B0" }} />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}