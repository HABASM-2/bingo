/** Telegram bot invite: `https://t.me/<bot>?start=<referral_code>` */

export function maskReferralCode(code: string): string {
  const trimmed = code.trim();
  if (trimmed.length <= 6) return trimmed;
  return `${trimmed.slice(0, 3)}…${trimmed.slice(-2)}`;
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}

export type ShareInviteResult = "shared" | "copied" | "cancelled" | "failed";

/**
 * Prefer Web Share when available, else copy the invite URL.
 * Falls back to Telegram's share URL if clipboard is blocked.
 */
export async function shareInviteLink(opts: {
  url: string;
  title: string;
  text: string;
}): Promise<ShareInviteResult> {
  const { url, title, text } = opts;
  if (!url) return "failed";

  try {
    if (typeof navigator.share === "function") {
      await navigator.share({ title, text, url });
      return "shared";
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return "cancelled";
    }
  }

  const copied = await copyText(url);
  if (copied) return "copied";

  try {
    const shareUrl =
      `https://t.me/share/url?url=${encodeURIComponent(url)}` +
      `&text=${encodeURIComponent(text)}`;
    window.open(shareUrl, "_blank", "noopener,noreferrer");
    return "shared";
  } catch {
    return "failed";
  }
}
