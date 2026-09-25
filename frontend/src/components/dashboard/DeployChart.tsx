"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DeployPoint } from "@/types";
import { useTheme } from "@/lib/theme";

// SVG presentation attributes can't read CSS variables, so the chart takes explicit values per theme.
// Bar colours pass the dataviz palette checks against each theme's panel surface.
const palettes = {
    light: { bar: "#2350c8", grid: "#ece9e2", axis: "#cdc9bf", tick: "#7a776f", cursor: "#f1efe9", surface: "#ffffff", ink: "#1d1c1a", ink2: "#4a4843" },
    dark: { bar: "#6b8ff0", grid: "#2c2b27", axis: "#4a4740", tick: "#8d8a82", cursor: "#262521", surface: "#1e1d1a", ink: "#ecebe6", ink2: "#bdbab2" },
};

export default function DeployChart({ data }: { data: DeployPoint[] }) {
    const c = palettes[useTheme()];
    if (!data.length) {
        return <p className="text-[13px] text-muted py-16 text-center">No default-branch CI runs in this window.</p>;
    }
    return (
        <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -24 }} barCategoryGap="28%">
                <CartesianGrid vertical={false} stroke={c.grid} />
                <XAxis dataKey="d" tick={{ fill: c.tick, fontSize: 11.5 }} axisLine={{ stroke: c.axis }} tickLine={false} interval="preserveStartEnd" />
                <YAxis allowDecimals={false} tick={{ fill: c.tick, fontSize: 11.5 }} axisLine={false} tickLine={false} />
                <Tooltip
                    cursor={{ fill: c.cursor }}
                    formatter={(value) => [`${value} run${value === 1 ? "" : "s"}`, "CI runs"]}
                    contentStyle={{ background: c.surface, border: `1px solid ${c.axis}`, borderRadius: 5, fontSize: 12.5, boxShadow: "0 2px 8px rgba(0,0,0,0.12)" }}
                    labelStyle={{ color: c.ink, fontWeight: 500 }}
                    itemStyle={{ color: c.ink2 }}
                />
                <Bar dataKey="v" fill={c.bar} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
            </BarChart>
        </ResponsiveContainer>
    );
}
