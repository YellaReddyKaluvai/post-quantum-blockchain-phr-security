import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Save a fetched Blob to the user's machine.
 *
 * Uses a synthetic anchor with `download` rather than `window.open`, because a
 * blob: URL opened in a new tab is treated as a pop-up and is silently blocked
 * by default in Chrome and Safari — the file never reaches the user.
 */
export function saveBlobAsFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  // Revoking immediately can abort the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Open a fetched Blob in a new tab for viewing, falling back to a download. */
export function openBlobInNewTab(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank", "noopener,noreferrer");
  if (!win) {
    // Pop-up blocked — fall back to saving the file so the action never
    // silently does nothing.
    URL.revokeObjectURL(url);
    saveBlobAsFile(blob, filename);
    return;
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
