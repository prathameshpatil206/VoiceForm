import { PageScanResult } from '../../types/schema';
import { scanPageForms } from './form-scanner';

export interface MutationWatcherOptions {
  debounceMs?: number;
  onUpdate: (result: PageScanResult, detectionLatencyMs: number) => void;
}

export class FormMutationWatcher {
  private observer: MutationObserver | null = null;
  private debounceTimer: number | null = null;
  private debounceMs: number;
  private onUpdate: (result: PageScanResult, latencyMs: number) => void;
  private firstMutationTimestamp: number | null = null;
  private isScanning = false;

  constructor(options: MutationWatcherOptions) {
    this.debounceMs = options.debounceMs ?? 200;
    this.onUpdate = options.onUpdate;
  }

  public start(): void {
    if (this.observer || typeof MutationObserver === 'undefined') return;

    this.observer = new MutationObserver(this.handleMutations.bind(this));
    this.observer.observe(document.body || document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['style', 'class', 'hidden', 'disabled', 'required', 'aria-hidden']
    });
  }

  public stop(): void {
    if (this.debounceTimer !== null) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }
  }

  private handleMutations(mutations: MutationRecord[]): void {
    if (this.isScanning) return;

    // Check if relevant form elements were added, removed, or modified
    let relevant = false;
    for (const mutation of mutations) {
      // Ignore our own debug drawer changes
      if (
        mutation.target instanceof Element &&
        (mutation.target.tagName.toLowerCase() === 'voiceform-debug-drawer' ||
         mutation.target.closest('voiceform-debug-drawer'))
      ) {
        continue;
      }

      if (mutation.type === 'childList') {
        for (const node of Array.from(mutation.addedNodes)) {
          if (isRelevantNode(node)) {
            relevant = true;
            break;
          }
        }
        if (relevant) break;
        for (const node of Array.from(mutation.removedNodes)) {
          if (isRelevantNode(node)) {
            relevant = true;
            break;
          }
        }
        if (relevant) break;
      } else if (mutation.type === 'attributes') {
        if (isRelevantNode(mutation.target)) {
          relevant = true;
          break;
        }
      }
    }

    if (!relevant) return;

    // Stamp the start of this mutation batch to measure reaction latency
    if (this.firstMutationTimestamp === null) {
      this.firstMutationTimestamp = performance.now();
    }

    if (this.debounceTimer !== null) {
      clearTimeout(this.debounceTimer);
    }

    this.debounceTimer = window.setTimeout(() => {
      this.triggerScan();
    }, this.debounceMs);
  }

  private triggerScan(): void {
    const startTime = this.firstMutationTimestamp ?? performance.now();
    this.firstMutationTimestamp = null;
    this.debounceTimer = null;

    this.isScanning = true;
    try {
      const result = scanPageForms();
      const latencyMs = Math.round(performance.now() - startTime);
      this.onUpdate(result, latencyMs);
    } finally {
      this.isScanning = false;
    }
  }
}

function isRelevantNode(node: Node): boolean {
  if (node.nodeType !== Node.ELEMENT_NODE) return false;
  const el = node as Element;

  const tag = el.tagName.toLowerCase();
  if (['form', 'input', 'select', 'textarea', 'label', 'fieldset'].includes(tag)) {
    return true;
  }

  // Check if subtree contains any form controls
  if (el.querySelector && el.querySelector('form, input, select, textarea')) {
    return true;
  }

  return false;
}
