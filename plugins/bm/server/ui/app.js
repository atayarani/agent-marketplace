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
    // Set of parent-collection paths whose nested children are currently
    // hidden. Default = empty (everything expanded). Toggle persists.
    collapsedColls: new Set(
      (localStorage.getItem("bm-collapsed-colls") || "")
        .split(",").map((s) => s.trim()).filter(Boolean)
    ),
    // "count" (default, biggest first) or "alpha" (a-z by leaf name).
    // Applies recursively to every level of the collection tree.
    collectionSort: localStorage.getItem("bm-coll-sort") === "alpha" ? "alpha" : "count",
    // "desc" or "asc". Defaults: count→desc (biggest first), alpha→asc (a-z).
    // Click the active field to flip; the chosen direction is remembered per
    // session so flipping count→asc then switching to alpha applies the
    // alpha default direction (not "asc" from count).
    collectionSortDir: localStorage.getItem("bm-coll-sort-dir") === "asc" ? "asc" : "desc",
  };

  function persistCollapsedColls() {
    localStorage.setItem("bm-collapsed-colls", Array.from(state.collapsedColls).join(","));
  }

  // Comparator for collection-tree nodes. "alpha" sorts by leaf name (the
  // segment after the last `/`), so depth-2 children alphabetize among their
  // siblings rather than against the whole path. Direction flips the result.
  function collComparator() {
    const flip = state.collectionSortDir === "asc" ? 1 : -1;
    if (state.collectionSort === "alpha") {
      // For alpha, "asc" = a-z (natural). Flip swaps to z-a.
      return (a, b) => {
        const al = a.name.split("/").pop().toLowerCase();
        const bl = b.name.split("/").pop().toLowerCase();
        const c = al.localeCompare(bl);
        return state.collectionSortDir === "asc" ? c : -c;
      };
    }
    // count: "desc" = biggest first (default). Name is the tiebreaker.
    return (a, b) => {
      const c = b.count - a.count;
      return (c !== 0 ? c : a.name.localeCompare(b.name)) * (state.collectionSortDir === "desc" ? 1 : -1);
    };
  }

  function renderSortToggle() {
    // Active button shows a direction arrow; click active to flip, click
    // inactive to switch field at that field's default direction.
    const arrow = (val) => {
      if (state.collectionSort !== val) return "";
      return state.collectionSortDir === "desc" ? " ↓" : " ↑";
    };
    const opt = (val, label) =>
      `<button data-sort="${val}" class="${state.collectionSort === val ? "active" : ""}" `
      + `aria-pressed="${state.collectionSort === val ? "true" : "false"}" `
      + `title="${state.collectionSort === val ? 'click to flip direction' : `sort by ${label}`}">${label}${arrow(val)}</button>`;
    els.sortToggle.innerHTML =
      `<span class="sort-label">Sort:</span>${opt("count", "count")}${opt("alpha", "a–z")}`;
  }

  // ---------- elements ----------

  const $ = (id) => document.getElementById(id);
  const els = {
    refresh: $("refresh"),
    search: $("search"),
    totals: $("totals"),
    sortToggle: $("sort-toggle"),
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

  // Thumbnail chain:
  //   filed + og:image  → og:image (rich, captured during enrichment)
  //   filed (no og)     → microlink screenshot (free 50/day per IP, no API key)
  //   inbox / no host   → favicon (cheap, instant, always works)
  //   anything missing  → first-letter glyph
  // All sources are lazy-loaded, no-referrer, browser-cached.
  // The chain is implemented via cascading `onerror` handlers; if microlink
  // rate-limits or the og:image 404s, the img reloads itself with the favicon.
  const thumbnailHTML = (b) => {
    const host = b.host;
    const ogImage = b.og_image;
    if (!host && !ogImage) return `<div class="bm-thumb no-host" aria-hidden="true">·</div>`;
    const faviconSrc = host ? `https://icons.duckduckgo.com/ip3/${encodeURIComponent(host)}.ico` : "";
    const glyph = escapeHTML((host && host[0]) || "·").toUpperCase();
    // Build a fallback handler that drops to favicon (and from there to glyph)
    const faviconFallback = faviconSrc
      ? `this.src='${faviconSrc}';this.classList.add('fallback');this.onerror=function(){this.parentElement.classList.add('no-host');this.outerHTML='${glyph}';};`
      : `this.parentElement.classList.add('no-host');this.outerHTML='${glyph}';`;

    if (ogImage) {
      const ogSrc = escapeHTML(ogImage);
      return `<div class="bm-thumb rich">`
        + `<img src="${ogSrc}" alt="" loading="lazy" referrerpolicy="no-referrer" `
        + `onerror="${faviconFallback}" />`
        + `</div>`;
    }

    // Filed bookmarks without og:image → microlink screenshot tier.
    // Inbox stays on favicon (un-enriched; also keeps us under microlink's
    // 50/day quota since the bulk of items are inbox).
    if (b.kind === "filed" && b.url) {
      const microlinkSrc = `https://api.microlink.io/?url=${encodeURIComponent(b.url)}&screenshot=true&embed=screenshot.url`;
      return `<div class="bm-thumb rich">`
        + `<img src="${microlinkSrc}" alt="" loading="lazy" referrerpolicy="no-referrer" `
        + `onerror="${faviconFallback}" />`
        + `</div>`;
    }

    // Inbox + filed-without-host → favicon directly
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
      // Trash is excluded from "All bookmarks" — only visible when _trash is
      // explicitly selected. Deleted things shouldn't pollute the active view.
      if (coll === null && b.kind === "trash") return false;
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
    const counts = [];
    if (t.inbox || t.trashed) {
      const parts = [`${t.filed} filed`];
      if (t.inbox)   parts.push(`${t.inbox} inbox`);
      if (t.trashed) parts.push(`${t.trashed} trashed`);
      counts.push(`<span>${parts.join(" · ")}</span>`);
    } else {
      counts.push(`<span>${t.bookmarks} bookmarks</span>`);
    }
    counts.push(`<span>${t.collections} collections</span>`);
    counts.push(`<span>${t.tags} tags</span>`);
    counts.push(`<span>${t.hosts} hosts</span>`);
    els.totals.innerHTML = counts.join("");
  }

  function renderHierarchy() {
    const colls = state.data.collections;
    const userColls = colls.filter((c) => c.kind === "user");
    const sysColls = colls.filter((c) => c.kind === "system");
    const total = state.data.totals.bookmarks;   // already excludes trash
    const sel = state.selectedCollection;

    // Build a tree from the flat collection list. A node is `<parent>/<leaf>`
    // when parent is also a known user collection — otherwise it's a root.
    // Skip "orphan" nests (`a/b/` with no `a/` collection) — they fall back
    // to being roots so they still render somewhere.
    const userNames = new Set(userColls.map((c) => c.name));
    const byName = {};
    for (const c of userColls) byName[c.name] = { name: c.name, count: c.count, children: [] };
    const roots = [];
    for (const c of userColls) {
      const slash = c.name.lastIndexOf("/");
      const parent = (slash > 0 && userNames.has(c.name.slice(0, slash))) ? c.name.slice(0, slash) : null;
      if (parent) byName[parent].children.push(byName[c.name]);
      else roots.push(byName[c.name]);
    }

    // Recursive descendant-sum for the roll-up pill on collapsed parents.
    function sumDescendants(node) {
      let s = 0;
      for (const c of node.children) s += c.count + sumDescendants(c);
      return s;
    }

    // Emit one node + (when expanded) its subtree, indented by depth via a
    // CSS custom property so arbitrary depth styles consistently.
    function emit(node, depth, out) {
      const hasKids = node.children.length > 0;
      const collapsed = hasKids && state.collapsedColls.has(node.name);
      const rolled = hasKids ? sumDescendants(node) : 0;
      const extra = rolled > 0
        ? `<span class="nested-roll" title="${rolled} more in nested collections">+${rolled}</span>`
        : "";
      const disc = hasKids
        ? `<span class="disclosure" data-toggle-coll="${escapeHTML(node.name)}" role="button" aria-label="${collapsed ? 'expand' : 'collapse'} ${escapeHTML(node.name)}/" aria-expanded="${collapsed ? 'false' : 'true'}">${collapsed ? '▸' : '▾'}</span>`
        : "";
      const isActive = sel === node.name;
      if (depth === 0) {
        // Top-level: full name, no tree glyph. Has-children → disclosure.
        const kls = hasKids ? "has-children" : "";
        out.push(
          `<a class="${kls}${isActive ? " active" : ""}" data-coll="${escapeHTML(node.name)}">`
          + `<span class="label">${disc}${escapeHTML(node.name)}</span>`
          + `<span class="count">${node.count}${extra}</span></a>`
        );
      } else {
        // Nested at any depth: leaf-only label, indent via --depth, tree
        // glyph only when there's no disclosure (else the disclosure carries
        // the visual cue for "node in tree").
        const leaf = node.name.split("/").pop();
        const tg = hasKids ? "" : `<span class="tree-glyph" aria-hidden="true">└</span>`;
        const kls = "nested" + (hasKids ? " has-children" : "");
        out.push(
          `<a class="${kls}${isActive ? " active" : ""}" data-coll="${escapeHTML(node.name)}" title="${escapeHTML(node.name)}/" style="--depth: ${depth};">`
          + `<span class="label">${tg}${disc}${escapeHTML(leaf)}</span>`
          + `<span class="count">${node.count}${extra}</span></a>`
        );
      }
      if (hasKids && !collapsed) {
        const sorted = [...node.children].sort(cmp);
        for (const c of sorted) emit(c, depth + 1, out);
      }
    }

    // Single comparator shared between roots and all descendant levels.
    const cmp = collComparator();

    const parts = [];
    parts.push(
      `<a class="${sel === null ? "active" : ""}" data-coll="">`
      + `<span class="label">All bookmarks</span>`
      + `<span class="count">${total}</span></a>`
    );
    parts.push(`<div class="group-label">Collections</div>`);
    const sortedRoots = [...roots].sort(cmp);
    for (const root of sortedRoots) emit(root, 0, parts);
    if (sysColls.length) {
      parts.push(`<div class="group-label">System</div>`);
      for (const c of sysColls) {
        let klass = "system";
        if (c.name === "_broken") klass += " broken";
        if (c.name === "_inbox") klass += " inbox";
        if (c.name === "_trash") klass += " trash";
        const isActive = sel === c.name;
        parts.push(
          `<a class="${klass}${isActive ? " active" : ""}" data-coll="${escapeHTML(c.name)}">`
          + `<span class="label">${escapeHTML(c.name)}</span>`
          + `<span class="count">${c.count}</span></a>`
        );
      }
    }
    els.hierarchy.innerHTML = parts.join("");
  }

  // Render a collection path for the bookmark-card meta chip: nested paths
  // get the parent dimmed and the leaf full-strength, so the structure reads
  // at a glance even before you click into it.
  function renderCollChip(collection) {
    const parts = (collection || "").split("/");
    if (parts.length <= 1) return escapeHTML(collection || "");
    const parent = parts.slice(0, -1).join("/");
    const leaf = parts[parts.length - 1];
    return `<span class="coll-parent">${escapeHTML(parent)}/</span>${escapeHTML(leaf)}`;
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
    const emptyTrashBtn = state.selectedCollection === "_trash" && (state.data.totals.trashed || 0) > 0
      ? `<button id="empty-trash-btn" class="danger-btn" title="Permanently delete all items in _trash">Empty trash (${state.data.totals.trashed})</button>`
      : "";
    els.activeFilters.innerHTML = `<span>${n} of ${total}${scope}</span>` + chips.join("") + emptyTrashBtn;
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
      const isTrash = b.kind === "trash";
      const inboxBadge = isInbox
        ? `<span class="badge-pending" title="awaiting /bm:enrich">pending${b.source ? " · " + escapeHTML(b.source) : ""}</span>`
        : "";
      const trashBadge = isTrash
        ? `<span class="badge-trashed" title="${escapeHTML('from ' + (b.trashed_from || 'unknown'))}">trashed${b.trashed_from ? " · from " + escapeHTML(b.trashed_from) : ""}</span>`
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
      const actionButton = isTrash
        ? `<button class="bm-restore" data-path="${escapeHTML(b.path || '')}" title="Restore${b.trashed_from ? ' to ' + b.trashed_from : ' to _unsorted'}" aria-label="Restore">↶</button>`
        : `<button class="bm-delete" data-path="${escapeHTML(b.path || '')}" title="Move to _trash" aria-label="Move to _trash">×</button>`;
      return `<article class="bm-card${isInbox ? " inbox" : ""}${isTrash ? " trash" : ""}">
  ${thumbnailHTML(b)}
  <div class="bm-body">
    <div class="bm-title"><a href="${url}" target="_blank" rel="noopener">${escapeHTML(displayTitle)}</a></div>
    <div class="bm-url">${url}</div>
    ${b.blurb ? `<div class="bm-blurb">${escapeHTML(b.blurb)}</div>` : ""}
    <div class="bm-meta">
      <span class="coll" data-coll="${escapeHTML(b.collection)}">${renderCollChip(b.collection)}/</span>
      ${tags}
      ${importedColl}
      ${statusBroken}
      ${needsReview}
      ${inboxBadge}
      ${trashBadge}
      <span>${escapeHTML(captured)}</span>
    </div>
  </div>
  ${actionButton}
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
    const userNames = new Set(colls.map((c) => c.name));
    const html = colls.map((c) => {
      const pct = (c.count / max * 100).toFixed(1);
      const slash = c.name.lastIndexOf("/");
      const isNested = slash > 0 && userNames.has(c.name.slice(0, slash));
      const label = isNested
        ? `<span class="coll-parent">${escapeHTML(c.name.slice(0, slash + 1))}</span>${escapeHTML(c.name.slice(slash + 1))}`
        : escapeHTML(c.name);
      return `<div class="size-row${isNested ? " nested" : ""}" data-coll="${escapeHTML(c.name)}">`
        + `<span class="name">${label}</span>`
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
    renderSortToggle();
    renderHierarchy();
    renderActiveFilters();
    renderList();
    renderViz();
  }

  // ---------- event wiring ----------

  els.refresh.addEventListener("click", loadData);

  els.sortToggle.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-sort]");
    if (!btn) return;
    const next = btn.dataset.sort;
    if (next !== "count" && next !== "alpha") return;
    if (state.collectionSort === next) {
      // Clicking the active field flips the direction.
      state.collectionSortDir = state.collectionSortDir === "desc" ? "asc" : "desc";
    } else {
      // Switching field: pick that field's natural default direction.
      // count → desc (biggest first); alpha → asc (a-z).
      state.collectionSort = next;
      state.collectionSortDir = next === "count" ? "desc" : "asc";
    }
    localStorage.setItem("bm-coll-sort", state.collectionSort);
    localStorage.setItem("bm-coll-sort-dir", state.collectionSortDir);
    renderSortToggle();
    renderHierarchy();
  });

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
    // Disclosure clicks toggle expand/collapse without changing the active
    // collection filter — they must short-circuit before the filter path.
    const disc = e.target.closest("[data-toggle-coll]");
    if (disc) {
      e.preventDefault();
      const name = disc.dataset.toggleColl;
      if (state.collapsedColls.has(name)) state.collapsedColls.delete(name);
      else state.collapsedColls.add(name);
      persistCollapsedColls();
      renderHierarchy();
      return;
    }
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

  async function handleDelete(path) {
    if (!path) return;
    const bm = state.data && state.data.bookmarks.find((x) => x.path === path);
    const label = bm ? (bm.title || bm.url) : path;
    if (!confirm(`Move to _trash?\n\n${label}`)) return;
    try {
      const res = await fetch("/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      // Optimistic state update: drop the bookmark from totals/collections and
      // bump the _trash collection's count. (Re-fetching /bookmarks.json would
      // be more accurate but visibly laggier on a 1845-card vault.)
      if (state.data && bm) {
        state.data.bookmarks = state.data.bookmarks.filter((x) => x.path !== path);
        state.data.totals.bookmarks = Math.max(0, state.data.totals.bookmarks - 1);
        if (bm.kind === "inbox") {
          state.data.totals.inbox = Math.max(0, (state.data.totals.inbox || 0) - 1);
        } else {
          state.data.totals.filed = Math.max(0, (state.data.totals.filed || 0) - 1);
        }
        state.data.totals.trashed = (state.data.totals.trashed || 0) + 1;
        const srcColl = state.data.collections.find((c) => c.name === bm.collection);
        if (srcColl) srcColl.count = Math.max(0, srcColl.count - 1);
        const trashColl = state.data.collections.find((c) => c.name === "_trash");
        if (trashColl) trashColl.count += 1;
        render();
      }
    } catch (e) {
      alert(`Delete failed: ${e.message}`);
    }
  }

  async function handleRestore(path) {
    if (!path) return;
    const bm = state.data && state.data.bookmarks.find((x) => x.path === path);
    try {
      const res = await fetch("/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      // Refetch to learn the restored bookmark's new state (trashed_from
      // stripped, kind back to filed/inbox, may go to a different collection
      // than trashed_from if that dir vanished). Cheaper than reconstructing
      // server-side logic in JS.
      await loadData();
    } catch (e) {
      alert(`Restore failed: ${e.message}`);
    }
  }

  async function handleEmptyTrash() {
    const n = (state.data && state.data.totals.trashed) || 0;
    if (n === 0) return;
    if (!confirm(`Permanently delete ${n} item${n === 1 ? "" : "s"} in _trash?\n\nThis removes the files from the working tree. Git history still preserves anything that was previously committed.`)) return;
    try {
      const res = await fetch("/empty-trash", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      if (data.errors && data.errors.length) {
        alert(`Deleted ${data.deleted} item(s); ${data.errors.length} failed.\nFirst error: ${data.errors[0].error}`);
      }
      await loadData();
    } catch (e) {
      alert(`Empty trash failed: ${e.message}`);
    }
  }

  // Delegate tag-chip + size-row + coll-meta + delete/restore clicks
  document.addEventListener("click", (e) => {
    const delEl = e.target.closest(".bm-delete");
    if (delEl) {
      e.preventDefault();
      handleDelete(delEl.dataset.path);
      return;
    }
    const restoreEl = e.target.closest(".bm-restore");
    if (restoreEl) {
      e.preventDefault();
      handleRestore(restoreEl.dataset.path);
      return;
    }
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
    if (e.target.closest("#empty-trash-btn")) {
      e.preventDefault();
      handleEmptyTrash();
      return;
    }
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
