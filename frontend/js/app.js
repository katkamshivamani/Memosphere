/**
 * MEMOSPHERE Core Dashboard Controller (app.js)
 * Coordinates sidebar view navigation, global memory search, dashboard metrics,
 * toast alerts, and AI provider status badge.
 */
window.MemoToast = function (message) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3800);
};

const MemoApp = {
  currentSection: "dashboard",

  async init() {
    this.bindNavigation();
    await this.refreshDashboard();
    await MemoriesManager.fetchMemories();
    await RemindersManager.loadReminders();
    await RemindersManager.loadRoutines();
    await this.loadAIStatusBadge();

    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  },

  bindNavigation() {
    const navButtons = document.querySelectorAll("[data-section]");
    navButtons.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const target = btn.getAttribute("data-section");
        if (!target) return;
        e.preventDefault();
        this.switchSection(target, btn.getAttribute("data-category-filter"));
      });
    });

    const searchInput = document.getElementById("global-memory-search");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        const val = e.target.value;
        MemoriesManager.fetchMemories(null, val);
      });
    }
  },

  switchSection(sectionName, categoryFilter = null) {
    this.currentSection = sectionName;
    document.querySelectorAll(".nav-item[data-section]").forEach((btn) => {
      const matches =
        btn.getAttribute("data-section") === sectionName &&
        (!categoryFilter || btn.getAttribute("data-category-filter") === categoryFilter);
      btn.classList.toggle("active", Boolean(matches));
    });

    document.querySelectorAll(".view-section").forEach((sec) => {
      sec.style.display = sec.id === `section-${sectionName}` ? "block" : "none";
    });

    if (categoryFilter) {
      const catTitle = document.getElementById("memories-section-heading");
      if (catTitle) {
        catTitle.textContent = categoryFilter === "All" ? "All Saved Memories" : `${categoryFilter} Memories`;
      }
      if (categoryFilter === "PlacesItems") {
        MemoriesManager.fetchMemories("Items", "");
      } else {
        MemoriesManager.fetchMemories(categoryFilter, "");
      }
    }
  },

  async refreshDashboard() {
    try {
      const res = await fetch("/api/dashboard/stats");
      const stats = await res.json();

      const setTxt = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      };

      setTxt("stat-total-memories", stats.total_memories || 0);
      setTxt("stat-people-count", (stats.category_counts && stats.category_counts.People) || 0);
      setTxt(
        "stat-items-places-count",
        ((stats.category_counts && stats.category_counts.Items) || 0) +
          ((stats.category_counts && stats.category_counts.Places) || 0)
      );
      setTxt("stat-reminders-count", stats.upcoming_reminders_count || 0);
      setTxt("stat-routine-pct", `${stats.routine_progress_percent || 0}%`);

      const progBar = document.getElementById("dashboard-routine-bar");
      if (progBar) progBar.style.width = `${stats.routine_progress_percent || 0}%`;

      const recentContainer = document.getElementById("dashboard-recent-memories");
      if (recentContainer && stats.recent_memories) {
        recentContainer.innerHTML = stats.recent_memories
          .slice(0, 4)
          .map(
            (m) => `
          <div class="list-card">
            <div>
              <span class="badge ${MemoriesManager.getBadgeClass(m.category)}">${MemoriesManager.escapeHtml(m.category)}</span>
              <div class="list-card-title" style="margin-top:0.25rem;">${MemoriesManager.escapeHtml(m.title)}</div>
              <div class="list-card-desc">${MemoriesManager.escapeHtml(m.content)}</div>
            </div>
          </div>`
          )
          .join("");
      }
    } catch (e) {
      console.error("Dashboard stats error:", e);
    }
  },

  async loadAIStatusBadge() {
    try {
      const res = await fetch("/api/ai/status");
      const data = await res.json();
      const badge = document.getElementById("ai-status-pill");
      if (badge) {
        if (data.api_key_configured) {
          badge.textContent = `AI: ${(data.selected_provider || "groq").toUpperCase()} Connected`;
          badge.className = "badge badge-places";
        } else {
          badge.textContent = `AI: ${(data.selected_provider || "groq").toUpperCase()} (Local Fallback Active)`;
          badge.className = "badge badge-items";
        }
      }
    } catch (e) {
      // Ignore
    }
  },
};

window.MemoApp = MemoApp;
document.addEventListener("DOMContentLoaded", () => MemoApp.init());
