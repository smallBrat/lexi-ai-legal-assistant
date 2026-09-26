/**
 * Windows stream hardening for the Next.js dev server.
 *
 * ROOT CAUSE (Phase 13): on Windows + Node 22 + PowerShell,
 * process.stdout / process.stderr can emit EPIPE ("broken pipe, write")
 * when the terminal buffer is momentarily unavailable — e.g. during a
 * Next.js build-output store timer flush. Node's default behaviour
 * propagates the socket-level EPIPE to the stream as an uncaught
 * exception. Next.js's dev-server uncaughtException handler calls
 * console.error(reason), which writes to stdout again and throws ANOTHER
 * EPIPE, re-entering _fatalException and crashing the process in a loop.
 *
 * The fix: attach 'error' event listeners to process.stdout and
 * process.stderr that swallow EPIPE/EIO silently. This is the canonical
 * Node.js recommendation (see
 * https://nodejs.org/api/process.html#a-note-on-process-io). The
 * listeners are additive — they do not remove Next.js's own stream
 * handlers.
 *
 * IMPORTANT: NO node: builtins here (not even dynamic import). Webpack
 * statically traces `import("node:fs")` and the module build fails with
 * UnhandledSchemeError. This module is console-free and file-write-free.
 */

/**
 * Suppress EPIPE errors on a writable stream.
 *
 * EPIPE / EIO are absorbed silently (non-fatal when the terminal pipe is
 * momentarily broken). Any other stream error is re-emitted on process so
 * the framework's own handlers still see it.
 */
function suppressStreamEpipe(stream: NodeJS.WriteStream): void {
  try {
    stream.on("error", (err: NodeJS.ErrnoException) => {
      if (err.code === "EPIPE" || err.code === "EIO") {
        return;
      }
      // Re-emit other errors so the framework's own handlers still fire.
      // Use setImmediate to avoid re-entering the current emit stack.
      setImmediate(() => {
        try {
          process.emit("uncaughtException", err as Error);
        } catch {
          // Never throw from error handling.
        }
      });
    });
  } catch {
    // suppressStreamEpipe must never throw — it runs at register time.
  }
}

export async function register(): Promise<void> {
  try {
    if (process.env.NODE_ENV !== "development") return;
    const flag = globalThis as { __LEXI_INSTRUMENTED__?: boolean };
    if (flag.__LEXI_INSTRUMENTED__) return;
    flag.__LEXI_INSTRUMENTED__ = true;

    suppressStreamEpipe(process.stdout);
    suppressStreamEpipe(process.stderr);
  } catch {
    // Register must never throw.
  }
}
