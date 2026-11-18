/**
 * MEMOSPHERE Adaptive Accessibility Manager (accessibility.js)
 * Persists Standard Mode vs Simplified Mode (Large Fonts, High Contrast, Voice-First UI)
 * in browser localStorage.
 */
const AccessibilityManager = {
  STORAGE_KEY: "memosphere_accessibility_mode",
  VOICE_READOUT_KEY: "memosphere_auto_speak",

  init() {
    let savedMode = "standard";
    try {
      savedMode = localStorage.getItem(this.STORAGE_KEY) || "standard";
    } catch (e) {
      savedMode = "standard";
    }
    this.applyMode(savedMode, false);

    const toggleButtons = document.querySelectorAll("[data-action='toggle-accessibility']");
    toggleButtons.forEach((btn) => {
      btn.addEventListener("click", () => this.toggleMode());
    });
  },

  getMode() {
    return document.body.classList.contains("simplified-mode") ? "simplified" : "standard";
  },

  toggleMode() {
    const nextMode = this.getMode() === "standard" ? "simplified" : "standard";
    this.applyMode(nextMode, true);
  },

  applyMode(mode, announce = false) {
    const isSimplified = mode === "simplified";
    if (isSimplified) {
      document.body.classList.add("simplified-mode");
    } else {
      document.body.classList.remove("simplified-mode");
    }

    try {
      localStorage.setItem(this.STORAGE_KEY, isSimplified ? "simplified" : "standard");
    } catch (e) {
      // Ignore storage quota errors
    }

    const labels = document.querySelectorAll("[data-role='accessibility-label']");
    labels.forEach((el) => {
      el.textContent = isSimplified ? "Simplified Mode: ON (Switch to Standard)" : "Simplified Mode (Large Text & Voice)";
    });

    if (announce && window.MemoToast) {
      window.MemoToast(
        isSimplified
          ? "Simplified Accessibility Mode enabled: Large fonts, high contrast, and voice-first controls active."
          : "Standard Dashboard Mode enabled."
      );
    }
  },
};

window.AccessibilityManager = AccessibilityManager;
document.addEventListener("DOMContentLoaded", () => AccessibilityManager.init());
