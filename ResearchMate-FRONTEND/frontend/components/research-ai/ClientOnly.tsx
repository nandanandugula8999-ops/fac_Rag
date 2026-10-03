'use client';
import { useEffect, useState } from 'react';

// Renders children only after client mount, so SSR HTML matches the server
// output (nothing) and browser-only values (dates, query params) never
// diverge during hydration.
export default function ClientOnly({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;
  return <>{children}</>;
}
