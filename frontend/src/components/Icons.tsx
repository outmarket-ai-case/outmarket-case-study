/**
 * Inline SVG icon set.
 *
 * Hand-rolled rather than pulled from an icon package because the page runs
 * under a `default-src 'self'` CSP: no icon CDN, no external font with glyph
 * icons. Inline SVG also means zero extra requests, crisp rendering at any
 * scale, and `currentColor` inheritance so icons follow their surrounding text.
 */

interface IconProps {
  size?: number;
  className?: string;
}

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none" as const,
  stroke: "currentColor" as const,
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: false,
});

/** Wordmark logo: a lightbulb on a board. Uses a gradient, so it needs its own fill. */
export function Logo({ size = 34 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden focusable="false">
      <defs>
        <linearGradient id="ib-logo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill="url(#ib-logo)" />
      <path
        d="M20 10.5a6.4 6.4 0 0 0-3.7 11.6c.5.4.8 1 .8 1.6v.6h5.8v-.6c0-.6.3-1.2.8-1.6A6.4 6.4 0 0 0 20 10.5Z"
        fill="#fff"
        fillOpacity="0.95"
      />
      <path d="M17.4 27.2h5.2M18.2 29.8h3.6" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export const IconBoard = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="3" y="4" width="18" height="16" rx="2.5" />
    <path d="M3 9.5h18M9 9.5V20" />
  </svg>
);

export const IconDocs = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10l1.5 2H19a1 1 0 0 1 1 1v11.5A1.5 1.5 0 0 1 18.5 20h-13A1.5 1.5 0 0 1 4 18.5Z" />
    <path d="M8 12h8M8 15.5h5" />
  </svg>
);

export const IconBulb = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M9.5 17.5h5M10.5 20.5h3" />
    <path d="M12 3.5a5.5 5.5 0 0 0-3.2 9.96c.44.32.7.83.7 1.37v.67h5v-.67c0-.54.26-1.05.7-1.37A5.5 5.5 0 0 0 12 3.5Z" />
  </svg>
);

export const IconCloud = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M7 18.5h9.5a3.5 3.5 0 0 0 .3-6.99A5 5 0 0 0 7.6 9.6 4.45 4.45 0 0 0 7 18.5Z" />
  </svg>
);

export const IconSparkles = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M12 3.5l1.6 4.2 4.2 1.6-4.2 1.6L12 15.1l-1.6-4.2L6.2 9.3l4.2-1.6Z" />
    <path d="M18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7Z" />
  </svg>
);

export const IconClock = ({ size = 14, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.8V12l3 1.9" />
  </svg>
);

export const IconSend = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4.5 12l15-7-7 15-1.8-6.2z" />
  </svg>
);

export const IconAlert = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 8v4.5M12 15.8v.2" />
  </svg>
);

export const IconRefresh = ({ size = 15, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M19.5 12a7.5 7.5 0 1 1-2.4-5.5" />
    <path d="M19.8 4.8v3.9h-3.9" />
  </svg>
);

export const IconLink = ({ size = 14, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M10 13.8a3.4 3.4 0 0 0 4.9.34l2.6-2.6a3.5 3.5 0 0 0-4.95-4.95l-1.1 1.1" />
    <path d="M14 10.2a3.4 3.4 0 0 0-4.9-.34l-2.6 2.6a3.5 3.5 0 0 0 4.95 4.95l1.1-1.1" />
  </svg>
);

export const IconGithub = ({ size = 17, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden focusable="false" className={className}>
    <path d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.53 2.34 1.09 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.56-1.11-4.56-4.95 0-1.09.39-1.99 1.03-2.69-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.03a9.4 9.4 0 0 1 5 0c1.91-1.3 2.75-1.03 2.75-1.03.55 1.38.2 2.4.1 2.65.64.7 1.03 1.6 1.03 2.69 0 3.85-2.34 4.7-4.57 4.94.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A10 10 0 0 0 12 2Z" />
  </svg>
);

export const IconCost = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <ellipse cx="12" cy="6.6" rx="7" ry="2.8" />
    <path d="M5 6.6v4.4c0 1.55 3.13 2.8 7 2.8s7-1.25 7-2.8V6.6" />
    <path d="M5 11v4.4c0 1.55 3.13 2.8 7 2.8s7-1.25 7-2.8V11" />
  </svg>
);

export const IconReliability = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M12 3.5l7 2.6v5.2c0 4.2-2.9 7.3-7 8.7-4.1-1.4-7-4.5-7-8.7V6.1Z" />
    <path d="M8.9 12.1l2.1 2.1 4.1-4.2" />
  </svg>
);

export const IconScale = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 19V9M9.3 19V5M14.7 19v-6.5M20 19v-10" />
    <path d="M3 21h18" />
  </svg>
);

export const IconSecurity = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="4.8" y="10.5" width="14.4" height="9.5" rx="2.2" />
    <path d="M8.4 10.5V7.9a3.6 3.6 0 0 1 7.2 0v2.6" />
    <path d="M12 14.2v2.1" />
  </svg>
);

export const IconFlow = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="5.5" cy="5.5" r="2.1" />
    <circle cx="5.5" cy="18.5" r="2.1" />
    <circle cx="18.5" cy="12" r="2.1" />
    <path d="M7.6 5.5h4.4a2 2 0 0 1 2 2v2.4M7.6 18.5h4.4a2 2 0 0 0 2-2v-2.4" />
    <path d="M16.4 12h-2.4" />
  </svg>
);

export const IconSteps = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M3.5 18.5h5v-4h5v-4h6" />
    <path d="M3.5 14.5v4M8.5 10.5v4M13.5 6.5v4" />
    <circle cx="19.5" cy="10.5" r="1.6" />
  </svg>
);
