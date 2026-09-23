import type { Metadata } from "next";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { PageShell } from "@/components/layout/PageShell";

export const metadata: Metadata = {
  title: "짠이와 대화",
  description: "“성수에서 3만원으로 혼밥하고 전시 볼래” 말로 하면 짠이가 예산 코스를 짜 드려요.",
};

export default function ChatPage() {
  return (
    <PageShell footer={false} tabBar={false} className="bg-soft">
      <ChatWindow />
    </PageShell>
  );
}
