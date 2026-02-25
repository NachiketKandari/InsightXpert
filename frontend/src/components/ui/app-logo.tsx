interface AppLogoProps {
  className?: string;
}

export function AppLogo({ className }: AppLogoProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 512 512"
      className={className}
      aria-hidden="true"
    >
      <rect width="512" height="512" rx="108" fill="#0B1120" />
      <rect x="100" y="312" width="72" height="120" rx="10" fill="#06B6D4" opacity="0.55" />
      <rect x="220" y="216" width="72" height="216" rx="10" fill="#06B6D4" opacity="0.75" />
      <rect x="340" y="120" width="72" height="312" rx="10" fill="#06B6D4" />
      <polyline points="136,312 256,216 376,120" fill="none" stroke="#06B6D4" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="376" cy="120" r="18" fill="#fff" opacity="0.9" />
      <circle cx="376" cy="120" r="10" fill="#06B6D4" />
    </svg>
  );
}
