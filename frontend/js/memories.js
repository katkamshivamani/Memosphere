/**
 * MEMOSPHERE Memory Management Client (memories.js)
 * Handles fetching, searching, filtering by category, creating, editing, and deleting SQLite memories.
 */
const MemoriesManager = {
  allMemories: [],
  activeCategory: "All",
  searchQuery: "",

  async fetchMemories(category = null, query = null) {
    if (category !== null) this.activeCategory = category;
    if (query !== null) this.searchQuery = query;

    const params = new URLSearchParams();
    if (this.activeCategory && this.activeCategory !== "All") {
      params.set("category", this.activeCategory);
    }
    if (this.searchQuery) {
      params.set("q", this.searchQuery);
    }

    try {
      const res = await fetch(`/api/memories?${params.toString()}`);
      const data = await res.json();
      this.allMemories = data.memories || [];
      this.renderMemoriesList();
      return this.allMemories;
    } catch (err) {
      console.error("Failed to fetch memories:", err);
      return [];
    }
  },

  getBadgeClass(category) {
    const map = {
      People: "badge-people",
      Places: "badge-places",
      Items: "badge-items",
      Activities: "badge-activities",
      Routines: "badge-routines",
    };
    return map[category] || "badge-items";
  },

  renderMemoriesList() {
    const container = document.getElementById("memories-list-container");
    if (!container) return;

    if (!this.allMemories.length) {
      container.innerHTML = `
        <div class="list-card">
          <div>
            <div class="list-card-title">No memories found in this filter</div>
            <div class="list-card-desc">Use Brain Dump or the Add Memory form to record a memory.</div>
          </div>
        </div>`;
      return;
    }

    container.innerHTML = this.allMemories
      .map(
        (m) => `
      <div class="list-card" data-memory-id="${m.id}">
        <div style="flex:1;">
          <div style="display:flex;align-items:center;gap:0.55rem;margin-bottom:0.3rem;flex-wrap:wrap;">
            <span class="badge ${this.getBadgeClass(m.category)}">${this.escapeHtml(m.category)}</span>
            <span class="list-card-title" style="margin:0;">${this.escapeHtml(m.title)}</span>
          </div>
          <div class="list-card-desc">${this.escapeHtml(m.content)}</div>
          <div class="list-card-meta">
            ${m.entity_name ? `<span><strong>Entity:</strong> ${this.escapeHtml(m.entity_name)}</span>` : ""}
            ${m.location ? `<span><strong>Location:</strong> ${this.escapeHtml(m.location)}</span>` : ""}
            ${m.event_date ? `<span><strong>Date:</strong> ${this.escapeHtml(m.event_date)}</span>` : ""}
          </div>
        </div>
        <div style="display:flex;gap:0.4rem;">
          <button class="btn btn-secondary" style="padding:0.4rem 0.75rem;font-size:0.82rem;" onclick="MemoriesManager.openEditModal(${m.id})">Edit</button>
          <button class="btn btn-danger" style="padding:0.4rem 0.75rem;font-size:0.82rem;" onclick="MemoriesManager.deleteMemory(${m.id})">Delete</button>
        </div>
      </div>`
      )
      .join("");
  },

  async createMemory(payload) {
    const res = await fetch("/api/memories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      if (window.MemoToast) window.MemoToast(data.message || "Memory saved!");
      await this.fetchMemories();
      if (window.MemoApp) window.MemoApp.refreshDashboard();
    }
    return data;
  },

  async deleteMemory(id) {
    const res = await fetch(`/api/memories/${id}`, { method: "DELETE" });
    if (res.ok) {
      if (window.MemoToast) window.MemoToast("Memory deleted.");
      await this.fetchMemories();
      if (window.MemoApp) window.MemoApp.refreshDashboard();
    }
  },

  openEditModal(id) {
    const mem = this.allMemories.find((m) => m.id === id);
    if (!mem) return;
    const editor = document.getElementById("manual-memory-editor");
    if (!editor) return;
    editor.style.display = "block";
    document.getElementById("edit-memory-id").value = mem.id;
    document.getElementById("edit-memory-category").value = mem.category;
    document.getElementById("edit-memory-title").value = mem.title;
    document.getElementById("edit-memory-content").value = mem.content;
    document.getElementById("edit-memory-entity").value = mem.entity_name || "";
    document.getElementById("edit-memory-location").value = mem.location || "";
    document.getElementById("edit-memory-date").value = mem.event_date || "";
    editor.scrollIntoView({ behavior: "smooth" });
  },

  async saveEditedMemory(event) {
    if (event) event.preventDefault();
    const id = document.getElementById("edit-memory-id").value;
    const payload = {
      category: document.getElementById("edit-memory-category").value,
      title: document.getElementById("edit-memory-title").value,
      content: document.getElementById("edit-memory-content").value,
      entity_name: document.getElementById("edit-memory-entity").value,
      location: document.getElementById("edit-memory-location").value,
      event_date: document.getElementById("edit-memory-date").value,
    };

    const url = id ? `/api/memories/${id}` : "/api/memories";
    const method = id ? "PUT" : "POST";
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      if (window.MemoToast) window.MemoToast(data.message || "Memory saved!");
      document.getElementById("manual-memory-editor").style.display = "none";
      document.getElementById("edit-memory-id").value = "";
      await this.fetchMemories();
      if (window.MemoApp) window.MemoApp.refreshDashboard();
    }
  },

  escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  },
};

window.MemoriesManager = MemoriesManager;
