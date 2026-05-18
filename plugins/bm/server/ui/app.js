/* bm web ui — vanilla JS. No framework, no build step.
 * Single IIFE; module-scope `state` holds everything. */

(() => {
  "use strict";

  // ---------- state ----------

  const state = {
    data: null,           // { vault, totals, collections, tags, hosts, bookmarks }
    selectedCollection: null,  // null = all
    search: "",
    selectedTags: new Set(),
    viz: "list",
    sidebarCollapsed: localStorage.getItem("bm-sidebar-collapsed") === "1",
  };

  // ---------- elements ----------

  const $ = (id) => document.getElementById(id);
  const els = {
    refresh: $("refresh"),
    search: $("search"),
    totals: $("totals"),
    hierarchy: $("hierarchy"),
    vizTabs: $("viz-tabs"),
    vizPane: $("viz-pane"),
    activeFilters: $("active-filters"),
    list: $("bookmark-list"),
    loading: $("loading"),
    sidebarToggle: $("sidebar-toggle"),
    app: document.querySelector(".app"),
  };

  // Apply persisted sidebar state immediately to avoid layout flash.
  if (state.sidebarCollapsed) els.app.classList.add("sidebar-collapsed");

  // ---------- utils ----------

  const escapeHTML = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

  const setLoading = (on) => els.loading.classList.toggle("show", on);

  const debounce = (fn, ms) => {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  };

  const dateOnly = (s) => (s || "").slice(0, 10);

  // Thumbnail chain: og:image (rich, when captured during enrichment) →
  // favicon (always works for any host) → first-letter glyph (no host at all).
  // All sources are lazy-loaded, no-referrer, browser-cached.
  const thumbnailHTML = (b) => {
    const host = b.host;
    const ogImage = b.og_image;
    if (!host && !ogImage) return `<div class="bm-thumb no-host" aria-hidden="true">·</div>`;
    const faviconSrc = host ? `https://icons.duckduckgo.com/ip3/${encodeURIComponent(host)}.ico` : "";
    const glyph = escapeHTML((host && host[0]) || "·").toUpperCase();
    if (ogImage) {
      // Rich og:image — fill the tile with cover. On error, swap in favicon
      // (and add `favicon-fallback` so CSS can downsize it to a contained icon).
      const ogSrc = escapeHTML(ogImage);
      const fallback = faviconSrc
        ? `this.src='${faviconSrc}';this.classList.add('fallback');this.onerror=function(){this.parentElement.classList.add('no-host');this.outerHTML='${glyph}';};`
        : `this.parentElement.classList.add('no-host');this.outerHTML='${glyph}';`;
      return `<div class="bm-thumb rich">`
        + `<img src="${ogSrc}" alt="" loading="lazy" referrerpolicy="no-referrer" `
        + `onerror="${fallback}" />`
        + `</div>`;
    }
    // Favicon-only path (current default for filed without og_image and all inbox)
    return `<div class="bm-thumb">`
      + `<img src="${faviconSrc}" alt="" loading="lazy" referrerpolicy="no-referrer" `
      + `onerror="this.parentElement.classList.add('no-host');this.outerHTML='${glyph}';" />`
      + `</div>`;
  };

  // ---------- fetch ----------

  async function loadData() {
    setLoading(true);
    try {
      const res = await fetch("/bookmarks.json", { cache: "no-store" });
      if (!res.ok) throw new Error(`bookmarks.json: ${res.status}`);
      state.data = await res.json();
      render();
    } catch (e) {
      els.list.innerHTML = `<div class="empty">error loading data: ${escapeHTML(e.message)}</div>`;
    } finally {
      setLoading(false);
    }
  }

  // ---------- filter ----------

  function filteredBookmarks() {
    if (!state.data) return [];
    const search = state.search.trim().toLowerCase();
    const tagFilter = state.selectedTags;
    const coll = state.selectedCollection;
    return state.data.bookmarks.filter((b) => {
      if (coll && b.collection !== coll) return false;
      if (search) {
        // Title + blurb + URL — URL is critical for inbox items that haven't
        // been enriched yet (often empty title/blurb).
        const hay = (b.title + " " + b.blurb + " " + b.url).toLowerCase();
        if (!hay.includes(search)) return false;
      }
      if (tagFilter.size > 0) {
        for (const t of tagFilter) if (!b.tags.includes(t)) return false;
      }
      return true;
    });
  }

  // ---------- renderers ----------

  function renderTotals() {
    const t = state.data.totals;
    const inboxLine = t.inbox ? `<span>${t.filed} filed · ${t.inbox} inbox</span>` : `<span>${t.bookmarks} bookmarks</span>`;
    els.totals.innerHTML =
      inboxLine +
      `<span>${t.collections} collections</span>` +
      `<span>${t.tags} tags</span>` +
      `<span>${t.hosts} hosts</span>`;
  }

  function renderHierarchy() {
    const colls = state.data.collections;
    const userColls = colls.filter((c) => c.kind === "user");
    const sysColls = colls.filter((c) => c.kind === "system");
    const total = state.data.totals.bookmarks;
    const sel = state.selectedCollection;
    const link = (name, count, klass = "") => {
      const isActive = (sel === name);
      const isAll = (name === null);
      return `<a class="${klass}${isActive ? " active" : ""}" data-coll="${name === null ? "" : escapeHTML(name)}">`
        + `<span>${name === null ? "All bookmarks" : escapeHTML(name)}</span>`
        + `<span class="count">${count}</span></a>`;
    };
    const parts = [];
    parts.push(link(null, total));
    parts.push(`<div class="group-label">Collections</div>`);
    userColls.forEach((c) => parts.push(link(c.name, c.count)));
    if (sysColls.length) {
      parts.push(`<div class="group-label">System</div>`);
      sysColls.forEach((c) => {
        let klass = "system";
        if (c.name === "_broken") klass += " broken";
        if (c.name === "_inbox") klass += " inbox";
        parts.push(link(c.name, c.count, klass));
      });
    }
    els.hierarchy.innerHTML = parts.join("");
  }

  function renderActiveFilters() {
    const chips = [];
    if (state.search) {
      chips.push(`<span class="filter-chip" data-clear="search">search: "${escapeHTML(state.search)}"</span>`);
    }
    for (const t of state.selectedTags) {
      chips.push(`<span class="filter-chip" data-clear-tag="${escapeHTML(t)}">tag: ${escapeHTML(t)}</span>`);
    }
    const n = filteredBookmarks().length;
    const total = state.data.bookmarks.length;
    const scope = state.selectedCollection ? ` in ${state.selectedCollection}/` : "";
    els.activeFilters.innerHTML = `<span>${n} of ${total}${scope}</span>` + chips.join("");
  }

  function renderList() {
    const items = filteredBookmarks();
    if (items.length === 0) {
      els.list.innerHTML = `<div class="empty">no bookmarks match</div>`;
      return;
    }
    // Sort by captured desc
    items.sort((a, b) => (b.captured || "").localeCompare(a.captured || ""));
    const html = items.map((b) => {
      const tags = (b.tags || []).map((t) =>
        `<a class="tag-chip${state.selectedTags.has(t) ? " selected" : ""}" data-tag="${escapeHTML(t)}">${escapeHTML(t)}</a>`
      ).join(" ");
      const isInbox = b.kind === "inbox";
      const inboxBadge = isInbox
        ? `<span class="badge-pending" title="awaiting /bm:enrich">pending${b.source ? " · " + escapeHTML(b.source) : ""}</span>`
        : "";
      const importedColl = isInbox && b.imported_collection
        ? `<span class="imported-coll" title="proposed collection from import">→ ${escapeHTML(b.imported_collection)}</span>`
        : "";
      const needsReview = b.needs_review ? `<span class="needs-review">needs review</span>` : "";
      const statusBroken = b.status === "broken" ? `<span class="status-broken">broken</span>` : "";
      const captured = dateOnly(b.captured);
      const url = escapeHTML(b.url);
      // Title fallback: for inbox without a title, use URL host + path
      const displayTitle = b.title || (isInbox ? (b.host + (b.url ? new URL(b.url).pathname.slice(0, 60) : "")) : b.url);
      return `<article class="bm-card${isInbox ? " inbox" : ""}">
  ${thumbnailHTML(b)}
  <div class="bm-body">
    <div class="bm-title"><a href="${url}" target="_blank" rel="noopener">${escapeHTML(displayTitle)}</a></div>
    <div class="bm-url">${url}</div>
    ${b.blurb ? `<div class="bm-blurb">${escapeHTML(b.blurb)}</div>` : ""}
    <div class="bm-meta">
      <span class="coll" data-coll="${escapeHTML(b.collection)}">${escapeHTML(b.collection)}/</span>
      ${tags}
      ${importedColl}
      ${statusBroken}
      ${needsReview}
      ${inboxBadge}
      <span>${escapeHTML(captured)}</span>
    </div>
  </div>
</article>`;
    }).join("");
    els.list.innerHTML = html;
  }

  // ---------- viz ----------

  function renderViz() {
    const tabs = els.vizTabs.querySelectorAll("button");
    tabs.forEach((b) => b.classList.toggle("active", b.dataset.viz === state.viz));
    if (state.viz === "list") {
      els.vizPane.hidden = true;
      return;
    }
    els.vizPane.hidden = false;
    if (state.viz === "tags") return renderTagCloud();
    if (state.viz === "sizes") return renderSizes();
    if (state.viz === "timeline") return renderTimeline();
    if (state.viz === "hosts") return renderHosts();
  }

  function renderTagCloud() {
    const tags = state.data.tags;
    if (!tags.length) {
      els.vizPane.innerHTML = `<div class="empty">no tags yet</div>`;
      return;
    }
    const max = Math.log(tags[0].count + 1);
    const min = Math.log(tags[tags.length - 1].count + 1);
    const range = Math.max(0.01, max - min);
    const html = tags.map((t) => {
      const norm = (Math.log(t.count + 1) - min) / range;
      const size = 12 + norm * 20;  // 12px..32px
      const sel = state.selectedTags.has(t.name) ? " selected" : "";
      return `<a class="cloud-tag tag-chip${sel}" data-tag="${escapeHTML(t.name)}" `
        + `style="font-size:${size.toFixed(1)}px;padding:2px 8px">`
        + `${escapeHTML(t.name)}<span class="c">${t.count}</span></a>`;
    }).join("");
    els.vizPane.innerHTML = `<div class="tag-cloud">${html}</div>`;
  }

  function renderSizes() {
    const colls = state.data.collections.filter((c) => c.kind === "user" && c.count > 0);
    if (!colls.length) {
      els.vizPane.innerHTML = `<div class="empty">no collections with bookmarks yet</div>`;
      return;
    }
    const max = colls[0].count;
    const html = colls.map((c) => {
      const pct = (c.count / max * 100).toFixed(1);
      return `<div class="size-row" data-coll="${escapeHTML(c.name)}">`
        + `<span class="name">${escapeHTML(c.name)}</span>`
        + `<span class="bar"><span class="bar-fill" style="width:${pct}%"></span></span>`
        + `<span class="count">${c.count}</span>`
        + `</div>`;
    }).join("");
    els.vizPane.innerHTML = `<div class="size-list">${html}</div>`;
  }

  function renderTimeline() {
    const items = state.data.bookmarks.filter((b) => b.captured);
    if (!items.length) {
      els.vizPane.innerHTML = `<div class="empty">no captured dates</div>`;
      return;
    }
    // Compute date range
    const times = items.map((b) => Date.parse(b.captured)).filter((t) => !isNaN(t));
    if (!times.length) {
      els.vizPane.innerHTML = `<div class="empty">no parseable dates</div>`;
      return;
    }
    const min = Math.min(...times);
    const max = Math.max(...times);
    const W = 820, H = 220, padX = 40, padY = 20;
    const innerW = W - padX * 2;
    const innerH = H - padY * 2;
    const xScale = (t) => padX + (innerW * (t - min) / Math.max(1, max - min));
    // Stable y-jitter from hash
    const yJit = (s) => {
      let h = 0;
      for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
      return padY + (Math.abs(h) % 1000) / 1000 * innerH;
    };
    // Axis ticks: ~5
    const ticks = [];
    for (let i = 0; i <= 4; i++) {
      const t = min + (max - min) * i / 4;
      const x = xScale(t);
      const d = new Date(t).toISOString().slice(0, 10);
      ticks.push(`<g class="axis"><line x1="${x}" y1="${padY}" x2="${x}" y2="${H - padY}" stroke-dasharray="2 4"></line>`
        + `<text x="${x}" y="${H - 4}" text-anchor="middle">${d}</text></g>`);
    }
    const dots = items.map((b) => {
      const t = Date.parse(b.captured);
      if (isNaN(t)) return "";
      const x = xScale(t).toFixed(1);
      const y = yJit(b.path || b.url).toFixed(1);
      const title = escapeHTML(`${b.title} — ${dateOnly(b.captured)}`);
      return `<circle cx="${x}" cy="${y}" r="3"><title>${title}</title></circle>`;
    }).join("");
    els.vizPane.innerHTML = `<svg class="timeline" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`
      + ticks.join("") + dots + `</svg>`;
  }

  function renderHosts() {
    const hosts = state.data.hosts.slice(0, 20);
    if (!hosts.length) {
      els.vizPane.innerHTML = `<div class="empty">no hosts</div>`;
      return;
    }
    const html = hosts.map((h) =>
      `<div class="host-row"><span class="host-name">${escapeHTML(h.host)}</span>`
      + `<span class="host-count">${h.count}</span></div>`
    ).join("");
    els.vizPane.innerHTML = `<div class="host-list">${html}</div>`;
  }

  // ---------- master render ----------

  function render() {
    if (!state.data) return;
    renderTotals();
    renderHierarchy();
    renderActiveFilters();
    renderList();
    renderViz();
  }

  // ---------- event wiring ----------

  els.refresh.addEventListener("click", loadData);

  function toggleSidebar(force) {
    const next = (typeof force === "boolean") ? force : !state.sidebarCollapsed;
    state.sidebarCollapsed = next;
    els.app.classList.toggle("sidebar-collapsed", next);
    localStorage.setItem("bm-sidebar-collapsed", next ? "1" : "0");
  }

  els.sidebarToggle.addEventListener("click", () => toggleSidebar());

  // 's' anywhere outside an input also toggles
  document.addEventListener("keydown", (e) => {
    if (e.key === "s" && !e.metaKey && !e.ctrlKey && !e.altKey
        && !(e.target instanceof HTMLInputElement)
        && !(e.target instanceof HTMLTextAreaElement)) {
      toggleSidebar();
    }
  });

  els.search.addEventListener("input", debounce((e) => {
    state.search = e.target.value;
    renderActiveFilters();
    renderList();
  }, 200));

  els.hierarchy.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-coll]");
    if (!a) return;
    e.preventDefault();
    const coll = a.dataset.coll || null;
    state.selectedCollection = coll || null;
    render();
  });

  els.vizTabs.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-viz]");
    if (!b) return;
    state.viz = b.dataset.viz;
    renderViz();
  });

  // Delegate tag-chip + size-row + coll-meta clicks throughout the document
  document.addEventListener("click", (e) => {
    const tagEl = e.target.closest("[data-tag]");
    if (tagEl) {
      const t = tagEl.dataset.tag;
      if (state.selectedTags.has(t)) state.selectedTags.delete(t);
      else state.selectedTags.add(t);
      render();
      return;
    }
    const sizeRow = e.target.closest(".size-row[data-coll]");
    if (sizeRow) {
      state.selectedCollection = sizeRow.dataset.coll;
      state.viz = "list";
      render();
      return;
    }
    const collMeta = e.target.closest(".bm-meta .coll[data-coll]");
    if (collMeta) {
      state.selectedCollection = collMeta.dataset.coll;
      render();
      return;
    }
  });

  els.activeFilters.addEventListener("click", (e) => {
    const clear = e.target.closest("[data-clear]");
    if (clear) {
      state.search = "";
      els.search.value = "";
      renderActiveFilters();
      renderList();
      return;
    }
    const clearTag = e.target.closest("[data-clear-tag]");
    if (clearTag) {
      state.selectedTags.delete(clearTag.dataset.clearTag);
      render();
      return;
    }
  });

  // ---------- boot ----------

  loadData();
})();
