import { MessageCircleQuestion } from "lucide-react";

export function QuestionCard({ question, index }: { question: string; index: number }): React.JSX.Element {
  return (
    <li className="flex items-start gap-3 rounded-xl bg-surface-container-lowest p-4 shadow-card border border-outline-variant/40">
      <MessageCircleQuestion size={18} className="text-primary shrink-0 mt-0.5" aria-hidden />
      <div>
        <p className="lexi-code">Question {index + 1}</p>
        <p className="font-body-md text-body-md text-on-surface">{question}</p>
      </div>
    </li>
  );
}
