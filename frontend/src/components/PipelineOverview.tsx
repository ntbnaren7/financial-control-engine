import { motion } from 'framer-motion';
import { Search, Zap, CheckCircle2, ShieldAlert, Cpu, RotateCcw, Flag } from 'lucide-react';

const STAGES = [
  { id: 'DETECT', title: 'DETECT', sub: 'Ingest & Reconcile', icon: Search, color: 'text-blue-500', bg: 'bg-blue-500' },
  { id: 'INVESTIGATE', title: 'INVESTIGATE', sub: 'A3 Reasoner', icon: Cpu, color: 'text-indigo-500', bg: 'bg-indigo-500' },
  { id: 'VERIFY', title: 'VERIFY', sub: 'A4 Verifier', icon: ShieldAlert, color: 'text-purple-500', bg: 'bg-purple-500' },
  { id: 'DECIDE', title: 'DECIDE', sub: 'Policy & Gov', icon: Zap, color: 'text-amber-500', bg: 'bg-amber-500' },
  { id: 'ACT', title: 'ACT', sub: 'OCC Actuator', icon: CheckCircle2, color: 'text-emerald-500', bg: 'bg-emerald-500' },
  { id: 'REOBSERVE', title: 'RE-OBSERVE', sub: 'Fresh State', icon: RotateCcw, color: 'text-teal-500', bg: 'bg-teal-500' },
  { id: 'OUTCOME', title: 'OUTCOME', sub: 'Resolved / Escalated', icon: Flag, color: 'text-rose-500', bg: 'bg-rose-500' }
];

export const PipelineOverview = () => {
  return (
    <div className="w-full h-full bg-[#f8fafc] p-6 flex flex-col relative rounded-b-[4px]">
      
      {/* Subtle Dot Background */}
      <div 
        className="absolute inset-0 pointer-events-none z-0" 
        style={{
          backgroundImage: 'radial-gradient(#CBD5E1 1px, transparent 1px)',
          backgroundSize: '24px 24px',
          opacity: 0.4
        }} 
      />

      <div className="max-w-[400px] mx-auto w-full relative pt-2 z-10">
        
        {/* The Timeline Track (Background Line) */}
        <div className="absolute left-[23px] top-10 bottom-10 w-[2px] bg-slate-200 rounded-full" />
        
        {/* The Animated Pulse Line (Foreground Line) */}
        <motion.div 
          className="absolute left-[23px] top-10 w-[2px] bg-gradient-to-b from-blue-400 via-indigo-500 to-emerald-400 rounded-full origin-top z-10"
          animate={{ height: ['0%', '100%', '100%', '0%'], opacity: [1, 1, 0, 0] }}
          transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
        />

        <div className="flex flex-col gap-4 relative z-20">
          {STAGES.map((stage, i) => (
            <div key={stage.id} className="flex items-center gap-6 group">
              {/* Node Circle */}
              <div className="relative shrink-0">
                <div className="w-12 h-12 rounded-full bg-white shadow-sm border border-slate-200 flex items-center justify-center z-20 relative group-hover:scale-110 transition-transform duration-300">
                  <stage.icon className={`w-5 h-5 ${stage.color}`} />
                </div>
                {/* Ping effect behind the icon */}
                <motion.div 
                  className={`absolute inset-0 rounded-full ${stage.bg}`}
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ scale: [1, 1.5, 1], opacity: [0, 0.3, 0] }}
                  transition={{ 
                    duration: 3, 
                    repeat: Infinity, 
                    delay: i * (6 / 7), // Stagger based on total animation time
                    ease: "easeOut"
                  }}
                />
              </div>

              {/* Card */}
              <div className="flex-1 bg-white/80 backdrop-blur-sm rounded-xl p-3.5 shadow-[0_4px_20px_rgb(0,0,0,0.02)] border border-slate-200/60 group-hover:-translate-y-0.5 group-hover:shadow-md transition-all cursor-default">
                <div className="text-[10px] font-bold tracking-widest text-slate-400 mb-0.5 uppercase">
                  {`0${i + 1} // ${stage.title}`}
                </div>
                <div className="text-slate-800 font-semibold text-sm">
                  {stage.sub}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
