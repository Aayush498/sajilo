"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

/**
 * One modal shell for the whole app, built on Radix.
 *
 * The hand-rolled dialogs it replaces were a div with a click-outside
 * handler. That looks the same and behaves nothing like a dialog: focus
 * stayed on the page behind, Tab walked out of the modal, Escape did
 * nothing, the background scrolled, and screen readers were never told a
 * dialog had opened. Radix gives all of that, so the app gets it once
 * rather than four times, imperfectly.
 *
 * `dismissable={false}` is for prompts the user must answer — the profile
 * gate — where Escape and click-outside are deliberately disabled.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  dismissable = true,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  dismissable?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && dismissable && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm data-[state=open]:animate-[fade_.15s_ease-out]" />
        <Dialog.Content
          className="card fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 p-6 shadow-2xl data-[state=open]:animate-[rise_.2s_ease-out]"
          onEscapeKeyDown={(e) => !dismissable && e.preventDefault()}
          onPointerDownOutside={(e) => !dismissable && e.preventDefault()}
          onInteractOutside={(e) => !dismissable && e.preventDefault()}
        >
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="text-lg font-bold">{title}</Dialog.Title>
            {dismissable && (
              <Dialog.Close
                className="muted -mr-1 -mt-1 rounded-lg p-1.5 transition-colors hover:bg-slate-100 dark:hover:bg-slate-800"
                aria-label="Close"
              >
                <X size={16} />
              </Dialog.Close>
            )}
          </div>

          {/* Radix warns when a dialog has no description, so always render
              the element and hide it when there is nothing to say. */}
          <Dialog.Description className={description ? "muted mt-1 text-sm" : "sr-only"}>
            {description ?? title}
          </Dialog.Description>

          <div className="mt-5 space-y-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
