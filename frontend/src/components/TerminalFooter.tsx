import React, { useState, useEffect } from 'react';
import { Terminal } from 'lucide-react';

export const TerminalFooter: React.FC = () => {
  const [cursorBlink, setCursorBlink] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setCursorBlink(b => !b);
    }, 530);
    return () => clearInterval(interval);
  }, []);

  return (
    <footer className="w-full bg-[#050505] border-t border-white/10 pt-16 pb-12 text-zinc-400 font-mono text-sm relative z-10">
      <div className="max-w-[1200px] mx-auto px-6 md:px-8">
        
        {/* Terminal Header */}
        <div className="flex items-center gap-2 mb-10 text-zinc-500 border-b border-white/10 pb-4">
          <Terminal className="w-4 h-4" />
          <span>invariant-sys --help</span>
        </div>

        {/* Command Output Layout */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-x-8 gap-y-12 mb-16">
          
          <div className="md:col-span-1">
            <h3 className="text-white font-bold mb-4 tracking-wider">NAME</h3>
            <p className="text-zinc-500 leading-relaxed">
              <span className="text-zinc-300">invariant</span> - The control plane between non-deterministic AI intent and deterministic enterprise truth.
            </p>
          </div>

          <div className="md:col-span-1">
            <h3 className="text-white font-bold mb-4 tracking-wider">COMMANDS</h3>
            <ul className="space-y-3 text-zinc-500">
              <li><a href="#how-it-works" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> man architecture</a></li>
              <li><a href="#open-source" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> cat open_source</a></li>
              <li><a href="#product" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> cd /platform</a></li>
            </ul>
          </div>

          <div className="md:col-span-1">
            <h3 className="text-white font-bold mb-4 tracking-wider">RESOURCES</h3>
            <ul className="space-y-3 text-zinc-500">
              <li><a href="https://github.com/ntbnaren7/financial-control-engine" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> open repository</a></li>
              <li><a href="#" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> cat docs.md</a></li>
              <li><a href="https://linkedin.com/in/ntbnaren7" target="_blank" rel="noreferrer" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> ping support</a></li>
            </ul>
          </div>

          <div className="md:col-span-1">
            <h3 className="text-white font-bold mb-4 tracking-wider">SYSTEM</h3>
            <ul className="space-y-3 text-zinc-500">
              <li className="flex justify-between"><span>VERSION</span> <span className="text-zinc-300">v1.0.0-rc</span></li>
              <li className="flex justify-between"><span>BUILD</span> <span className="text-zinc-300">2026.09.15</span></li>
              <li className="flex justify-between"><span>UPTIME</span> <span className="text-zinc-300">99.999%</span></li>
            </ul>
          </div>

        </div>

        {/* Active Prompt */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-zinc-300 font-mono text-sm mt-16 pt-8 border-t border-white/10">
          <div className="flex items-center gap-2">
            <span className="text-green-400">invariant-engine@razorpay</span>
            <span className="text-zinc-500">:</span>
            <span className="text-blue-400">~</span>
            <span className="text-zinc-500">$</span>
            <span className={`w-2.5 h-5 bg-white transition-opacity duration-75 ${cursorBlink ? 'opacity-100' : 'opacity-0'}`} />
          </div>
          
          <div className="text-zinc-600 text-xs">
            &copy; {new Date().getFullYear()} Razorpay Buildathon. System active.
          </div>
        </div>

      </div>
    </footer>
  );
};
