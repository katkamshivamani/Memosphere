/**
 * MEMOSPHERE Web Speech API Integration (voice.js)
 * Provides Speech-to-Text (SpeechRecognition) for Voice Q&A and Brain Dump capture,
 * and Text-to-Speech (speechSynthesis) for patient audio responses.
 */
const VoiceCompanion = {
  recognition: null,
  isListening: false,

  isSupported() {
    return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
  },

  listenIntoInput(inputElement, buttonElement, onCompleteCallback) {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      if (window.MemoToast) {
        window.MemoToast("Voice recognition is not supported in this browser. Using sample voice transcript for demo.");
      }
      if (inputElement && !inputElement.value) {
        inputElement.value = "Where did I keep my charger?";
        if (typeof onCompleteCallback === "function") {
          onCompleteCallback(inputElement.value);
        }
      }
      return;
    }

    if (this.isListening && this.recognition) {
      this.recognition.stop();
      return;
    }

    const rec = new SpeechRec();
    this.recognition = rec;
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      this.isListening = true;
      if (buttonElement) {
        buttonElement.classList.add("listening");
        buttonElement.setAttribute("aria-pressed", "true");
      }
      if (window.MemoToast) {
        window.MemoToast("Listening... Speak clearly now.");
      }
    };

    rec.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      if (inputElement) {
        inputElement.value = transcript;
      }
      if (typeof onCompleteCallback === "function") {
        onCompleteCallback(transcript);
      }
    };

    rec.onerror = () => {
      this.isListening = false;
      if (buttonElement) {
        buttonElement.classList.remove("listening");
      }
    };

    rec.onend = () => {
      this.isListening = false;
      if (buttonElement) {
        buttonElement.classList.remove("listening");
        buttonElement.setAttribute("aria-pressed", "false");
      }
    };

    rec.start();
  },

  speakText(text) {
    if (!("speechSynthesis" in window) || !text) {
      return;
    }
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.95;
      utterance.pitch = 1.0;
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      // Ignore audio block errors before user interaction
    }
  },
};

window.VoiceCompanion = VoiceCompanion;
