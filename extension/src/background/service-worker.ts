/**
 * VoiceForm Background Service Worker (Manifest V3)
 * M1 Scope: Minimal lifecycle handler and message router.
 */

chrome.runtime.onInstalled.addListener(() => {
  console.log('[VoiceForm] Extension installed successfully (Milestone 1: Form Scanner)');
});
