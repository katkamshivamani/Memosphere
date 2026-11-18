/**
 * MEMOSPHERE Reminders & Routines Client (reminders.js)
 * Manages reminders (Friendly, Calm, Direct tones) and daily routine logs.
 */
const RemindersManager = {
  reminders: [],
  routines: [],

  async loadReminders() {
    try {
      const res = await fetch("/api/reminders");
      const data = await res.json();
      this.reminders = data.reminders || [];
      this.renderReminders();
      return this.reminders;
    } catch (e) {
      console.error("Failed to load reminders:", e);
      return [];
    }
  },

  async loadRoutines() {
    try {
      const res = await fetch("/api/routines");
      const data = await res.json();
      this.routines = data.routines || [];
      this.renderRoutines(data.summary || {});
      return this.routines;
    } catch (e) {
      console.error("Failed to load routines:", e);
      return [];
    }
  },

  renderReminders() {
    const containers = document.querySelectorAll("[data-role='reminders-list']");
    containers.forEach((container) => {
      if (!this.reminders.length) {
        container.innerHTML = `<div class="list-card"><div class="list-card-desc">No reminders scheduled yet.</div></div>`;
        return;
      }
      container.innerHTML = this.reminders
        .map(
          (r) => `
        <div class="list-card" style="${r.completed ? "opacity:0.68;" : ""}">
          <div style="flex:1;">
            <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
              <span class="badge badge-People" style="background:#e0e7ff;color:#3730a3;">${MemoriesManager.escapeHtml(r.reminder_datetime)}</span>
              <span class="badge badge-activities">${MemoriesManager.escapeHtml(r.tone)} Tone</span>
              <span class="badge badge-places">${MemoriesManager.escapeHtml(r.recurrence)}</span>
              <span class="list-card-title" style="${r.completed ? "text-decoration:line-through;" : ""}">${MemoriesManager.escapeHtml(r.title)}</span>
            </div>
            <div class="list-card-desc" style="margin-top:0.35rem;font-style:italic;">
              "${MemoriesManager.escapeHtml(r.notification_message)}"
            </div>
          </div>
          <div style="display:flex;gap:0.4rem;align-items:center;">
            <button class="btn btn-secondary" style="padding:0.4rem 0.75rem;font-size:0.82rem;" onclick="RemindersManager.toggleReminder(${r.id}, ${!r.completed})">
              ${r.completed ? "Undo" : "Done"}
            </button>
            <button class="btn btn-secondary" style="padding:0.4rem 0.75rem;font-size:0.82rem;" onclick="VoiceCompanion.speakText(${JSON.stringify(r.notification_message)})">
              Speak
            </button>
            <button class="btn btn-danger" style="padding:0.4rem 0.75rem;font-size:0.82rem;" onclick="RemindersManager.deleteReminder(${r.id})">
              Delete
            </button>
          </div>
        </div>`
        )
        .join("");
    });
  },

  renderRoutines(summary) {
    const containers = document.querySelectorAll("[data-role='routines-list']");
    containers.forEach((container) => {
      if (!this.routines.length) {
        container.innerHTML = `<div class="list-card"><div class="list-card-desc">No routines configured yet.</div></div>`;
        return;
      }
      container.innerHTML = this.routines
        .map((rt) => {
          const statusColor =
            rt.completion_status === "completed"
              ? "badge-places"
              : rt.completion_status === "missed"
              ? "badge-routines"
              : "badge-items";
          return `
          <div class="list-card">
            <div>
              <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
                <span class="badge ${statusColor}">${MemoriesManager.escapeHtml(rt.completion_status.toUpperCase())}</span>
                <span class="list-card-title">${MemoriesManager.escapeHtml(rt.routine_name)}</span>
              </div>
              <div class="list-card-meta">Scheduled: ${MemoriesManager.escapeHtml(rt.scheduled_time)}</div>
            </div>
            <div style="display:flex;gap:0.4rem;">
              <button class="btn btn-secondary" style="padding:0.4rem 0.75rem;font-size:0.82rem;" onclick="RemindersManager.updateRoutineStatus(${rt.id}, 'completed')">Complete</button>
              <button class="btn btn-danger" style="padding:0.4rem 0.75rem;font-size:0.82rem;" onclick="RemindersManager.updateRoutineStatus(${rt.id}, 'missed')">Missed</button>
            </div>
          </div>`;
        })
        .join("");
    });

    const pctEls = document.querySelectorAll("[data-role='routine-progress-pct']");
    pctEls.forEach((el) => {
      el.textContent = `${summary.completion_rate || 0}%`;
    });
    const barEls = document.querySelectorAll("[data-role='routine-progress-bar']");
    barEls.forEach((el) => {
      el.style.width = `${summary.completion_rate || 0}%`;
    });
  },

  async createReminder(event) {
    if (event) event.preventDefault();
    const title = document.getElementById("rem-title").value.trim();
    const reminder_datetime = document.getElementById("rem-datetime").value.trim();
    const recurrence = document.getElementById("rem-recurrence").value;
    const tone = document.getElementById("rem-tone").value;
    const description = document.getElementById("rem-desc").value.trim();

    if (!title || !reminder_datetime) {
      if (window.MemoToast) window.MemoToast("Please enter a reminder title and time.");
      return;
    }

    const res = await fetch("/api/reminders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, reminder_datetime, recurrence, tone, description }),
    });
    const data = await res.json();
    if (res.ok) {
      if (window.MemoToast) window.MemoToast(data.reminder.notification_message);
      document.getElementById("rem-title").value = "";
      document.getElementById("rem-desc").value = "";
      await this.loadReminders();
      if (window.MemoApp) window.MemoApp.refreshDashboard();
    }
  },

  async toggleReminder(id, completed) {
    await fetch(`/api/reminders/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed }),
    });
    await this.loadReminders();
    if (window.MemoApp) window.MemoApp.refreshDashboard();
  },

  async deleteReminder(id) {
    await fetch(`/api/reminders/${id}`, { method: "DELETE" });
    if (window.MemoToast) window.MemoToast("Reminder removed.");
    await this.loadReminders();
    if (window.MemoApp) window.MemoApp.refreshDashboard();
  },

  async createRoutine(event) {
    if (event) event.preventDefault();
    const routine_name = document.getElementById("routine-name").value.trim();
    const scheduled_time = document.getElementById("routine-time").value.trim() || "09:00 AM";
    if (!routine_name) return;

    const res = await fetch("/api/routines", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ routine_name, scheduled_time, completion_status: "pending" }),
    });
    if (res.ok) {
      document.getElementById("routine-name").value = "";
      if (window.MemoToast) window.MemoToast("Daily routine added!");
      await this.loadRoutines();
      if (window.MemoApp) window.MemoApp.refreshDashboard();
    }
  },

  async updateRoutineStatus(id, completion_status) {
    await fetch(`/api/routines/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completion_status }),
    });
    if (window.MemoToast) window.MemoToast(`Routine marked as ${completion_status}.`);
    await this.loadRoutines();
    if (window.MemoApp) window.MemoApp.refreshDashboard();
  },
};

window.RemindersManager = RemindersManager;
