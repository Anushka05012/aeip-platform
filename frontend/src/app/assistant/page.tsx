import ChatPanel from "@/components/assistant/ChatPanel";
import { PageHeader } from "@/components/ui";

export default function AssistantPage() {
    return (
        <div className="max-w-205 flex flex-col gap-6">
            <PageHeader title="Ask the codebase" meta="Retrieval over the indexed repository, with the sources shown for every answer." />
            <ChatPanel initial={[]} />
        </div>
    );
}
