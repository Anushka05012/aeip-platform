import ChatPanel from "@/components/assistant/ChatPanel";

export default function AssistantPage() {
    return (
        <div className="h-[600px]">
            <h1 className="text-[19px] text-[#E7E9EC] mb-4">AI Engineering Assistant</h1>
            <div className="h-[500px]">
                <ChatPanel initial={[]} />
            </div>
        </div>
    );
}
