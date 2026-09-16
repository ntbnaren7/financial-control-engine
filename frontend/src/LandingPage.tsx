import React from 'react';
import { motion } from 'framer-motion';
import { UnboundedEngineCanvas } from './components/UnboundedEngineCanvas';
import type { 
  ScenarioDefinition, 
  ScenarioPresetId, 
  PipelineStageId, 
  ProofItem 
} from './types';

import { FlickeringGrid } from './components/FlickeringGrid';
import { PipelineIdeView } from './components/PipelineIdeView';
import { OpenSourceSection } from './components/OpenSourceSection';
import { TerminalFooter } from './components/TerminalFooter';

interface LandingPageProps {
  currentScenario: ScenarioDefinition;
  currentScenarioId: ScenarioPresetId;
  onSelectScenario: (id: ScenarioPresetId) => void;
  currentStageIndex: number;
  selectedStageId: PipelineStageId | 'READY';
  onSelectStage: (id: PipelineStageId | 'READY') => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onStepForward: () => void;
  onReset: () => void;
  playbackSpeed: number;
  onChangeSpeed: (speed: number) => void;
  proofs: ProofItem[];
  caseIdentity: {
    paymentId: string;
    orderId: string;
    amount: number;
    currency: string;
  };
}

export const LandingPage: React.FC<LandingPageProps> = (props) => {
  return (
    <div className="min-h-screen text-white font-sans selection:bg-blue-500/30 selection:text-white relative bg-[#000000]">
      
      {/* Navbar: Floating Elements */}
      <motion.nav 
        initial={{ opacity: 0, y: -20, x: "-50%" }}
        animate={{ opacity: 1, y: 0, x: "-50%" }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className="fixed top-6 left-1/2 z-50 flex items-center justify-between w-[95%] max-w-7xl"
      >
        <div className="flex items-center gap-2 font-bold tracking-tight">
          <a 
            href="#" 
            onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }} 
            className="flex items-center gap-2 text-white text-xl font-bold tracking-tight cursor-pointer hover:opacity-80 transition-opacity"
          >
            <img src="/apple-touch-icon.png" alt="Invariant Logo" className="w-6 h-6 rounded-md" />
            Invariant
          </a>
        </div>

        {/* Center: Glassmorphic Pill */}
        <div className="hidden md:flex absolute left-1/2 -translate-x-1/2 items-center bg-zinc-900/60 backdrop-blur-xl border border-white/10 rounded-full p-1.5">
          <a href="#product" className="text-black bg-white rounded-full px-5 py-2 text-sm font-semibold transition-all">Platform</a>
          <a href="#how-it-works" className="text-zinc-300 hover:text-white rounded-full px-5 py-2 text-sm font-medium transition-colors">Architecture</a>
          <a href="#open-source" className="text-zinc-300 hover:text-white rounded-full px-5 py-2 text-sm font-medium transition-colors">Open Source</a>
        </div>

        {/* Right: CTA */}
        <a 
          href="https://github.com/ntbnaren7/financial-control-engine#readme" 
          target="_blank" 
          rel="noreferrer"
          className="flex items-center bg-zinc-900 hover:bg-zinc-800 text-white border border-white/10 px-5 py-2.5 rounded-md text-sm font-medium transition-all shadow-sm"
        >
          View Documentation
        </a>
      </motion.nav>

      {/* Hero Region */}
      <section id="product" className="pt-40 pb-0 relative z-10 flex flex-col items-center">
        
        {/* Flickering Grid Background */}
        <div 
          className="absolute inset-0 z-0 pointer-events-none" 
          style={{ 
            maskImage: 'linear-gradient(to bottom, white 0%, white 80%, transparent 100%)', 
            WebkitMaskImage: 'linear-gradient(to bottom, white 0%, white 80%, transparent 100%)' 
          }}
        >
          <FlickeringGrid 
            className="w-full h-full"
            squareSize={4}
            gridGap={6}
            color="#ffffff"
            maxOpacity={0.1}
            flickerChance={0.3}
          />
        </div>

        {/* TYPOGRAPHY COMPOSITION */}
        <div className="max-w-[1200px] w-full mx-auto flex flex-col items-center text-center px-6 relative z-10">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
            className="flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-white/[0.03] border border-white/10 backdrop-blur-md mb-8"
          >
            <div className="relative flex items-center justify-center w-2 h-2">
              <div className="absolute inset-0 rounded-full bg-blue-500 animate-ping opacity-75" />
              <div className="relative w-1.5 h-1.5 rounded-full bg-blue-500" />
            </div>
            <span className="font-mono text-xs font-medium text-zinc-400 tracking-widest uppercase">FCE // CONTROL LOOP WALKTHROUGH</span>
          </motion.div>
          
          <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
            className="text-5xl md:text-[80px] font-bold tracking-[-0.04em] leading-[1.05] text-white"
          >
            A control plane for <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-zinc-400 to-zinc-600">
              payment operations.
            </span>
          </motion.h1>
          
          <motion.p 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.3 }}
            className="mt-8 text-lg text-zinc-400 leading-relaxed max-w-2xl mx-auto font-medium"
          >
            A deterministic control layer between financial state and financial action. Invariant sits around the payment lifecycle to guarantee that when internal state and provider state diverge, they safely converge.
          </motion.p>
        </div>

        {/* =========================================
            UNBOUNDED ENGINE CANVAS
        ========================================= */}
        <motion.div 
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, ease: [0.16, 1, 0.3, 1], delay: 0.4 }}
          className="w-full max-w-[1600px] mx-auto px-4 md:px-8 z-20"
        >
          <UnboundedEngineCanvas {...props} />
        </motion.div>
      </section>

      <PipelineIdeView />
      <OpenSourceSection />
      <TerminalFooter />
    </div>
  );
};
