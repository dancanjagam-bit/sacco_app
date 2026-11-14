import React from "react";

const shapes = {
  home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9M9 20v-6h6v6" /></>,
  wallet: <><rect x="3" y="5" width="18" height="15" rx="2" /><path d="M3 8h16a2 2 0 0 1 2 2v3h-5a2 2 0 0 0 0 4h5" /><path d="M16 15h.01" /></>,
  coins: <><circle cx="8" cy="8" r="5" /><path d="M8 5v6M6 6.5h3M6 9.5h3" /><path d="M13 5.5a5 5 0 1 1-4.5 7.2M13 13h.01" /></>,
  receipt: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
  file: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h5M9 12h6M9 16h6" /></>,
  bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  lock: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 1 1 8 0v3M12 14v3" /></>,
  bus: <><rect x="4" y="3" width="16" height="17" rx="3" /><path d="M4 11h16M8 20v2M16 20v2M8 7h.01M16 7h.01M8 15h2M14 15h2" /></>,
  camera: <><path d="M4 7h3l1.5-2h7L17 7h3a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1Z" /><circle cx="12" cy="13" r="3.5" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19 13.5v-3l-2-.6-.7-1.4 1-1.9-2.2-1.6-1.5 1.4h-1.6L10.5 5 8 6.1l.2 2-1.1 1.2-2-.1-.8 2.6 1.6 1.2v1.6l-1.4 1.3 1.5 2.3 1.9-.6 1.4.7.6 1.8h2.8l.6-1.8 1.4-.7 1.9.6 1.5-2.3-1.4-1.3v-1.6z" /></>,
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="10" cy="7" r="4" /><path d="M20 21v-2a4 4 0 0 0-3-3.9M16 3.2a4 4 0 0 1 0 7.6" /></>,
  truck: <><path d="M3 6h11v12H3zM14 10h4l3 3v5h-7" /><circle cx="7.5" cy="18.5" r="1.5" /><circle cx="17.5" cy="18.5" r="1.5" /></>,
  shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z" /><path d="m9 12 2 2 4-4" /></>,
  logout: <><path d="M10 17l5-5-5-5M15 12H3" /><path d="M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7" /></>,
  menu: <><path d="M4 6h16M4 12h16M4 18h16" /></>,
  close: <><path d="m6 6 12 12M18 6 6 18" /></>,
  arrowRight: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
  download: <><path d="M12 3v12M7 10l5 5 5-5M4 20h16" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 17h.01M12 17h.01" /></>,
  chart: <><path d="M4 19V5M4 19h16" /><path d="m7 15 3-4 3 2 5-7" /></>,
  check: <><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></>,
  alert: <><path d="M10.3 3.9 2.6 17.2A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  filter: <><path d="M4 5h16M7 12h10M10 19h4" /></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5.5 9a7 7 0 0 1 11.8-2L20 12M4 12l2.7 5a7 7 0 0 0 11.8-2" /></>,
  bank: <><path d="m3 9 9-6 9 6M5 10v8M9 10v8M15 10v8M19 10v8M3 21h18M2 18h20" /></>,
  chevron: <><path d="m9 18 6-6-6-6" /></>,
  chevronDown: <><path d="m6 9 6 6 6-6" /></>,
  map: <><path d="M3 7l6-3 6 3 6-3v14l-6 3-6-3-6 3V7z" /><path d="M9 4v14M15 7v14" /></>,
  fuel: <><path d="M3 22V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v7" /><path d="M15 13h2a2 2 0 0 1 2 2v3a1 1 0 0 0 1 1 1 1 0 0 0 1-1v-6l-3-3" /><path d="M7 10H9" /></>,
  wrench: <><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /></>,
  siren: <><path d="M11.5 2a9 9 0 0 0 0 18" /><path d="M13 2.1a9 9 0 0 1 2.9 1.5M20.3 11H22" /><path d="M19.6 7.9A9 9 0 0 1 20.9 11" /><path d="M5 12H3M12 5V3M9 3.6A9 9 0 0 0 7.1 5" /><path d="m17 17-5-5" /><path d="M17 17a2 2 0 1 1-2 2" /></>,
  heart: <><path d="M20 12.5a8 8 0 1 0-16 0c0 3.9 3.1 7.7 8 10 4.9-2.3 8-6.1 8-10z" /></>,
  vote: <><path d="m9 12 2 2 4-4" /><path d="M5 7c0-1.1.9-2 2-2h10a2 2 0 0 1 2 2v12H5V7z" /><path d="M22 19H2" /></>,
  plus: <><path d="M12 5v14M5 12h14" /></>,
  id: <><rect x="2" y="6" width="20" height="13" rx="2" /><circle cx="8" cy="12" r="2" /><path d="M13 11h4M13 15h3" /></>,
  folder: <><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" /></>,
  layers: <><path d="m12 2 10 6-10 6L2 8z" /><path d="m2 14 10 6 10-6" /><path d="m2 10 10 6 10-6" /></>,
  barChart: <><path d="M18 20V10M12 20V4M6 20v-6" /></>,
  eye: <><path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12Z" /><circle cx="12" cy="12" r="2.5" /></>,
  eyeOff: <><path d="m3 3 18 18M10.6 6.2A10.8 10.8 0 0 1 12 6c6.4 0 10 6 10 6a16 16 0 0 1-3.2 3.8M6.2 6.2C3.5 8 2 12 2 12s3.6 6 10 6c1.1 0 2.1-.2 3-.5" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></>,
};

export default function Icon({ name, size = 18, className = "", strokeWidth = 1.8 }) {
  return (
    <svg aria-hidden="true" className={className} width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round"
      strokeLinejoin="round" focusable="false">
      {shapes[name] || shapes.file}
    </svg>
  );
}
