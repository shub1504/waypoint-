const P = {
  home: <path d="M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />,
  compass: <><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5z" /></>,
  chat: <path d="M4 5h16v11H9l-5 4z" />,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21c1-4 4-6 8-6s7 2 8 6" /></>,
  plane: <path d="M2 16 22 7l-8 15-2.5-6.5z" />,
  bed: <><path d="M3 19V7M3 14h18v5M21 14v-2a3 3 0 0 0-3-3h-7v5" /><circle cx="7" cy="11" r="1.6" /></>,
  train: <><rect x="5" y="3" width="14" height="14" rx="3" /><path d="M5 11h14M9 21l2-4M15 21l-2-4" /></>,
  bus: <><rect x="4" y="4" width="16" height="13" rx="2" /><path d="M4 11h16M7 20v-3M17 20v-3" /></>,
  check: <path d="m5 12 5 5 9-10" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  table: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M3 15h18M9 4v16" /></>,
  flask: <path d="M9 3h6M10 3v6L5 19a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-10V3" />,
  sliders: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></>,
  pin: <><path d="M12 21s7-6 7-11a7 7 0 0 0-14 0c0 5 7 11 7 11z" /><circle cx="12" cy="10" r="2.5" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  grid: <><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></>,
  archive: <><rect x="3" y="4" width="18" height="5" rx="1" /><path d="M5 9v10h14V9M10 13h4" /></>,
  send: <path d="M3 11 21 3l-8 18-2-8z" />,
  chevron: <path d="m9 6 6 6-6 6" />,
  back: <path d="m15 6-6 6 6 6" />,
  wallet: <><rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M16 14h2" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  swap: <path d="M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  chart: <path d="M5 20V11M12 20V4M19 20v-6" />,
  arrow: <path d="M7 17 17 7M8 7h9v9" />,
};

export function Icon({ name, size = 22, fill = false }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={fill ? "currentColor" : "none"} stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {P[name]}
    </svg>
  );
}