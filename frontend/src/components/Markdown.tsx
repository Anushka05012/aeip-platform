import type { ReactNode } from "react";

/**
 * Minimal markdown for LLM answers: paragraphs, headings, lists, fenced code, pipe tables,
 * `inline code` and **bold**. Builds React elements (never raw HTML), so model output can't inject markup.
 */

function inline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    nodes.push(token.startsWith("`")
      ? <code key={`${keyBase}-${index++}`} className="font-mono text-[12.5px] bg-sunken border border-line rounded-[3px] px-1 py-px">{token.slice(1, -1)}</code>
      : <strong key={`${keyBase}-${index++}`} className="font-semibold text-ink">{token.slice(2, -2)}</strong>);
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

const isTableRow = (line: string) => /^\s*\|.*\|\s*$/.test(line);
const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());

export default function Markdown({ text }: { text: string }) {
  // Some models add 【source】 citation markers; sources are listed separately.
  const lines = text.replace(/【[^】]*】/g, "").replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    if (line.trim().startsWith("```")) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) body.push(lines[i++]);
      i++;
      blocks.push(<pre key={key++} className="font-mono text-[12px] leading-5 bg-sunken border border-line rounded-[5px] p-3 overflow-x-auto">{body.join("\n")}</pre>);
      continue;
    }

    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push(<p key={key++} className="font-semibold text-ink mt-1">{inline(heading[2], `h${key}`)}</p>);
      i++;
      continue;
    }

    if (isTableRow(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const header = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isTableRow(lines[i])) rows.push(cells(lines[i++]));
      blocks.push(<div key={key++} className="overflow-x-auto">
        <table className="border-collapse text-[12.5px]">
          <thead><tr>{header.map((cell, c) => <th key={c} className="text-left font-medium text-muted border-b border-line px-2 py-1">{inline(cell, `th${key}${c}`)}</th>)}</tr></thead>
          <tbody>{rows.map((row, r) => <tr key={r}>{row.map((cell, c) => <td key={c} className="border-b border-line px-2 py-1 align-top">{inline(cell, `td${key}${r}${c}`)}</td>)}</tr>)}</tbody>
        </table>
      </div>);
      continue;
    }

    if (/^\s*>/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push(<blockquote key={key++} className="border-l-2 border-line-strong pl-3 text-ink-2 italic">
        {inline(quote.join(" "), `q${key}`)}
      </blockquote>);
      continue;
    }

    const bullet = /^\s*([-*•]|\d+[.)])\s+/;
    if (bullet.test(line)) {
      const ordered = /^\s*\d/.test(line);
      const items: string[] = [];
      while (i < lines.length && bullet.test(lines[i])) {
        let item = lines[i++].replace(bullet, "");
        // continuation lines indented under the bullet
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !bullet.test(lines[i])) item += " " + lines[i++].trim();
        items.push(item);
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(<List key={key++} className={`${ordered ? "list-decimal" : "list-disc"} pl-5 flex flex-col gap-1 marker:text-muted`}>
        {items.map((item, n) => <li key={n}>{inline(item, `li${key}${n}`)}</li>)}
      </List>);
      continue;
    }

    const paragraph: string[] = [lines[i++].trim()]; // always consume one line so the loop advances
    while (i < lines.length && lines[i].trim() && !lines[i].trim().startsWith("```") && !bullet.test(lines[i]) && !/^#{1,4}\s/.test(lines[i]) && !isTableRow(lines[i]) && !/^\s*>/.test(lines[i])) {
      paragraph.push(lines[i++].trim());
    }
    blocks.push(<p key={key++}>{inline(paragraph.join(" "), `p${key}`)}</p>);
  }

  return <div className="flex flex-col gap-3 text-[14px] leading-[1.65] text-ink-2">{blocks}</div>;
}
