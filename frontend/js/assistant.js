/**
 * MEMOSPHERE AI Assistant & Brain Dump Client (assistant.js)
 * Handles:
 * 1. Natural Language Memory Q&A (/api/ai/ask) with supporting memory citations and patient repetition handling.
 * 2. Quick Voice & Text Brain Dump (/api/ai/extract) with structured JSON preview, clarification prompts, and manual correction before saving.
 */
const AssistantManager = {
  lastExtracted: null,

  async askQuestion(questionText, speakReply = false) {
    const q = (questionText || "").trim();
    if (!q) {
      if (window.MemoToast) window.MemoToast("Please enter or speak a question first.");
      return;
    }

    const answerBox = document.getElementById("qa-answer-box");
    if (answerBox) {
      answerBox.style.display = "block";
      answerBox.innerHTML = `<div class="list-card-desc">Searching your saved memories...</div>`;
    }

    try {
      const res = await fetch("/api/ai/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (answerBox) {
          answerBox.innerHTML = `<div class="list-card-desc" style="color:#b91c1c;">${data.error || "Unable to process question."}</div>`;
        }
        return;
      }

      const refs = (data.supporting_memories || [])
        .map(
          (m) =>
            `<span class="badge ${MemoriesManager.getBadgeClass(m.category)}" style="margin-right:0.35rem;">Ref #${m.id}: ${MemoriesManager.escapeHtml(m.title)} (${MemoriesManager.escapeHtml(m.location || m.category)})</span>`
        )
        .join("");

      const modeBadge =
        data.source_mode === "external_ai_api"
          ? `<span class="badge badge-people">AI API: ${(data.provider || "").toUpperCase()}</span>`
          : `<span class="badge badge-activities">Privacy Rule-Based Mode</span>`;

      const repeatBadge = data.is_repeated_question
        ? `<span class="badge badge-places" style="margin-left:0.35rem;">Patient Reminder (#${data.repetition_count + 1})</span>`
        : "";

      if (answerBox) {
        answerBox.innerHTML = `
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem;flex-wrap:wrap;gap:0.4rem;">
            <div>${modeBadge}${repeatBadge}</div>
            <button class="btn btn-secondary" style="padding:0.3rem 0.7rem;font-size:0.8rem;" onclick="VoiceCompanion.speakText(${JSON.stringify(data.answer)})">Read Aloud</button>
          </div>
          <div style="font-size:1.1rem;font-weight:700;color:var(--text-primary);margin-bottom:0.55rem;">
            ${MemoriesManager.escapeHtml(data.answer)}
          </div>
          ${refs ? `<div style="margin-top:0.45rem;"><small style="color:var(--text-muted);display:block;margin-bottom:0.25rem;">Supporting Saved Memories:</small>${refs}</div>` : ""}
        `;
      }

      if (speakReply || AccessibilityManager.getMode() === "simplified") {
        VoiceCompanion.speakText(data.answer);
      }
    } catch (err) {
      console.error("Ask error:", err);
    }
  },

  async extractBrainDump(rawText) {
    const text = (rawText || "").trim();
    if (!text) {
      if (window.MemoToast) window.MemoToast("Please enter or speak a memory note first.");
      return;
    }

    const previewCard = document.getElementById("brain-dump-preview");
    if (previewCard) {
      previewCard.style.display = "block";
    }

    try {
      const res = await fetch("/api/ai/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, auto_save: false }),
      });
      const data = await res.json();
      if (!res.ok || !data.extracted) {
        if (window.MemoToast) window.MemoToast(data.error || "Extraction failed.");
        return;
      }

      const ext = data.extracted;
      this.lastExtracted = ext;

      document.getElementById("bd-category").value = ext.category || "Items";
      document.getElementById("bd-title").value = ext.title || "";
      document.getElementById("bd-content").value = ext.content || text;
      document.getElementById("bd-entity").value = ext.entity_name || "";
      document.getElementById("bd-location").value = ext.location || "";
      document.getElementById("bd-date").value = ext.event_date || "";

      const jsonPre = document.getElementById("bd-json-output");
      if (jsonPre) {
        jsonPre.textContent = JSON.stringify(
          {
            category: ext.category,
            title: ext.title,
            content: ext.content,
            entity_name: ext.entity_name,
            location: ext.location,
            event_date: ext.event_date,
          },
          null,
          2
        );
      }

      const clarBox = document.getElementById("bd-clarification-alert");
      if (clarBox) {
        if (ext.needs_clarification && ext.clarification_question) {
          clarBox.style.display = "block";
          clarBox.innerHTML = `<strong>Clarification Helpful:</strong> ${MemoriesManager.escapeHtml(ext.clarification_question)}`;
        } else {
          clarBox.style.display = "none";
        }
      }

      if (window.MemoToast) {
        window.MemoToast("Structured details extracted! Review or edit below before saving.");
      }
    } catch (err) {
      console.error("Brain Dump extraction failed:", err);
    }
  },

  async confirmSaveBrainDump(event) {
    if (event) event.preventDefault();
    const payload = {
      category: document.getElementById("bd-category").value,
      title: document.getElementById("bd-title").value,
      content: document.getElementById("bd-content").value,
      entity_name: document.getElementById("bd-entity").value,
      location: document.getElementById("bd-location").value,
      event_date: document.getElementById("bd-date").value,
      prevent_duplicates: true,
    };

    await MemoriesManager.createMemory(payload);
    const previewCard = document.getElementById("brain-dump-preview");
    if (previewCard) previewCard.style.display = "none";
    const input = document.getElementById("brain-dump-input");
    if (input) input.value = "";
  },
};

window.AssistantManager = AssistantManager;
