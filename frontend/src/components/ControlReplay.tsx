import React, { useState } from 'react';
import { api } from '../services/api';
interface ControlReplayProps {
  onEventInjected?: () => void;
}

export const ControlReplay: React.FC<ControlReplayProps> = ({ onEventInjected }) => {
  const [paymentId, setPaymentId] = useState('pay_' + Math.floor(Math.random() * 100000));
  const [orderId, setOrderId] = useState('ord_' + Math.floor(Math.random() * 100000));
  const [amount, setAmount] = useState('4500');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<{message: string, isError: boolean} | null>(null);

  const handleInject = async () => {
    setIsSubmitting(true);
    setResult(null);
    try {
      // Mocking the Razorpay payload structure loosely based on what FCE expects
      const payload = {
        event: "payment.captured",
        payload: {
          payment: {
            entity: {
              id: paymentId,
              order_id: orderId,
              amount: parseInt(amount, 10),
              currency: "INR",
              status: "captured"
            }
          }
        },
        created_at: Math.floor(Date.now() / 1000)
      };

      await api.triggerWebhook(payload);
      setResult({ message: "Webhook injected successfully. FCE pipeline started.", isError: false });
      
      if (onEventInjected) {
        onEventInjected();
      }

      // Auto-generate new IDs for the next run
      setPaymentId('pay_' + Math.floor(Math.random() * 100000));
      setOrderId('ord_' + Math.floor(Math.random() * 100000));
    } catch (err: any) {
      setResult({ message: err.message || "Error injecting webhook.", isError: true });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="control-panel flex flex-col gap-4">
      <h2 className="font-mono text-sm font-semibold uppercase text-fce-textMuted tracking-wider border-b border-slate-700 pb-2">
        Control Replay
      </h2>
      <div className="text-xs text-fce-textMuted font-mono">
        Inject a real provider event into the pipeline to watch the control loop.
      </div>
      
      <div className="grid grid-cols-3 gap-4 font-mono text-xs">
        <div>
          <label className="block text-fce-textMuted mb-1">Payment ID</label>
          <input 
            type="text" 
            value={paymentId} 
            onChange={e => setPaymentId(e.target.value)}
            className="w-full bg-slate-900 border border-slate-700 p-2 text-fce-text focus:outline-none focus:border-fce-accent"
          />
        </div>
        <div>
          <label className="block text-fce-textMuted mb-1">Order ID</label>
          <input 
            type="text" 
            value={orderId} 
            onChange={e => setOrderId(e.target.value)}
            className="w-full bg-slate-900 border border-slate-700 p-2 text-fce-text focus:outline-none focus:border-fce-accent"
          />
        </div>
        <div>
          <label className="block text-fce-textMuted mb-1">Amount</label>
          <input 
            type="text" 
            value={amount} 
            onChange={e => setAmount(e.target.value)}
            className="w-full bg-slate-900 border border-slate-700 p-2 text-fce-text focus:outline-none focus:border-fce-accent"
          />
        </div>
      </div>

      <div className="flex items-center gap-4 mt-2">
        <button 
          onClick={handleInject}
          disabled={isSubmitting}
          className="bg-fce-accent/20 border border-fce-accent text-fce-accent px-4 py-2 font-mono text-xs uppercase tracking-wider hover:bg-fce-accent hover:text-slate-900 transition-colors disabled:opacity-50"
        >
          {isSubmitting ? 'Injecting...' : 'Send Event'}
        </button>
        {result && (
          <span className={`text-xs font-mono ${result.isError ? 'text-fce-danger' : 'text-fce-success'}`}>
            {result.message}
          </span>
        )}
      </div>
    </section>
  );
};
