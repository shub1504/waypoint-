/** Waypoint mark: a location pin on a dashed route, the point where Waypoint steps in. */
export default function Logo({ size = 28 }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="Waypoint">
      <defs><linearGradient id="wpg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#0057b8" /><stop offset="1" stopColor="#00a88f" /></linearGradient></defs>
      <rect width="32" height="32" rx="9" fill="url(#wpg)" />
      <path d="M5.5 25.5c5-1 6.5-4.5 10.5-4.5s5 3 10.5 1.5" fill="none" stroke="#fff" strokeOpacity=".6" strokeWidth="1.8" strokeLinecap="round" strokeDasharray="0.1 3.4" />
      <path d="M16 4.5c-3.800 0-6.500 2.800-6.500 6.300 0 4.500 6.500 10.200 6.500 10.200s6.500-5.700 6.500-10.200c0-3.500-2.700-6.300-6.500-6.300z" fill="#fff" />
      <circle cx="16" cy="10.800" r="2.400" fill="#0b6fb8" />
    </svg>
  );
}
