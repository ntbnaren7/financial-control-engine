import { useRef } from 'react';
import { Search } from 'lucide-react';
import { motion, useScroll, useTransform } from 'framer-motion';
import { SimulationShowcase } from './components/SimulationShowcase';
import type { 
  ScenarioDefinition, 
  ScenarioPresetId, 
  PipelineStageId, 
  ProofItem 
} from './types';


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
  const macbookRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: macbookRef,
    offset: ["start 80%", "end 20%"],
  });

  // Tilted backwards initially, scaling up and flattening as you scroll
  const rotateX = useTransform(scrollYProgress, [0, 0.5], [25, 0]);
  const scale = useTransform(scrollYProgress, [0, 0.5], [0.8, 1]);
  const translateY = useTransform(scrollYProgress, [0, 0.5], [50, 0]);
  const opacity = useTransform(scrollYProgress, [0, 0.3], [0, 1]);
  return (
    <div className="min-h-screen text-white font-sans selection:bg-blue-500/30 selection:text-white relative">
      
      {/* =========================================
          PHASE 3: BACKGROUND ATMOSPHERE & GRID
      ========================================= */}
      
      <div className="absolute top-0 left-0 w-full h-[1200px] bg-white pointer-events-none z-0" />
      
      {/* Base Vertical Gradient - Fades to white at 850px down */}
      <div className="absolute top-0 left-0 w-full h-[850px] bg-gradient-to-b from-[#020617] from-0% via-[#1D4ED8] via-60% to-white to-100% pointer-events-none z-0" />
      
      {/* Smooth White Transition Overlays on Left & Right Edges (Pulling the white up on the sides) */}
      <div className="absolute top-[250px] left-0 w-[45vw] max-w-[800px] h-[600px] bg-[radial-gradient(ellipse_100%_100%_at_0%_100%,rgba(255,255,255,1)_20%,rgba(255,255,255,0)_100%)] pointer-events-none z-0" />
      <div className="absolute top-[250px] right-0 w-[45vw] max-w-[800px] h-[600px] bg-[radial-gradient(ellipse_100%_100%_at_100%_100%,rgba(255,255,255,1)_20%,rgba(255,255,255,0)_100%)] pointer-events-none z-0" />
      
      {/* Central intense glow behind illustration */}
      <div className="absolute top-[400px] left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.5)_0%,transparent_70%)] pointer-events-none z-0 mix-blend-screen" />

      {/* The masked grid spanning the hero region */}
      <div className="absolute top-0 left-0 w-full h-[1200px] hero-grid pointer-events-none z-0" />

      {/* =========================================
          PHASE 2: MACRO LAYOUT & SHELL
      ========================================= */}
      
      {/* Navbar: Floating Elements */}
      <nav className="absolute top-6 left-1/2 -translate-x-1/2 z-50 flex items-center justify-between w-[95%] max-w-6xl">
        {/* Left: Logo */}
        <div className="flex items-center gap-1.5 font-bold tracking-tight">
          <span className="text-white font-black text-xl leading-none">↗</span>
          <span className="text-white text-sm font-bold">FCE</span>
        </div>

        {/* Center: Glassmorphic Pill */}
        <div className="hidden md:flex absolute left-1/2 -translate-x-1/2 items-center bg-[#020617]/60 backdrop-blur-xl border border-white/10 rounded-md p-1.5">
          <a href="#product" className="text-slate-900 bg-white rounded shadow-sm px-5 py-2 text-sm font-semibold transition-all">Platform</a>
          <a href="#how-it-works" className="text-white hover:bg-white/10 rounded px-5 py-2 text-sm font-medium transition-all">How it works</a>
          <a href="#results" className="text-white hover:bg-white/10 rounded px-5 py-2 text-sm font-medium transition-all">Impact</a>
        </div>

        {/* Right: CTA */}
        <a 
          href="https://github.com" 
          target="_blank" 
          rel="noreferrer"
          className="flex items-center bg-white hover:bg-slate-100 text-[#020617] px-5 py-2.5 rounded-md text-sm font-bold transition-all shadow-sm"
        >
          View on GitHub
        </a>
      </nav>

      {/* Hero Region */}
      <section id="product" className="pt-40 pb-20 relative z-10 flex flex-col items-center text-center">
        
        {/* =========================================
            PHASE 4: TYPOGRAPHY COMPOSITION
        ========================================= */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-[1100px] w-full mx-auto flex flex-col items-center px-6"
        >

          <div className="flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-white/[0.03] border border-white/10 backdrop-blur-md mb-8">
            <div className="w-1.5 h-1.5 rounded-full bg-white/80" />
            <span className="text-sm font-medium text-white/90 tracking-wide">Simulation Engine</span>
          </div>
          
          <h1 className="text-5xl md:text-[80px] font-bold tracking-[-0.04em] leading-[1.05] text-white">
            Detect Mismatches <br />
            Automate Resolutions <br />
            All right inside FCE
          </h1>
          
          <p className="mt-8 text-lg text-white/80 leading-relaxed font-medium max-w-2xl mx-auto">
            A high-performance reconciliation platform that empowers engineering teams to build robust financial controls, pinpoint transaction discrepancies, and automate resolutions at scale.
          </p>
        </motion.div>

        {/* =========================================
            PHASE 5: LAPTOP MOCKUP (3D SCROLL EFFECT)
        ========================================= */}
        <div ref={macbookRef} style={{ perspective: "1500px" }} className="w-full relative pb-32">
          <motion.div
            style={{ 
              rotateX, 
              scale, 
              y: translateY,
              opacity,
              transformStyle: "preserve-3d" 
            }}
            className="relative w-full max-w-[1100px] mx-auto -mt-20 px-4 md:px-8 z-20 origin-bottom"
          >
            {/* Laptop Base and Screen */}
          <div className="relative mx-auto w-full">
            {/* Screen bezel */}
            <div className="bg-[#0f172a] rounded-t-[16px] rounded-b-[4px] border-[10px] border-[#0f172a] shadow-[0_30px_60px_-15px_rgba(0,0,0,0.5)] overflow-hidden flex flex-col relative h-[650px]">
              
              {/* Fake Webcam */}
              <div className="absolute top-1 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-slate-800 border border-slate-900 z-50" />

              {/* Browser/OS Header */}
              <div className="h-10 bg-slate-50 border-b border-slate-200 flex items-center px-4 gap-2 relative z-40 mt-1">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-rose-400" />
                  <div className="w-2.5 h-2.5 rounded-full bg-amber-400" />
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                </div>
                <div className="mx-auto text-xs font-medium font-mono text-slate-500 bg-white px-4 py-1 rounded-md border border-slate-200 shadow-sm flex items-center gap-2">
                  <Search className="w-3 h-3 text-slate-400" />
                  fce-dashboard.local
                </div>
                <div className="w-10" />
              </div>

              {/* The Actual FCE UI inside the laptop */}
              <div className="flex-1 overflow-y-auto bg-slate-50 relative pointer-events-auto custom-scrollbar">
                <SimulationShowcase {...props} />
              </div>
            </div>
            
            {/* Laptop Bottom Lip */}
            <div className="h-4 md:h-5 bg-gradient-to-b from-[#94a3b8] to-[#475569] w-[104%] md:w-[108%] absolute -bottom-4 md:-bottom-5 left-1/2 -translate-x-1/2 rounded-b-[20px] shadow-[0_20px_40px_-10px_rgba(0,0,0,0.5)] flex justify-center z-30">
              {/* Thumb indent */}
              <div className="w-20 h-2 bg-slate-600 rounded-b-md" />
            </div>
          </div>
        </motion.div>
        </div>
      </section>



      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-12 relative z-10">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <span className="text-blue-600 font-black text-xl leading-none">↗</span>
            <span className="text-xl font-bold tracking-tight text-slate-900">FCE</span>
            <span className="text-slate-400 text-sm font-medium ml-2">| Razorpay Buildathon 2026</span>
          </div>
          <div className="text-sm font-medium text-slate-400">
            Detect discrepancies. Enable trust.
          </div>
        </div>
      </footer>
    </div>
  );
};
