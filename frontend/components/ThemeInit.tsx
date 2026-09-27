"use client";
import { useEffect } from "react";
import { hydratePalette } from "../lib/palette";

/** Theme bootstrap. Reads the saved choice (or the OS preference once), sets
 *  `data-theme` on <html>, and re-renders if the OS preference changes while
 *  the user hasn't chosen explicitly.
 *
 *  Also adopts the saved *palette* into the palette store. The two are
 *  independent — `data-theme` is the light/dark mode, `data-palette` is the
 *  colour palette, and any combination of the two is valid. */
export default function ThemeInit() {
  useEffect(() => {
    hydratePalette();
    const saved = localStorage.getItem("vantor.theme");
    const apply = (mode: string | null) => {
      const theme = mode ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      document.documentElement.dataset.theme = theme;
    };
    apply(saved);
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (!localStorage.getItem("vantor.theme")) apply(null);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return null;
}

export function toggleTheme(): string {
  const cur = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("vantor.theme", next); } catch { /* ignore */ }
  return next;
}

export function currentTheme(): "light" | "dark" {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}
