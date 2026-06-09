import React, { useState, useRef, useCallback } from 'react';

interface WikiLayoutProps {
  navigation: React.ReactNode;
  mainContent: React.ReactNode;
  sidebar: React.ReactNode;
  sidebarTitle?: string;
}

export function WikiLayout({ navigation, mainContent, sidebar, sidebarTitle = 'Édition' }: WikiLayoutProps) {
  const [sidebarWidth, setSidebarWidth] = useState(380);
  const [sidebarOpen, setSidebarOpen]   = useState(true);
  const dragging = useRef(false);
  const startX   = useRef(0);
  const startW   = useRef(0);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true;
    startX.current   = e.clientX;
    startW.current   = sidebarWidth;
    document.body.style.cursor    = 'col-resize';
    document.body.style.userSelect = 'none';

    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return;
      const delta = startX.current - ev.clientX;
      setSidebarWidth(Math.max(260, Math.min(600, startW.current + delta)));
    };
    const onUp = () => {
      dragging.current = false;
      document.body.style.cursor    = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [sidebarWidth]);

  return (
    <div className="flex h-full w-full overflow-hidden p-6 gap-6">
      {/* ── Panneau gauche : arbre ── */}
      <aside className="w-[320px] border border-white/10 bg-[#0a0a0a]/80 backdrop-blur-2xl rounded-[2rem] shadow-2xl ring-1 ring-white/5 flex flex-col flex-shrink-0 overflow-hidden relative">
        {navigation}
      </aside>

      {/* ── Zone centrale ── */}
      <main className="flex-1 flex flex-col overflow-hidden bg-transparent min-w-0">
        <div className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar">
          {mainContent}
        </div>
      </main>
    </div>
  );
}
