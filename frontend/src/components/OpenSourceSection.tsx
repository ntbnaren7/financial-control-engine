import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Star, 
  GitFork, 
  Copy,
  Check,
  ChevronRight, 
  ChevronDown, 
  Folder, 
  FileText, 
  FileCode2,
  Terminal,
  CircleDot
} from 'lucide-react';

export const OpenSourceSection: React.FC = () => {
  const [isCopied, setIsCopied] = useState(false);

  return (
    <section id="open-source" className="w-full relative z-10 pt-0 pb-16 flex flex-col items-center justify-center overflow-hidden scroll-mt-32">
      
      {/* Background Ambience */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1000px] h-[600px] bg-[radial-gradient(ellipse_50%_50%_at_50%_50%,rgba(59,130,246,0.08),transparent_100%)] pointer-events-none" />

      <div className="max-w-[1200px] w-full mx-auto px-4 md:px-8 flex flex-col items-center relative z-10">
        
        {/* Section Header & CTA */}
        <div className="flex flex-col items-center text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-white mb-6 leading-[80px]">
            Built in the open.<br/>Verify everything.
          </h2>
          <p className="text-lg text-zinc-400 max-w-2xl leading-relaxed mb-10">
            Trust isn't given; it's proven. Audit the deterministic state gates, cryptographic trails, and version-locked actuators directly in our repository.
          </p>

          <div className="flex flex-col sm:flex-row items-center gap-4">
            <a 
              href="https://github.com/ntbnaren7/financial-control-engine" 
              target="_blank" 
              rel="noreferrer"
              className="group relative inline-flex items-center justify-center gap-2 px-8 py-4 bg-white text-black font-semibold rounded-lg overflow-hidden transition-all duration-300 hover:shadow-[0_0_40px_rgba(255,255,255,0.3)]"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-zinc-200 to-white opacity-0 group-hover:opacity-100 transition-opacity" />
              <Star className="w-5 h-5 relative z-10 text-yellow-400 fill-yellow-400" />
              <span className="relative z-10">Star on GitHub</span>
            </a>
            
            <button 
              className="group relative flex items-center justify-center bg-white/5 hover:bg-white/10 border border-white/10 text-white font-medium rounded-lg transition-all duration-300 w-40 h-[54px] overflow-hidden"
              onClick={() => {
                navigator.clipboard.writeText("git clone https://github.com/ntbnaren7/financial-control-engine.git");
                setIsCopied(true);
                setTimeout(() => setIsCopied(false), 2000);
              }}
            >
              <AnimatePresence mode="wait">
                {isCopied ? (
                  <motion.div
                    key="copied"
                    initial={{ opacity: 0, y: 15 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -15 }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                    className="flex items-center gap-2 absolute inset-0 justify-center"
                  >
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="font-mono text-sm text-green-400">Copied!</span>
                  </motion.div>
                ) : (
                  <motion.div
                    key="clone"
                    initial={{ opacity: 0, y: 15 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -15 }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                    className="flex items-center gap-2 absolute inset-0 justify-center"
                  >
                    <Copy className="w-4 h-4 text-zinc-400 group-hover:text-white transition-colors" />
                    <span className="font-mono text-sm">git clone</span>
                  </motion.div>
                )}
              </AnimatePresence>
            </button>
          </div>
        </div>

        {/* The IDE Window */}
        <motion.div 
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="w-full flex flex-col rounded-xl border border-white/10 bg-[#050505] shadow-[0_0_80px_rgba(0,0,0,0.6)] overflow-hidden"
        >
          {/* IDE Title Bar */}
          <div className="h-10 border-b border-white/10 bg-black/40 flex items-center px-4 relative">
            <div className="flex items-center gap-2 absolute left-4">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
            </div>
            
            <div className="w-full text-center flex items-center justify-center gap-2 text-zinc-400 text-sm font-mono font-medium">
              <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current" aria-hidden="true">
                <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"></path>
              </svg>
              ntbnaren7 / financial-control-engine
            </div>
          </div>

          {/* IDE Content Area */}
          <div className="flex h-[700px]">
            
            {/* Sidebar (File Explorer) - Hidden on Mobile */}
            <div className="hidden md:flex flex-col w-64 border-r border-white/10 bg-[#09090b]">
              <div className="px-4 py-3 text-xs font-semibold text-zinc-500 tracking-wider uppercase">
                Explorer
              </div>
              
              <div className="flex flex-col text-sm font-mono text-zinc-400">
                <div className="flex items-center gap-1.5 px-4 py-1.5 hover:bg-white/5 cursor-pointer transition-colors">
                  <ChevronRight className="w-4 h-4 text-zinc-500" />
                  <Folder className="w-4 h-4 text-blue-400 fill-blue-400/20" />
                  .github
                </div>
                
                <div className="flex items-center gap-1.5 px-4 py-1.5 hover:bg-white/5 cursor-pointer transition-colors">
                  <ChevronDown className="w-4 h-4 text-zinc-500" />
                  <Folder className="w-4 h-4 text-blue-400 fill-blue-400/20" />
                  frontend
                </div>
                <div className="flex items-center gap-1.5 pl-9 pr-4 py-1.5 hover:bg-white/5 cursor-pointer transition-colors">
                  <ChevronRight className="w-4 h-4 text-zinc-500" />
                  <Folder className="w-4 h-4 text-blue-400 fill-blue-400/20" />
                  src
                </div>
                
                <div className="flex items-center gap-1.5 px-4 py-1.5 hover:bg-white/5 cursor-pointer transition-colors">
                  <ChevronRight className="w-4 h-4 text-zinc-500" />
                  <Folder className="w-4 h-4 text-blue-400 fill-blue-400/20" />
                  core-engine
                </div>

                <div className="flex items-center gap-1.5 px-4 py-1.5 bg-blue-500/10 text-blue-400 border-l-2 border-blue-500 cursor-pointer">
                  <div className="w-4" /> {/* Spacer for alignment */}
                  <FileText className="w-4 h-4" />
                  README.md
                </div>

                <div className="flex items-center gap-1.5 px-4 py-1.5 hover:bg-white/5 cursor-pointer transition-colors">
                  <div className="w-4" /> {/* Spacer for alignment */}
                  <FileCode2 className="w-4 h-4 text-amber-400" />
                  package.json
                </div>
                
                <div className="flex items-center gap-1.5 px-4 py-1.5 hover:bg-white/5 cursor-pointer transition-colors">
                  <div className="w-4" /> {/* Spacer for alignment */}
                  <FileCode2 className="w-4 h-4 text-zinc-300" />
                  tailwind.config.ts
                </div>
              </div>
            </div>

            {/* Main Editor Pane */}
            <div className="flex-1 bg-[#050505] relative overflow-hidden flex flex-col">
              
              {/* Editor Tabs */}
              <div className="flex h-10 border-b border-white/10 bg-[#09090b]">
                <div className="flex items-center gap-2 px-4 border-r border-white/10 bg-[#050505] border-t-2 border-t-blue-500">
                  <FileText className="w-4 h-4 text-blue-400" />
                  <span className="text-sm font-mono text-white">README.md</span>
                </div>
              </div>

              {/* Editor Content (Markdown Rendered) */}
              <div className="flex-1 p-8 md:p-12 md:pb-6 overflow-y-auto font-sans relative">
                
                {/* Subtle Editor Grid */}
                <div className="absolute inset-0 canvas-dot-grid opacity-[0.15] pointer-events-none" />

                <div className="relative z-10 max-w-3xl pb-2">
                  <h1 className="text-4xl font-bold text-white mb-4 tracking-tight">Invariant - Financial Control Engine</h1>
                  
                  <div className="flex flex-wrap gap-2 mb-8">
                    <span className="px-2 py-1 bg-white/5 border border-white/10 rounded text-xs font-mono text-zinc-300">license: MIT</span>
                    <span className="px-2 py-1 bg-white/5 border border-white/10 rounded text-xs font-mono text-zinc-300">version: 1.0.0</span>
                    <span className="px-2 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded text-xs font-mono text-emerald-400">build: passing</span>
                    <span className="px-2 py-1 bg-blue-500/10 border border-blue-500/20 rounded text-xs font-mono text-blue-400">status: production-ready</span>
                  </div>

                  <blockquote className="border-l-4 border-blue-500 pl-4 py-1 mb-10 text-xl text-zinc-300 font-medium">
                    "The control plane between non-deterministic AI intent and deterministic enterprise truth."
                  </blockquote>

                  <h2 className="text-2xl font-semibold text-white mb-4 border-b border-white/10 pb-2">Overview</h2>
                  <p className="text-zinc-400 leading-relaxed mb-6">
                    Invariant is a 7-stage architectural pipeline designed to safely integrate Large Language Models (LLMs) into high-stakes financial environments. It explicitly untrusts the AI, forcing all reasoning through rigid cryptographic and deterministic state gates before execution.
                  </p>

                  <h2 className="text-2xl font-semibold text-white mb-4 border-b border-white/10 pb-2">Architecture</h2>
                  <ul className="list-disc pl-5 text-zinc-400 space-y-2 mb-8 marker:text-zinc-600">
                    <li><strong className="text-zinc-200">Stage 1 (D1 Extractor):</strong> Deterministic data extraction from unstructured intents.</li>
                    <li><strong className="text-zinc-200">Stage 2 (D2 Synthesizer):</strong> Action formulation without execution.</li>
                    <li><strong className="text-zinc-200">Stage 3 (D3 Simulator):</strong> Parallel sandboxed dry-runs to project state impact.</li>
                    <li><strong className="text-zinc-200">Stage 4 (D4 Verifier):</strong> Cryptographic anomaly detection and drift analysis.</li>
                    <li><strong className="text-zinc-200">Stage 5 (Policy & Gov):</strong> Hard-coded business rule enforcement.</li>
                    <li><strong className="text-zinc-200">Stage 6 (OCC Actuator):</strong> Optimistic Concurrency Control commits.</li>
                    <li><strong className="text-zinc-200">Stage 7 (Terminal Outcome):</strong> Absolute ledger finality.</li>
                  </ul>

                  <h2 className="text-2xl font-semibold text-white mb-4 border-b border-white/10 pb-2">Why a Database?</h2>
                  <p className="text-zinc-400 leading-relaxed mb-8">
                    While LLMs are inherently stateless and non-deterministic, financial systems require absolute state persistence and auditability. The database serves as the ultimate source of truth, enforcing Optimistic Concurrency Control (OCC) at Stage 6 and providing the immutable ledger for the Terminal Outcome (Stage 7). Without it, cryptographic trails and rollback capabilities would be impossible.
                  </p>

                  <h2 className="text-2xl font-semibold text-white mb-4 border-b border-white/10 pb-2">Quick Start</h2>
                  <div className="bg-[#09090b] border border-white/10 rounded-lg p-4 font-mono text-sm text-zinc-300 mb-8 shadow-inner">
                    <div className="flex items-center gap-2 mb-2">
                      <Terminal className="w-4 h-4 text-zinc-500" />
                      <span className="text-zinc-500"># Clone the repository</span>
                    </div>
                    <div className="text-blue-400">git clone https://github.com/ntbnaren7/financial-control-engine.git</div>
                    
                    <div className="mt-4 flex items-center gap-2 mb-2">
                      <Terminal className="w-4 h-4 text-zinc-500" />
                      <span className="text-zinc-500"># Install dependencies</span>
                    </div>
                    <div className="text-white">npm install</div>

                    <div className="mt-4 flex items-center gap-2 mb-2">
                      <Terminal className="w-4 h-4 text-zinc-500" />
                      <span className="text-zinc-500"># Setup database (PostgreSQL required)</span>
                    </div>
                    <div className="text-white">cp .env.example .env</div>
                    <div className="text-white mt-1">npm run db:migrate</div>
                    <div className="text-white mt-1">npm run db:seed</div>

                    <div className="mt-4 flex items-center gap-2 mb-2">
                      <Terminal className="w-4 h-4 text-zinc-500" />
                      <span className="text-zinc-500"># Start the engine locally</span>
                    </div>
                    <div className="text-white">npm run dev</div>
                  </div>
                </div>

                {/* Bottom Fade Gradient for text overflow illusion */}
                <div className="absolute bottom-0 inset-x-0 h-32 bg-gradient-to-t from-[#050505] to-transparent pointer-events-none" />
              </div>
            </div>
          </div>

          {/* IDE Status Bar */}
          <div className="h-7 border-t border-white/10 bg-[#09090b] flex items-center justify-between px-4 text-xs font-mono text-zinc-500">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5 hover:text-white cursor-pointer transition-colors">
                <GitFork className="w-3.5 h-3.5" />
                <span>main*</span>
              </div>
              <div className="flex items-center gap-1.5 hover:text-white cursor-pointer transition-colors">
                <CircleDot className="w-3.5 h-3.5 text-blue-500" />
                <span>0 errors, 0 warnings</span>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <div className="hidden sm:flex items-center gap-1.5 hover:text-white cursor-pointer transition-colors">
                <Star className="w-3.5 h-3.5" />
                <span>0 Stars</span>
              </div>
              <div className="hidden sm:flex items-center gap-1.5 hover:text-white cursor-pointer transition-colors">
                <GitFork className="w-3.5 h-3.5" />
                <span>0 Forks</span>
              </div>
              <div className="flex items-center gap-1.5 hover:text-white cursor-pointer transition-colors">
                <span>UTF-8</span>
              </div>
              <div className="flex items-center gap-1.5 hover:text-white cursor-pointer transition-colors">
                <span>Python (83.8%)</span>
              </div>
            </div>
          </div>

        </motion.div>
      </div>
    </section>
  );
};
