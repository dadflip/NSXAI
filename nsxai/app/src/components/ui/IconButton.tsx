import React from 'react';

interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon: React.ReactNode;
  variant?: 'ghost' | 'solid';
  active?: boolean;
}

export function IconButton({ icon, variant = 'ghost', active, className = '', ...props }: IconButtonProps) {
  const baseClasses = "flex items-center justify-center transition-all duration-200 rounded-lg active:scale-95";
  
  const variants = {
    ghost: "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50",
    solid: "bg-neutral-800 text-neutral-200 hover:bg-neutral-700 hover:text-white"
  };

  const activeClasses = active ? "text-white bg-neutral-800" : "";

  return (
    <button 
      className={`${baseClasses} ${variants[variant]} ${activeClasses} p-1.5 ${className}`}
      {...props}
    >
      {icon}
    </button>
  );
}
