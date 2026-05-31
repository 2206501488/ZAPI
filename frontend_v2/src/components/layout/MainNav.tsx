import { Activity, Images, Settings } from 'lucide-react';
import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

function navClass(isActive: boolean) {
    return [
        'group relative inline-flex h-11 w-11 items-center justify-center rounded-[14px] transition-all duration-200',
        isActive
            ? 'premium-button text-[var(--rail-active-text)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-accent)]'
            : 'premium-icon-button text-[var(--rail-icon-color)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-accent)]',
    ].join(' ');
}

function RailLink({
    to,
    label,
    active,
    children,
}: {
    to: string;
    label: string;
    active: boolean;
    children: ReactNode;
}) {
    return (
        <NavLink to={to} className={navClass(active)} title={label} aria-label={label}>
            {children}
            <span className="pointer-events-none absolute left-[calc(100%+10px)] top-1/2 z-50 -translate-y-1/2 whitespace-nowrap rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-1.5 text-xs text-[var(--text-primary)] opacity-0 shadow-lg backdrop-blur-xl transition-opacity group-hover:opacity-100">
                {label}
            </span>
        </NavLink>
    );
}

function BrandMark() {
    return (
        <div className="relative mb-3 flex h-11 w-11 items-center justify-center rounded-[16px] bg-[var(--rail-logo-bg)] shadow-[var(--rail-logo-shadow)]">
            <div className="absolute inset-px rounded-[15px] bg-[linear-gradient(145deg,rgba(255,255,255,0.16),transparent_42%)] opacity-[var(--rail-logo-mark-opacity)]" />
            <svg viewBox="0 0 42 42" className="absolute h-8 w-8 drop-shadow-[0_3px_8px_rgba(0,0,0,0.28)] opacity-[var(--rail-logo-mark-opacity)]" aria-hidden="true">
                <path
                    d="M13 11h18L14 31h18"
                    fill="none"
                    stroke="white"
                    strokeWidth="4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />
                <circle cx="30" cy="12" r="3.5" fill="#22d3ee" />
                <circle cx="13" cy="30" r="3.5" fill="#ffffff" opacity="0.92" />
            </svg>
            <img src="/proxycanvas.svg" alt="" className="absolute h-8 w-8 opacity-[var(--rail-logo-favicon-opacity)]" draggable={false} />
        </div>
    );
}

export function MainNav() {
    const location = useLocation();
    const inOps = location.pathname.startsWith('/ops');
    const inGallery = location.pathname.startsWith('/gallery') || location.pathname === '/';
    const inSettings = location.pathname.startsWith('/settings');

    return (
        <aside className="glass-panel fixed left-4 top-1/2 z-50 hidden w-[4.25rem] -translate-y-1/2 flex-col items-center rounded-[1.75rem] px-2.5 py-3 md:flex">
            <BrandMark />

            <nav className="flex flex-col items-center gap-2">
                <RailLink to="/gallery" label="画廊" active={inGallery}>
                    <Images className="h-5 w-5" />
                </RailLink>
                <RailLink to="/ops/jobs" label="运行中心" active={inOps}>
                    <Activity className="h-5 w-5" />
                </RailLink>
            </nav>

            <div className="my-3 h-px w-8 bg-[var(--rail-divider)]" />

            <RailLink to="/settings/preferences" label="全局设置" active={inSettings}>
                <Settings className="h-5 w-5" />
            </RailLink>
        </aside>
    );
}
