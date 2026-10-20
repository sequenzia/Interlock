// Inline icons, 16px grid, stroke only. No icon dependency.

interface IconProps {
  className?: string;
}

function Svg({ className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ?? "h-3.5 w-3.5"}
    >
      {children}
    </svg>
  );
}

export function PlayIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M4 2.5v11l9-5.5z" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function PauseIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M4.5 3v10M11.5 3v10" strokeWidth="2.5" />
    </Svg>
  );
}

export function StepIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M3 3v10l7-5z" fill="currentColor" stroke="none" />
      <path d="M12.5 3v10" strokeWidth="2.25" />
    </Svg>
  );
}

export function ResetIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M2.5 8a5.5 5.5 0 1 0 1.6-3.9" />
      <path d="M2.5 2.5v3.5h3.5" />
    </Svg>
  );
}

export function CloseIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M4 4l8 8M12 4l-8 8" />
    </Svg>
  );
}

export function ChevronLeftIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M10 3L5 8l5 5" />
    </Svg>
  );
}

export function ChevronRightIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M6 3l5 5-5 5" />
    </Svg>
  );
}

export function ChevronDownIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M3 6l5 5 5-5" />
    </Svg>
  );
}

export function KeyboardIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="1.5" y="4" width="13" height="8.5" rx="1.5" />
      <path d="M4 7h.01M7 7h.01M10 7h.01M12 7h.01M5 10h6" />
    </Svg>
  );
}

export function ArrowRightIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M3 8h10M9 4l4 4-4 4" />
    </Svg>
  );
}
