"use client";

import { motion } from "framer-motion";
import { SUGGESTED_QUESTIONS } from "@/lib/constants";

interface WelcomeScreenProps {
  onSendMessage: (message: string) => void;
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

export function WelcomeScreen({ onSendMessage }: WelcomeScreenProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-2 text-center"
      >
        <h1 className="bg-gradient-to-r from-cyan-400 to-cyan-600 bg-clip-text text-4xl font-bold tracking-tight text-transparent sm:text-5xl">
          InsightXpert
        </h1>
        <p className="mt-3 text-sm text-muted-foreground sm:text-base">
          AI-powered analytics for Indian digital payments
        </p>
      </motion.div>

      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="mt-10 grid w-full max-w-2xl grid-cols-2 gap-3 sm:grid-cols-3"
      >
        {SUGGESTED_QUESTIONS.map((question) => (
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
    </div>
  );
}
