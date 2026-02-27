"use client";

import { useRef, useState, useCallback, useEffect, type KeyboardEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Shuffle } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { SAMPLE_QUESTIONS } from "@/lib/sample-questions";
import { InputToolbar } from "./input-toolbar";
import { useChatStore } from "@/stores/chat-store";

const ALL_QUESTIONS = SAMPLE_QUESTIONS.flatMap((cat) => cat.questions);

function pickRandom(count: number, exclude?: string[]): string[] {
  const pool = exclude
    ? ALL_QUESTIONS.filter((q) => !exclude.includes(q))
    : [...ALL_QUESTIONS];
  const result: string[] = [];
  for (let i = 0; i < count && pool.length > 0; i++) {
    const idx = Math.floor(Math.random() * pool.length);
    result.push(pool[idx]);
    pool.splice(idx, 1);
  }
  return result;
}

interface WelcomeScreenProps {
  onSendMessage: (message: string) => void;
  onStop: () => void;
  isStreaming: boolean;
}

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.2 },
  },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: "easeOut" as const } },
};

export function WelcomeScreen({ onSendMessage, onStop, isStreaming }: WelcomeScreenProps) {
  const [value, setValue] = useState("");
  const [questions, setQuestions] = useState(() => pickRandom(3));
  const [shuffleKey, setShuffleKey] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Subscribe to pendingInput changes outside the render cycle to avoid
  // cascading setState-in-effect warnings.
  useEffect(() => {
    return useChatStore.subscribe((state) => {
      if (state.pendingInput) {
        setValue(state.pendingInput);
        state.setPendingInput(null);
        textareaRef.current?.focus();
      }
    });
  }, []);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isStreaming) return;
    onSendMessage(trimmed);
    setValue("");
  }, [value, isStreaming, onSendMessage]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleShuffle = useCallback(() => {
    setQuestions((prev) => pickRandom(3, prev));
    setShuffleKey((k) => k + 1);
  }, []);

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-3 sm:px-4 py-8 sm:py-12">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-6 text-center"
      >
        <h1 className="text-4xl font-bold leading-tight tracking-tight pb-1 sm:text-5xl">
          Insight<span className="text-primary dark:text-cyan-accent">Xpert</span>
        </h1>
        <p className="mt-3 text-sm text-muted-foreground sm:text-base">
          AI-powered analytics for Indian digital payments
        </p>
      </motion.div>

      {/* Centered input bar */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
        className="w-full max-w-2xl"
      >
        <div className="glass-input flex flex-col rounded-2xl px-3 py-1.5">
          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about Indian digital payments..."
            className="min-h-[36px] max-h-[140px] flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm shadow-none focus-visible:ring-0"
            rows={1}
          />
          <InputToolbar
            onSend={handleSend}
            onStop={onStop}
            isStreaming={isStreaming}
            canSend={!!value.trim()}
          />
        </div>
      </motion.div>

      <p className="mt-2 text-center text-[11px] text-muted-foreground/60">
        AI can make mistakes. Please double-check responses.
      </p>

      {/* Suggestion chips */}
      <AnimatePresence mode="wait">
        <motion.div
          key={shuffleKey}
          variants={container}
          initial="hidden"
          animate="show"
          exit="hidden"
          className="mt-4 sm:mt-6 grid w-full max-w-2xl grid-cols-1 min-[400px]:grid-cols-3 gap-2 sm:gap-3"
        >
          {questions.map((question) => (
            <motion.button
              key={question}
              variants={item}
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => onSendMessage(question)}
              className="glass cursor-pointer rounded-xl px-4 py-3 text-left text-xs leading-relaxed text-foreground/80 transition-shadow hover:shadow-[0_0_20px_rgba(6,182,212,0.15)] sm:text-sm"
            >
              <span className="line-clamp-3">{question}</span>
            </motion.button>
          ))}
        </motion.div>
      </AnimatePresence>

      {/* Shuffle button */}
      <motion.button
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.5 }}
        onClick={handleShuffle}
        className="mt-3 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-muted-foreground/70 transition-colors hover:text-foreground/80 hover:bg-accent/50 cursor-pointer"
      >
        <Shuffle className="size-3" />
        Shuffle suggestions
      </motion.button>
    </div>
  );
}
