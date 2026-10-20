import { useEffect } from "react";
import { CloseIcon } from "../icons";
import { useStore } from "../store";

const TOAST_MS = 6000;

// Server errors and "not connected" land here, top center, and clear themselves.
export function Toasts() {
  const errors = useStore((s) => s.errors);
  const dismissErrors = useStore((s) => s.dismissErrors);

  useEffect(() => {
    if (errors.length === 0) return;
    const id = setTimeout(dismissErrors, TOAST_MS);
    return () => clearTimeout(id);
  }, [errors, dismissErrors]);

  if (errors.length === 0) return null;
  return (
    <div
      role="status"
      className="enter fixed top-14 left-1/2 z-40 flex max-w-lg -translate-x-1/2 items-start gap-3 rounded-md border border-blocked/50 bg-rose-950/95 px-3 py-2 text-rose-50 shadow-lg"
    >
      <ul className="flex flex-col gap-0.5 text-xs">
        {errors.map((m, i) => (
          <li key={i}>{m}</li>
        ))}
      </ul>
      <button type="button" className="btn btn-icon" onClick={dismissErrors} aria-label="dismiss">
        <CloseIcon />
      </button>
    </div>
  );
}
