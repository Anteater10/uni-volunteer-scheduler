// Phase 28 — Organizer QR check-in scanner.
//
// Usage:
//   <QRScanner open={open} onClose={() => setOpen(false)} onCheckedIn={...} />
//
// Flow:
//   1. Modal opens → request camera → stream live video into <video>.
//   2. @zxing/browser decodes QR payloads from the video stream.
//   3. On decode, extract `manage_token` query param from the URL.
//   4. Call api.organizer.lookupByManageToken(token) → resolve signup.
//   5. If not already checked-in: POST /signups/{id}/check-in.
//   6. Toast success + vibrate. Modal stays open for next scan.
//
// Fallbacks:
//   - Camera permission denied: show "Grant camera access in browser
//     settings." error + reveal text-input fallback.
//   - @zxing/browser fails to import: show text-input fallback.
//   - Invalid QR (not a SciTrek manage URL): "Unrecognized QR" + retry.
//   - Already checked in: banner "Already checked in at …", no POST.
//
// The scanner is HTTPS-only in production; localhost dev works because
// Chrome/Edge whitelist http://localhost for getUserMedia.

import React, { useEffect, useRef, useState } from "react";
import { Modal, Button, Input, Label } from "../ui";
import api from "../../lib/api";
import { toast } from "../../state/toast";

function extractManageToken(text) {
  if (!text) return null;
  // Accept bare tokens (>=16 chars, no whitespace, no URL structure) as a
  // convenience — organizers can paste a token directly.
  if (!text.includes("?") && !text.includes("/") && text.length >= 16) {
    return text.trim();
  }
  try {
    // Use window.location.origin as base for relative URLs.
    const url = new URL(text, window.location.origin);
    return url.searchParams.get("manage_token") || url.searchParams.get("token");
  } catch {
    return null;
  }
}

export default function QRScanner({ open, onClose, onCheckedIn }) {
  const videoRef = useRef(null);
  const readerRef = useRef(null);
  const [status, setStatus] = useState("idle"); // idle | scanning | error | camera_denied
  const [errorMsg, setErrorMsg] = useState("");
  const [manualToken, setManualToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState(null);

  // Spin up / tear down zxing on open.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setStatus("idle");
    setErrorMsg("");

    async function start() {
      try {
        const mod = await import("@zxing/browser");
        if (cancelled) return;
        const Reader = mod.BrowserMultiFormatReader || mod.default;
        const reader = new Reader();
        readerRef.current = reader;
        setStatus("scanning");
        await reader.decodeFromVideoDevice(
          undefined,
          videoRef.current,
          (result, err) => {
            if (result) {
              const text =
                typeof result.getText === "function"
                  ? result.getText()
                  : result.text || String(result);
              handleDecoded(text);
            }
            // Decode errors are noisy (NotFoundException fires per frame
            // when no QR is visible) — ignore unless they're a fatal.
          },
        );
      } catch (err) {
        if (cancelled) return;
        const name = err?.name || "";
        if (
          name === "NotAllowedError" ||
          name === "SecurityError" ||
          name === "PermissionDeniedError"
        ) {
          setStatus("camera_denied");
          setErrorMsg(
            "Grant camera access in your browser settings, or paste the magic-link URL below.",
          );
        } else {
          setStatus("error");
          setErrorMsg(
            err?.message || "Scanner failed to start. Use text input below.",
          );
        }
      }
    }

    start();
    return () => {
      cancelled = true;
      const r = readerRef.current;
      try {
        if (r && typeof r.reset === "function") r.reset();
      } catch {
        /* ignore */
      }
      try {
        const stream = videoRef.current?.srcObject;
        if (stream && typeof stream.getTracks === "function") {
          stream.getTracks().forEach((t) => t.stop());
        }
      } catch {
        /* ignore */
      }
      readerRef.current = null;
    };
  }, [open]);

  async function handleDecoded(text) {
    if (busy) return;
    const token = extractManageToken(text);
    if (!token) {
      toast.error("Unrecognized QR. Ask the volunteer for their magic link.");
      return;
    }
    setBusy(true);
    try {
      const info = await api.organizer.lookupByManageToken(token);
      if (
        info.status === "checked_in" ||
        info.status === "attended"
      ) {
        setLastResult({
          ...info,
          already: true,
        });
        toast.info(
          `${info.volunteer_first_name || "Volunteer"} is already checked in.`,
        );
        if (typeof onCheckedIn === "function") onCheckedIn(info);
        return;
      }
      await api.organizer.checkInSignup(info.signup_id);
      try {
        if (typeof navigator !== "undefined" && navigator.vibrate) {
          navigator.vibrate(100);
        }
      } catch {
        /* ignore */
      }
      toast.success(
        `Checked in ${info.volunteer_first_name || ""} ${
          info.volunteer_last_name || ""
        }.`.trim(),
      );
      setLastResult({ ...info, already: false });
      if (typeof onCheckedIn === "function") onCheckedIn(info);
    } catch (err) {
      const status = err?.response?.status;
      if (status === 404) {
        toast.error("QR not recognized. Ask for the magic link.");
      } else if (status === 403) {
        toast.error("Not allowed to check in this signup.");
      } else if (status === 409) {
        toast.info("Already checked in.");
      } else {
        toast.error(err?.message || "Check-in failed");
      }
    } finally {
      setBusy(false);
    }
  }

  function handleManualSubmit(e) {
    e.preventDefault();
    if (!manualToken.trim()) return;
    handleDecoded(manualToken.trim());
    setManualToken("");
  }

  return (
    <Modal open={open} onClose={onClose} title="Scan QR to check in">
      <div className="space-y-3">
        {status !== "camera_denied" && status !== "error" ? (
          <div className="bg-black rounded-lg overflow-hidden aspect-video flex items-center justify-center">
            <video
              ref={videoRef}
              aria-label="QR camera preview"
              playsInline
              className="w-full h-full object-cover"
              data-testid="qr-video"
            />
          </div>
        ) : null}

        {errorMsg ? (
          <p
            className="text-sm text-red-600"
            role="alert"
            data-testid="qr-error"
          >
            {errorMsg}
          </p>
        ) : null}

        <details className="rounded-lg border border-[var(--color-border)] p-2">
          <summary className="cursor-pointer text-sm font-medium">
            Type or paste the magic link
          </summary>
          <form
            onSubmit={handleManualSubmit}
            className="mt-2 space-y-2"
            data-testid="qr-fallback-form"
          >
            <Label htmlFor="qr-manual">Magic link or manage token</Label>
            <Input
              id="qr-manual"
              value={manualToken}
              onChange={(e) => setManualToken(e.target.value)}
              placeholder="https://…/manage?manage_token=…"
            />
            <Button type="submit" disabled={busy || !manualToken.trim()}>
              {busy ? "Checking…" : "Submit"}
            </Button>
          </form>
        </details>

        {lastResult ? (
          <div
            className="rounded-lg bg-[var(--color-bg-muted)] p-3 text-sm"
            data-testid="qr-last-result"
          >
            <strong>
              {lastResult.already ? "Already checked in: " : "Checked in: "}
            </strong>
            {lastResult.volunteer_first_name} {lastResult.volunteer_last_name}
          </div>
        ) : null}

        <div className="flex justify-end">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export { extractManageToken };
