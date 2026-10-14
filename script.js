document.addEventListener("DOMContentLoaded", () => {
  /* ---------- modals ---------- */
  const openModal = (id, trigger) => {
    const modal = document.getElementById(id);
    if (!modal) return;
    const form = modal.querySelector("form");
    const item = trigger && trigger.dataset.item ? JSON.parse(trigger.dataset.item) : null;
    if (form) {
      form.reset();
      if (trigger && trigger.dataset.action) form.action = trigger.dataset.action;
      if (item) {
        Object.keys(item).forEach((key) => {
          const el = form.elements[key];
          if (el && el.type !== "file" && el.type !== "hidden") el.value = item[key] == null ? "" : item[key];
        });
      }
    }
    if (item) {
      modal.querySelectorAll("[data-field]").forEach((el) => {
        const v = item[el.dataset.field];
        el.textContent = v === null || v === undefined || v === "" ? "Not provided" : v;
      });
      modal.querySelectorAll("[data-resume]").forEach((a) => {
        a.hidden = !item.resume;
        a.href = "/resume/" + item.id;
      });
    }
    const title = modal.querySelector("[data-modal-title]");
    if (title && trigger && trigger.dataset.title) title.textContent = trigger.dataset.title;
    modal.classList.add("open");
    const first = modal.querySelector("input:not([type=hidden]):not([readonly]), select, textarea");
    if (first) first.focus();
  };
  const closeModals = () => document.querySelectorAll(".modal.open").forEach((m) => m.classList.remove("open"));

  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-modal]");
    if (opener) { e.preventDefault(); openModal(opener.dataset.modal, opener); return; }
    if (e.target.closest("[data-close]") || e.target.classList.contains("modal")) closeModals();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModals(); });

  document.querySelectorAll("form[data-confirm]").forEach((f) =>
    f.addEventListener("submit", (e) => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));

  /* ---------- mobile sidebar ---------- */
  const menuBtn = document.getElementById("menuBtn");
  const sidebar = document.getElementById("sidebar");
  if (menuBtn && sidebar) menuBtn.addEventListener("click", () => sidebar.classList.toggle("open"));

  /* ---------- flash auto-dismiss ---------- */
  document.querySelectorAll(".flash.success").forEach((f) => setTimeout(() => f.remove(), 6000));

  /* ---------- job search + filters (no page reload) ---------- */
  const cards = [...document.querySelectorAll(".job-card")];
  if (cards.length) {
    const val = (id) => (document.getElementById(id) || {}).value || "";
    const empty = document.getElementById("noJobs");
    const count = document.getElementById("jobCount");
    const apply = () => {
      const search = val("fSearch").toLowerCase().trim();
      const loc = val("fLocation"), type = val("fType"), dept = val("fDept").toLowerCase();
      const minSal = parseFloat(val("fSalary")) || 0, maxCgpa = parseFloat(val("fCgpa")) || 0;
      const onlyElig = document.getElementById("fEligible")?.checked;
      let shown = 0;
      cards.forEach((c) => {
        const d = c.dataset;
        const depts = d.dept.split(",").map((x) => x.trim());
        const ok =
          (!search || d.company.includes(search) || d.role.includes(search)) &&
          (!loc || d.location === loc) && (!type || d.type === type) &&
          (!minSal || parseFloat(d.salary) >= minSal) &&
          (!maxCgpa || parseFloat(d.cgpa) <= maxCgpa) &&
          (!dept || depts.includes(dept) || depts.includes("all")) &&
          (!onlyElig || d.eligible === "1");
        c.hidden = !ok;
        if (ok) shown++;
      });
      if (empty) empty.hidden = shown !== 0;
      if (count) count.textContent = shown;
    };
    document.querySelectorAll("[data-filter]").forEach((el) => el.addEventListener("input", apply));
    document.getElementById("resetFilters")?.addEventListener("click", () => {
      document.querySelectorAll("[data-filter]").forEach((el) => { el.type === "checkbox" ? (el.checked = false) : (el.value = ""); });
      apply();
    });
    apply();
  }

  /* ---------- eligibility check ---------- */
  const eligBody = document.getElementById("eligBody");
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  document.querySelectorAll("[data-check-job]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      if (!eligBody) return;
      eligBody.innerHTML = "<p class='muted'>Checking your profile against the requirements...</p>";
      document.getElementById("eligModal").classList.add("open");
      try {
        const res = await fetch("/api/eligibility/" + btn.dataset.checkJob, { headers: { Accept: "application/json" } });
        if (!res.ok) throw new Error();
        const r = await res.json();
        const title = `<p class="muted small">${esc(r.role)} at ${esc(r.company)}</p>`;
        eligBody.innerHTML = r.eligible
          ? `${title}<div class="elig-box ok"><strong>Congratulations! You are eligible to apply for this position.</strong>${r.applied ? "<p>You have already applied.</p>" : ""}</div>`
          : `${title}<div class="elig-box no"><strong>You do not meet the eligibility criteria.</strong><ul>${r.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
      } catch {
        eligBody.innerHTML = "<div class='elig-box no'>Could not check eligibility. Please try again.</div>";
      }
    }));
});
