import React, { useEffect, useRef, useState } from 'react';
import { Search, Cpu, ShieldAlert, Zap, CheckCircle2, RotateCcw, Flag, Lock, Terminal, Database, FileJson, Check, AlertTriangle, AlertCircle } from 'lucide-react';

const STAGES = [
  { id: 'stage-01', index: '01', title: 'Ingest & Detect', icon: Search, file: '01_ingest_detect.ts' },
  { id: 'stage-02', index: '02', title: 'A3 Reasoner', icon: Cpu, file: '02_a3_reasoner.ts' },
  { id: 'stage-03', index: '03', title: 'D4 Verifier', icon: ShieldAlert, file: '03_d4_verifier.ts' },
  { id: 'stage-04', index: '04', title: 'Policy & Gov', icon: Zap, file: '04_governance_gate.ts' },
  { id: 'stage-05', index: '05', title: 'OCC Actuator', icon: CheckCircle2, file: '05_occ_actuator.ts' },
  { id: 'stage-06', index: '06', title: 'Re-Observe', icon: RotateCcw, file: '06_reobserve.ts' },
  { id: 'stage-07', index: '07', title: 'Terminal Outcome', icon: Flag, file: '07_terminal_outcome.ts' },
];

export const PipelineIdeView: React.FC = () => {
  const [activeStageId, setActiveStageId] = useState<string>('stage-01');
  const stageRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.intersectionRatio > 0.3) {
            setActiveStageId(entry.target.id);
          }
        });
      },
      {
        root: null,
        rootMargin: '-20% 0px -40% 0px',
        threshold: [0.3, 0.6],
      }
    );

    Object.values(stageRefs.current).forEach((ref) => {
      if (ref) observer.observe(ref);
    });

    return () => observer.disconnect();
  }, []);

  const handleScrollTo = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      const y = el.getBoundingClientRect().top + window.scrollY - 100;
      window.scrollTo({ top: y, behavior: 'smooth' });
    }
  };

  return (
    <section id="how-it-works" className="w-full relative z-10 pt-24 pb-0">
      
      {/* Background Ambience */}
      <div className="absolute inset-0 canvas-dot-grid pointer-events-none opacity-50" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-[500px] bg-[radial-gradient(ellipse_80%_50%_at_50%_0%,rgba(59,130,246,0.05),transparent_70%)] pointer-events-none" />

      <div className="max-w-[1200px] mx-auto px-6 relative z-10">
        
        {/* Section Header */}
        <div className="mb-24 flex flex-col items-start max-w-2xl">
          <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-white mb-6 leading-tight">
            The Seven Invariant Stages.
          </h2>
          <p className="text-lg text-zinc-400 leading-relaxed">
            Invariant safely encloses untrusted AI reasoning between deterministic state gates, cryptographic audit trails, and version-locked actuators.
          </p>
        </div>

        {/* IDE Split View Grid */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 lg:gap-16 relative">
          
          {/* Left Column: Explorer (Sticky) */}
          <div className="hidden md:block md:col-span-4 lg:col-span-3">
            <div className="sticky top-32 bg-[#09090b]/80 border border-white/[0.06] backdrop-blur-xl rounded-xl overflow-hidden shadow-2xl">
              
              <div className="px-4 py-3 border-b border-white/[0.06] bg-black/40 flex items-center gap-2">
                <FileJson className="w-4 h-4 text-zinc-500" />
                <span className="font-mono text-[11px] text-zinc-400 tracking-wider uppercase">Pipeline_Explorer</span>
              </div>
              
              <div className="p-2 py-3 flex flex-col gap-0.5">
                {STAGES.map((stage) => {
                  const isActive = activeStageId === stage.id;
                  const Icon = stage.icon;
                  return (
                    <button
                      key={stage.id}
                      onClick={() => handleScrollTo(stage.id)}
                      className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-all duration-200 group ${
                        isActive 
                          ? 'bg-white/[0.06] text-white shadow-[inset_2px_0_0_0_rgba(59,130,246,1)]' 
                          : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.02]'
                      }`}
                    >
                      <span className={`font-mono text-[10px] ${isActive ? 'text-blue-400' : 'text-zinc-600 group-hover:text-zinc-400'}`}>
                        {stage.index}
                      </span>
                      <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-blue-400' : 'text-zinc-500'}`} />
                      <span className="text-[13px] font-medium tracking-wide">{stage.title}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Right Column: Editor Panes */}
          <div className="col-span-1 md:col-span-8 lg:col-span-9 flex flex-col gap-24 pb-32">
            
            {/* STAGE 1 */}
            <article 
              id="stage-01" 
              ref={(el) => { stageRefs.current['stage-01'] = el as HTMLDivElement | null; }}
              className="scroll-mt-32 node-milled-border rounded-xl overflow-hidden group"
            >
              <StageHeader file="01_ingest_detect.ts" authority="DETERMINISTIC CONTROL (0% AI)" />
              <div className="p-6 md:p-8">
                <h3 className="text-2xl font-bold text-white mb-2">Dual-Ledger Ingestion & Delta Detection</h3>
                <p className="text-zinc-400 text-sm mb-8">Reconciliation Engine deterministically identifies discrepancies between the internal source of truth and provider webhooks without AI intervention.</p>
                
                {/* Micro-UI */}
                <div className="bg-[#050505] border border-white/[0.06] rounded-xl p-5 font-mono text-[12px] shadow-inner mb-6 relative overflow-hidden">
                  <div className="absolute top-0 right-0 p-3 flex gap-2">
                    <span className="px-2 py-1 bg-rose-500/10 text-rose-400 border border-rose-500/20 rounded text-[10px] uppercase flex items-center gap-1.5 shadow-[0_0_10px_rgba(244,63,94,0.3)]">
                      <div className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
                      STATE_MISMATCH
                    </span>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <div className="text-zinc-500 mb-2">// Expectation (Internal Ledger)</div>
                      <div className="text-zinc-300">{"{"}</div>
                      <div className="pl-4 text-zinc-400">"id": <span className="text-emerald-300">"exp_ord_5601928472"</span>,</div>
                      <div className="pl-4 text-zinc-400 bg-rose-500/10 border-l-2 border-rose-500 -ml-[2px] pl-[14px] py-0.5">
                        <span className="text-rose-400">- "status": "SETTLED"</span>
                      </div>
                      <div className="pl-4 text-zinc-400">"amount": <span className="text-blue-300">4500.00</span></div>
                      <div className="text-zinc-300">{"}"}</div>
                    </div>
                    
                    <div className="space-y-1 mt-4 md:mt-0">
                      <div className="text-zinc-500 mb-2">// Observation (Gateway Webhook)</div>
                      <div className="text-zinc-300">{"{"}</div>
                      <div className="pl-4 text-zinc-400">"id": <span className="text-emerald-300">"obs_pay_3819482701"</span>,</div>
                      <div className="pl-4 text-zinc-400 bg-emerald-500/10 border-l-2 border-emerald-500 -ml-[2px] pl-[14px] py-0.5">
                        <span className="text-emerald-400">+ "status": "PENDING"</span>
                      </div>
                      <div className="pl-4 text-zinc-400">"amount": <span className="text-blue-300">4500.00</span></div>
                      <div className="text-zinc-300">{"}"}</div>
                    </div>
                  </div>
                </div>

                <InvariantRule rule="State equality requires 1:1 match across all monetary values and canonical status mappings." />
              </div>
            </article>

            {/* STAGE 2 */}
            <article 
              id="stage-02" 
              ref={(el) => { stageRefs.current['stage-02'] = el as HTMLDivElement | null; }}
              className="scroll-mt-32 node-milled-border rounded-xl overflow-hidden group"
            >
              <StageHeader file="02_a3_reasoner.ts" authority="UNTRUSTED AI (AUTHORITY: NONE)" isAi />
              <div className="p-6 md:p-8">
                <h3 className="text-2xl font-bold text-white mb-2">Bounded AI Causal Hypothesis Engine</h3>
                <p className="text-zinc-400 text-sm mb-8">The LLM reasons strictly over a bounded evidentiary context to propose a causal hypothesis and a verification intent, but possesses zero authority to execute.</p>
                
                {/* Micro-UI */}
                <div className="bg-[#050505] border border-amber-500/20 rounded-xl overflow-hidden shadow-[inset_0_0_20px_rgba(245,158,11,0.05)] relative mb-6">
                  {/* Warning Strip */}
                  <div className="h-1.5 w-full bg-[repeating-linear-gradient(45deg,#f59e0b,#f59e0b_10px,#000_10px,#000_20px)] opacity-50" />
                  
                  <div className="p-5">
                    <div className="flex items-center justify-between mb-4 pb-4 border-b border-white/[0.06]">
                      <div className="flex items-center gap-2 text-amber-500/80 font-mono text-[10px] uppercase tracking-widest">
                        <Lock className="w-3 h-3" /> READ-ONLY SANDBOX
                      </div>
                      <div className="flex gap-2 text-[10px] font-mono text-zinc-500">
                        <span className="bg-white/[0.04] px-2 py-0.5 rounded">TEMP: 0.0</span>
                        <span className="bg-white/[0.04] px-2 py-0.5 rounded">EVIDENCE: 4 RECS</span>
                      </div>
                    </div>

                    <div className="font-mono text-[12px] space-y-3">
                      <div>
                        <span className="text-zinc-500">system_prompt:</span> <span className="text-amber-200/80">"STRICT_READ_ONLY_ANALYSIS"</span>
                      </div>
                      <div className="text-zinc-300">{"{"}</div>
                      <div className="pl-4">
                        <span className="text-zinc-400">"hypothesis":</span> <span className="text-emerald-300">"Gateway capture lagged merchant cancellation. Order voided while payment succeeded."</span>,
                      </div>
                      <div className="pl-4">
                        <span className="text-zinc-400">"confidence":</span> <span className="text-blue-300">0.94</span>,
                      </div>
                      <div className="pl-4">
                        <span className="text-zinc-400">"proposed_intent":</span> <span className="text-amber-400 bg-amber-500/10 px-1 rounded">"READ_PAYMENT_STATE"</span>
                      </div>
                      <div className="text-zinc-300">{"}"}</div>
                    </div>
                  </div>
                </div>

                <InvariantRule rule="Untrusted AI reasoning can propose hypotheses but cannot mutate financial state or contact external gateways directly." />
              </div>
            </article>

            {/* STAGE 3 */}
            <article 
              id="stage-03" 
              ref={(el) => { stageRefs.current['stage-03'] = el as HTMLDivElement | null; }}
              className="scroll-mt-32 node-milled-border rounded-xl overflow-hidden group"
            >
              <StageHeader file="03_d4_verifier.ts" authority="DETERMINISTIC MACHINE TRUTH" />
              <div className="p-6 md:p-8">
                <h3 className="text-2xl font-bold text-white mb-2">D4 Containment Gate & Provider Ping</h3>
                <p className="text-zinc-400 text-sm mb-8">The determinisic gatekeeper validates that AI intents do not hallucinate evidence, and directly queries ground truth to verify the hypothesis.</p>
                
                {/* Micro-UI */}
                <div className="bg-[#0c0c0e] border border-white/[0.06] rounded-xl p-1 mb-6">
                  <div className="bg-[#050505] rounded-lg p-5 font-mono text-[12px] space-y-4">
                    <div className="flex items-start gap-3">
                      <Terminal className="w-4 h-4 text-zinc-500 mt-0.5 shrink-0" />
                      <div className="w-full">
                        <div className="text-zinc-400 mb-1">$ verify_containment --llm-intent READ_PAYMENT_STATE</div>
                        <div className="text-emerald-400 flex items-center gap-2">
                          <Check className="w-3 h-3" /> 
                          [PASS] Intent schema valid. Evidence IDs strictly contained.
                        </div>
                      </div>
                    </div>
                    <div className="w-full h-px bg-white/[0.06]" />
                    <div className="flex items-start gap-3">
                      <Terminal className="w-4 h-4 text-zinc-500 mt-0.5 shrink-0" />
                      <div className="w-full">
                        <div className="text-zinc-400 mb-1">$ curl -X GET api.razorpay.com/v1/payments/pay_3819482701</div>
                        <div className="text-blue-300 mb-1">HTTP/1.1 200 OK</div>
                        <div className="text-zinc-300">
                          {"{"} <span className="text-zinc-400">"status"</span>: <span className="text-emerald-300">"captured"</span>, <span className="text-zinc-400">"captured"</span>: <span className="text-blue-300">true</span>, <span className="text-zinc-400">"amount"</span>: <span className="text-blue-300">450000</span> {"}"}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <InvariantRule rule="All AI intents must pass strict deterministic schema and containment validation before any external execution is permitted." />
              </div>
            </article>

            {/* STAGE 4 */}
            <article 
              id="stage-04" 
              ref={(el) => { stageRefs.current['stage-04'] = el as HTMLDivElement | null; }}
              className="scroll-mt-32 node-milled-border rounded-xl overflow-hidden group"
            >
              <StageHeader file="04_governance_gate.ts" authority="DETERMINISTIC RULE ENGINE" />
              <div className="p-6 md:p-8">
                <h3 className="text-2xl font-bold text-white mb-2">Autonomous Mutation Authorization</h3>
                <p className="text-zinc-400 text-sm mb-8">Before modifying external state, the policy engine verifies live health metrics, checks monetary budgets, and enforces strict operational rules.</p>
                
                {/* Micro-UI */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
                  <div className="bg-[#050505] border border-white/[0.06] rounded-xl p-4 flex flex-col gap-3 relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-16 h-16 bg-emerald-500/10 blur-2xl rounded-full" />
                    <div className="flex items-center gap-2 text-zinc-400 text-[11px] font-mono uppercase tracking-wider">
                      <Zap className="w-3.5 h-3.5 text-emerald-400" /> Kill Switch
                    </div>
                    <div className="text-white font-medium text-sm flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      SYSTEM_RUNNING
                    </div>
                  </div>
                  
                  <div className="bg-[#050505] border border-white/[0.06] rounded-xl p-4 flex flex-col gap-3">
                    <div className="flex items-center gap-2 text-zinc-400 text-[11px] font-mono uppercase tracking-wider">
                      <Database className="w-3.5 h-3.5 text-blue-400" /> Hourly Budget
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex justify-between text-xs font-mono">
                        <span className="text-white">₹4.5K used</span>
                        <span className="text-zinc-500">₹50K</span>
                      </div>
                      <div className="w-full h-1 bg-white/[0.06] rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500 w-[9%]" />
                      </div>
                    </div>
                  </div>

                  <div className="bg-[#050505] border border-white/[0.06] rounded-xl p-4 flex flex-col gap-3">
                    <div className="flex items-center gap-2 text-zinc-400 text-[11px] font-mono uppercase tracking-wider">
                      <ShieldAlert className="w-3.5 h-3.5 text-purple-400" /> Action Policy
                    </div>
                    <div className="text-white font-mono text-[11px] bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2 py-1 rounded w-fit">
                      ALLOW_AUTO_REFUND
                    </div>
                  </div>
                </div>

                <InvariantRule rule="Mutations are strictly prohibited unless explicit cryptographically verifiable ground-truth evidence justifies the action." />
              </div>
            </article>

            {/* STAGE 5 */}
            <article 
              id="stage-05" 
              ref={(el) => { stageRefs.current['stage-05'] = el as HTMLDivElement | null; }}
              className="scroll-mt-32 node-milled-border rounded-xl overflow-hidden group"
            >
              <StageHeader file="05_occ_actuator.ts" authority="DETERMINISTIC EXECUTION" />
              <div className="p-6 md:p-8">
                <h3 className="text-2xl font-bold text-white mb-2">Version-Locked Side Effects</h3>
                <p className="text-zinc-400 text-sm mb-8">The actuator commits state mutations externally, wrapped in an Optimistic Concurrency Control (OCC) lock and idempotency key to prevent double execution.</p>
                
                {/* Micro-UI */}
                <div className="bg-[#050505] border border-white/[0.06] rounded-xl p-5 font-mono text-[12px] shadow-inner mb-6 space-y-4">
                  <div className="flex items-center justify-between border-b border-white/[0.06] pb-4">
                    <div className="flex items-center gap-3">
                      <div className="bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded text-[10px]">OCC LOCK</div>
                      <div className="text-zinc-400">Target: <span className="text-white">pay_3819482701</span></div>
                    </div>
                    <div className="flex items-center gap-2 text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 text-[10px]">
                      <Lock className="w-3 h-3" /> ACQUIRED
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <div>
                      <div className="text-zinc-500 mb-1">State Version</div>
                      <div className="flex items-center gap-2 text-zinc-300">
                        <span className="bg-white/10 px-1.5 py-0.5 rounded">v1</span>
                        <span className="text-zinc-500">➔</span>
                        <span className="bg-blue-500/20 text-blue-300 border border-blue-500/30 px-1.5 py-0.5 rounded">v2</span>
                      </div>
                    </div>
                    <div>
                      <div className="text-zinc-500 mb-1">Idempotency-Key</div>
                      <div className="text-zinc-300 truncate">idem_pay_3819_rfnd</div>
                    </div>
                  </div>

                  <div className="bg-white/[0.02] border border-white/[0.04] p-3 rounded-lg flex items-center justify-between">
                    <span className="text-zinc-400">Dispatching: <span className="text-emerald-300 font-bold">POST /v1/refunds</span></span>
                    <span className="text-zinc-500 text-[10px]">SHA256: 3a1b4c...</span>
                  </div>
                </div>

                <InvariantRule rule="Duplicate intents must never result in duplicate financial effects. Mutations must be idempotent and strictly version-locked." />
              </div>
            </article>

            {/* STAGE 6 */}
            <article 
              id="stage-06" 
              ref={(el) => { stageRefs.current['stage-06'] = el as HTMLDivElement | null; }}
              className="scroll-mt-32 node-milled-border rounded-xl overflow-hidden group"
            >
              <StageHeader file="06_reobserve.ts" authority="DETERMINISTIC CONVERGENCE" />
              <div className="p-6 md:p-8">
                <h3 className="text-2xl font-bold text-white mb-2">Closed-Loop Post-Mutation Verification</h3>
                <p className="text-zinc-400 text-sm mb-8">The engine refuses to blindly trust that its dispatched mutation worked. It actively re-polls the provider gateway to assert mathematical state convergence.</p>
                
                {/* Micro-UI */}
                <div className="bg-[#050505] border border-white/[0.06] rounded-xl p-5 font-mono text-[11px] shadow-inner mb-6 space-y-3">
                  <div className="flex gap-4">
                    <span className="text-zinc-500 w-16">T+0ms</span>
                    <span className="text-zinc-400">Dispatched mutation to provider gateway.</span>
                  </div>
                  <div className="flex gap-4">
                    <span className="text-zinc-500 w-16">T+100ms</span>
                    <span className="text-zinc-400">Polling provider state... <span className="text-amber-400">PENDING</span></span>
                  </div>
                  <div className="flex gap-4">
                    <span className="text-zinc-500 w-16">T+400ms</span>
                    <span className="text-zinc-400">Polling provider state... <span className="text-blue-400">REFUNDED</span></span>
                  </div>
                  <div className="flex gap-4">
                    <span className="text-zinc-500 w-16">T+450ms</span>
                    <span className="text-zinc-400">Reconciling internal ledger delta... <span className="text-emerald-400 font-bold">₹0.00</span></span>
                  </div>
                  <div className="w-full h-px bg-white/[0.06] my-2" />
                  <div className="flex gap-4 items-center">
                    <span className="text-zinc-500 w-16">Result</span>
                    <span className="text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded border border-emerald-500/20 shadow-[0_0_10px_rgba(52,211,153,0.2)]">STATE_CONVERGED_100%</span>
                  </div>
                </div>

                <InvariantRule rule="A dispatched mutation does not equal a verified outcome. The system must re-observe to prove convergence." />
              </div>
            </article>

            {/* STAGE 7 */}
            <article 
              id="stage-07" 
              ref={(el) => { stageRefs.current['stage-07'] = el as HTMLDivElement | null; }}
              className="scroll-mt-32 node-milled-border rounded-xl overflow-hidden group"
            >
              <StageHeader file="07_terminal_outcome.ts" authority="DUAL-PATH SAFETY GUARANTEE" />
              <div className="p-6 md:p-8">
                <h3 className="text-2xl font-bold text-white mb-2">Autonomous Convergence vs Honest Escalation</h3>
                <p className="text-zinc-400 text-sm mb-8">The final incident outcome. Either successfully remediated without human toil, or safely halted, quarantined, and escalated if any invariant fails.</p>
                
                {/* Micro-UI */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
                  {/* Path A */}
                  <div className="bg-[#050505] border border-white/[0.06] rounded-xl p-5 flex flex-col justify-between relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/10 blur-3xl rounded-full" />
                    <div>
                      <div className="text-[10px] font-mono text-emerald-400 mb-2 uppercase tracking-widest flex items-center gap-2">
                        <CheckCircle2 className="w-3 h-3" /> Path A: Auto-Repair
                      </div>
                      <h4 className="text-white font-medium mb-1">Fully Autonomous Resolution</h4>
                      <p className="text-zinc-500 text-xs">When evidence matches and policy approves, state converges automatically.</p>
                    </div>
                    <div className="mt-6 font-mono text-[10px] text-zinc-400 space-y-1.5">
                      <div className="flex justify-between"><span>Status:</span> <span className="text-emerald-400">RESOLVED</span></div>
                      <div className="flex justify-between"><span>Human Toil:</span> <span className="text-white">0 ms</span></div>
                      <div className="flex justify-between"><span>Cycle Time:</span> <span className="text-white">820 ms</span></div>
                    </div>
                  </div>

                  {/* Path B */}
                  <div className="bg-[#050505] border border-white/[0.06] rounded-xl p-5 flex flex-col justify-between relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-24 h-24 bg-rose-500/10 blur-3xl rounded-full" />
                    <div>
                      <div className="text-[10px] font-mono text-rose-400 mb-2 uppercase tracking-widest flex items-center gap-2">
                        <AlertTriangle className="w-3 h-3" /> Path B: Honest Escalation
                      </div>
                      <h4 className="text-white font-medium mb-1">Quarantine & Escalate</h4>
                      <p className="text-zinc-500 text-xs">If evidence is missing or attacks are caught, the engine safely halts and escalates.</p>
                    </div>
                    <div className="mt-6 font-mono text-[10px] text-zinc-400 space-y-1.5">
                      <div className="flex justify-between"><span>Status:</span> <span className="text-rose-400">ESCALATED</span></div>
                      <div className="flex justify-between"><span>Halluc Risk:</span> <span className="text-emerald-400">0.00%</span></div>
                      <div className="flex justify-between"><span>State Freezed:</span> <span className="text-white">TRUE</span></div>
                    </div>
                  </div>
                  
                  {/* Cryptographic Audit Receipt */}
                  <div className="sm:col-span-2 bg-[#050505] border border-white/[0.06] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded bg-white/[0.04] border border-white/[0.1] flex items-center justify-center shrink-0">
                        <ShieldAlert className="w-4 h-4 text-zinc-300" />
                      </div>
                      <div>
                        <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Cryptographic Audit Seal</div>
                        <div className="text-xs font-mono text-zinc-300 truncate max-w-[200px] sm:max-w-xs">Root: 0x8f7a9d42...c018</div>
                      </div>
                    </div>
                    <div className="text-[10px] font-mono text-zinc-400 bg-white/[0.03] px-3 py-1.5 rounded-full border border-white/[0.05] whitespace-nowrap">
                      Stages Validated: 7/7
                    </div>
                  </div>
                </div>

                <InvariantRule rule="Contradictory evidence, unresolved state, or policy violations must immediately escalate and quarantine the transaction." />
              </div>
            </article>

          </div>
        </div>
      </div>
    </section>
  );
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const StageHeader: React.FC<{ file: string; authority: string; isAi?: boolean }> = ({ file, authority, isAi }) => {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-white/[0.06] bg-[#0c0c0e]">
      {/* Fake window tabs */}
      <div className="flex items-center gap-3 px-4 py-2 sm:border-r border-white/[0.06]">
        <div className="flex gap-1.5 shrink-0">
          <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
        </div>
        <span className="font-mono text-[11px] text-zinc-400 tracking-wider ml-2">{file}</span>
      </div>
      
      {/* Authority Badge */}
      <div className="px-4 py-2 border-t sm:border-t-0 border-white/[0.06]">
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[9px] font-mono tracking-widest uppercase border ${
          isAi 
            ? 'text-amber-400 bg-amber-500/10 border-amber-500/20 shadow-[0_0_10px_rgba(245,158,11,0.2)]'
            : authority.includes('DUAL')
              ? 'text-blue-400 bg-blue-500/10 border-blue-500/20 shadow-[0_0_10px_rgba(59,130,246,0.2)]'
              : 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20 shadow-[0_0_10px_rgba(52,211,153,0.2)]'
        }`}>
          {isAi ? <AlertCircle className="w-3 h-3" /> : <CheckCircle2 className="w-3 h-3" />}
          {authority}
        </span>
      </div>
    </div>
  );
};

const InvariantRule: React.FC<{ rule: string }> = ({ rule }) => (
  <div className="bg-white/[0.02] border-l-2 border-white/20 p-4 rounded-r-lg">
    <div className="text-[10px] font-mono text-zinc-500 mb-1.5 uppercase tracking-widest">Architectural Invariant</div>
    <div className="text-sm font-medium text-zinc-300 leading-relaxed">"{rule}"</div>
  </div>
);
