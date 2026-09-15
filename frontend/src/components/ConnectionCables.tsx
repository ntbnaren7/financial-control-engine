import React from 'react';
import { motion } from 'framer-motion';
import type { NodeCardProps } from './NodeCard';

export interface Connection {
  sourceId: string;
  targetId: string;
  isActive?: boolean;
}

interface ConnectionCablesProps {
  nodes: NodeCardProps[];
  connections: Connection[];
}

export const ConnectionCables: React.FC<ConnectionCablesProps> = ({ nodes, connections }) => {
  // Find node by id to get coordinates
  const getNodeCenter = (id: string, type: 'output' | 'input') => {
    const node = nodes.find(n => n.id === id);
    if (!node) return { x: 0, y: 0 };
    
    const nodeWidth = 256; // w-64 = 16rem = 256px
    const nodeHeight = 104; // approximate height of NodeCard
    
    if (type === 'output') {
      return {
        x: node.x + nodeWidth,
        y: node.y + (nodeHeight / 2)
      };
    } else {
      return {
        x: node.x,
        y: node.y + (nodeHeight / 2)
      };
    }
  };

  return (
    <div className="absolute inset-0 pointer-events-none z-0">
      <svg className="w-full h-full overflow-visible">
        <defs>
          <filter id="cable-glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          
          <linearGradient id="active-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#3B82F6" stopOpacity="0" />
            <stop offset="50%" stopColor="#60A5FA" stopOpacity="1" />
            <stop offset="100%" stopColor="#3B82F6" stopOpacity="0" />
          </linearGradient>
        </defs>

        {connections.map((conn, i) => {
          const source = getNodeCenter(conn.sourceId, 'output');
          const target = getNodeCenter(conn.targetId, 'input');
          
          // Generate smooth cubic bezier curve
          const controlPointX = (target.x - source.x) * 0.5;
          const d = `M ${source.x} ${source.y} C ${source.x + controlPointX} ${source.y}, ${target.x - controlPointX} ${target.y}, ${target.x} ${target.y}`;
          
          return (
            <g key={`${conn.sourceId}-${conn.targetId}-${i}`}>
              {/* Base dark cable */}
              <path
                d={d}
                fill="none"
                stroke="rgba(255,255,255,0.12)"
                strokeWidth={1.5}
              />
              
              {/* Animated pulse layer if active */}
              {conn.isActive && (
                <motion.path
                  d={d}
                  fill="none"
                  stroke="url(#active-grad)"
                  strokeWidth={2}
                  filter="url(#cable-glow)"
                  initial={{ pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: [0, 1], opacity: [0, 1, 0] }}
                  transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    ease: "linear"
                  }}
                />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};
