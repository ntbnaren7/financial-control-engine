import React from 'react';
import { FlickeringGrid } from './FlickeringGrid';

export const TerminalFooter: React.FC = () => {

  return (
    <footer className="w-full pt-16 pb-12 text-zinc-400 font-mono text-sm relative z-10 overflow-hidden border-t border-white/5">
      
      {/* Background Grid */}
      <div className="absolute inset-0 z-0 pointer-events-none opacity-40">
        <FlickeringGrid 
          squareSize={4}
          gridGap={6}
          color="rgba(255, 255, 255, 0.4)"
          maxOpacity={0.15}
          flickerChance={0.1}
        />
      </div>

      {/* Smooth top fade transition from Open Source section */}
      <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-black to-transparent z-10 pointer-events-none" />

      {/* Content */}
      <div className="max-w-[1200px] mx-auto px-6 md:px-8 relative z-20">
        


        {/* Command Output Layout */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-x-8 gap-y-12 mb-16">
          
          <div>
            <h3 className="text-white font-bold mb-4 tracking-wider">NAME</h3>
            <p className="text-zinc-500 leading-relaxed">
              <span className="text-zinc-300">invariant</span> - The control plane<br />
              between non-deterministic<br />
              AI intent and deterministic<br />
              enterprise truth.
            </p>
          </div>

          <div className="md:justify-self-center">
            <h3 className="text-white font-bold mb-4 tracking-wider">COMMANDS</h3>
            <ul className="space-y-3 text-zinc-500">
              <li><a href="#how-it-works" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> man architecture</a></li>
              <li><a href="#open-source" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> cat open_source</a></li>
              <li><a href="#product" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> cd /platform</a></li>
            </ul>
          </div>

          <div className="md:justify-self-end">
            <h3 className="text-white font-bold mb-4 tracking-wider">RESOURCES</h3>
            <ul className="space-y-3 text-zinc-500">
              <li><a href="https://github.com/ntbnaren7/financial-control-engine" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> open repository</a></li>
              <li><a href="https://github.com/ntbnaren7/financial-control-engine#readme" target="_blank" rel="noreferrer" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> cat docs.md</a></li>
              <li><a href="https://www.linkedin.com/in/naren-tech/" target="_blank" rel="noreferrer" className="hover:text-white transition-colors flex gap-2"><span className="text-zinc-600">$</span> ping support</a></li>
            </ul>
          </div>
        </div>

        {/* Active Prompt */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-zinc-300 font-mono text-sm mt-16 pt-8 border-t border-white/10">
          <div className="flex items-center gap-2 text-green-400">
            Built for Tracks 3 & 4 of the Razorpay Buildathon.
          </div>
          
          <div className="text-zinc-600 text-xs sm:text-right">
            Copyright &copy; Naren A. MIT License.
          </div>
        </div>

      </div>
    </footer>
  );
};
