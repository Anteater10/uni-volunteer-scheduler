import { useEffect, useState } from "react";

export default function DesktopOnlyBanner() {
  return (
    <div
      role="status"
      className="min-h-[60vh] flex items-center justify-center p-8 text-center"
    >
      <div className="max-w-md">
        <h2 className="text-xl font-semibold mb-3">Please switch to a larger screen</h2>
        <p className="text-gray-600">
          This admin view is designed for screens ≥ 768px — please use a laptop or tablet.
        </p>
      </div>
    </div>
  );
}

export function useIsDesktop(breakpoint = 768) {
  const [isDesktop, setIsDesktop] = useState(
    typeof window === "undefined" ? true : window.innerWidth >= breakpoint,
  );
  useEffect(() => {
    const onResize = () => setIsDesktop(window.innerWidth >= breakpoint);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [breakpoint]);
  return isDesktop;
}
