// Stewards' Room: the interactive parts. The ban-clock simulator, "You make the call",
// and the searchable register. Data comes from report.json via app.js; text from the data
// is always set with textContent, and every outbound link must point at fia.com.
(() => {
  const $ = (id) => document.getElementById(id);
  function el(tag, attrs = {}, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k === "on") for (const [ev, fn] of Object.entries(v)) e.addEventListener(ev, fn);
      else e.setAttribute(k, v);
    }
    for (const k of kids) if (k != null) e.append(typeof k === "string" ? document.createTextNode(k) : k);
    return e;
  }
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const day = (iso) => { const [y, m, d] = String(iso).slice(0, 10).split("-"); return MONTHS[+m - 1] ? `${+d} ${MONTHS[+m - 1]} ${y}` : String(iso); };
  const safeUrl = (u) => (/^https:\/\/(www\.)?fia\.com\//.test(u) ? u : "#");
  const pdf = (u, t = "Read the PDF ↗") => el("a", { class: "src", href: safeUrl(u), target: "_blank", rel: "noopener noreferrer", text: t });
  const rule = (a) => { const m = /^L-IV-(\d)([a-z])$/.exec(a || ""); return m ? `Appendix L, Chapter IV, Article ${m[1]} ${m[2]})` : (a || "Rule not printed"); };
  const ISO = (t) => new Date(t).toISOString().slice(0, 10);
  const DAY = 86400000;

  // ------------------------------------------------------------------ ban clock
  function clock(r) {
    const drivers = r.clock.filter((c) => c.awards.length);
    if (!drivers.length) return;
    const start = Date.parse("2025-03-01"), end = Date.parse(r.generated || "2026-10-21");
    const slider = $("simSlider");
    slider.max = String(Math.round((end - start) / DAY));
    $("axA").textContent = day(ISO(start));
    $("axB").textContent = day(ISO(end));
    let cur = drivers.find((d) => d.driver === "Max Verstappen") || drivers[0];
    let what = 0;

    const live = (c, d) => c.awards.filter((a) => a.on <= d && d < a.expires).reduce((n, a) => n + a.points, 0);
    // Points the FIA counted that the register can't see: printed total minus what the register held that day.
    // They come from earlier decisions, so they expire no later than 12 months after the printed date.
    function hidden(c, d) {
      const printed = c.awards.filter((a) => a.stated_total != null && a.on <= d && d < a.expires).sort((x, y) => (x.on < y.on ? 1 : -1))[0];
      if (!printed) return { n: 0 };
      const gap = printed.stated_total - live(c, printed.on);
      return gap > 0 ? { n: gap, on: printed.on, until: printed.expires, total: printed.stated_total } : { n: 0 };
    }

    function paint() {
      const d = ISO(start + Number(slider.value) * DAY);
      const reg = live(cur, d), h = hidden(cur, d), total = reg + h.n + what;
      const m = $("simMeter");
      m.replaceChildren();
      for (let i = 1; i <= 12; i++) {
        const cls = i <= reg ? "on" : i <= reg + h.n ? "ghost" : i <= total ? "what" : "";
        m.append(el("i", { class: cls }));
      }
      m.setAttribute("aria-label", `${reg + h.n} of 12 penalty points`);
      $("simPts").textContent = String(Math.min(reg + h.n + what, 99));
      $("simDate").textContent = day(d);
      const bits = [`${cur.driver}: ${reg} point${reg === 1 ? "" : "s"} live in the register`];
      if (h.n) bits.push(`plus ${h.n} more the FIA counted on ${day(h.on)} (it printed a total of ${h.total}); the register doesn't hold those decisions, so we only know they lapse by ${day(h.until)}`);
      const nextExp = cur.awards.filter((a) => a.on <= d && d < a.expires).map((a) => a.expires).sort()[0];
      if (nextExp) bits.push(`next to fall away: ${day(nextExp)}`);
      $("simNote").textContent = bits.join("; ") + ".";
      const left = 12 - total;
      $("whatOut").textContent = what === 0 ? "" : left <= 0 ? "That would be a one-race ban." : `Still ${left} short of a ban.`;
      $("whatOut").className = "sim-out" + (what && left <= 0 ? " ban" : "");
      $("whatN").textContent = String(what);
    }

    $("simDrivers").replaceChildren(...drivers.map((c) => el("button", {
      type: "button", class: "chip" + (c === cur ? " on" : ""), "aria-pressed": String(c === cur), text: c.driver,
      on: { click: (e) => {
        cur = c; what = 0;
        [...$("simDrivers").children].forEach((b) => { const on = b === e.currentTarget; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); });
        slider.value = String(Math.round((Date.parse(c.awards[c.awards.length - 1].on) - start) / DAY));
        paint();
      } },
    })));
    slider.value = String(Math.round((Date.parse(cur.awards[cur.awards.length - 1].on) - start) / DAY));
    slider.addEventListener("input", paint);
    $("whatPlus").addEventListener("click", () => { what = Math.min(what + 1, 12); paint(); });
    $("whatMinus").addEventListener("click", () => { what = Math.max(what - 1, 0); paint(); });
    paint();
  }

  // ------------------------------------------------------------ you make the call
  const OPTIONS = [
    { k: "none", t: "No penalty or a warning" },
    { k: "5s", t: "5-second penalty" },
    { k: "10s", t: "10-second penalty" },
    { k: "grid", t: "Grid drop" },
  ];
  const kind = (o) => (/grid/.test(o) ? "grid" : /^10s/.test(o) ? "10s" : /^5s/.test(o) ? "5s" : "none");
  const label = (k) => OPTIONS.find((o) => o.k === k).t;

  function game(r) {
    const deck = r.decisions.filter((d) => d.fact && d.decision).sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!deck.length) return;
    const usual = (d) => r.spread.find((s) => s.article === d.article && s.season === d.season);
    const answers = new Array(deck.length).fill(null);
    let i = 0, pick = null;

    const prog = $("gProg");
    prog.replaceChildren(...deck.map(() => el("i")));

    $("gPick").replaceChildren(...OPTIONS.map((o) => el("button", {
      type: "button", class: "g-opt", "data-k": o.k, "aria-pressed": "false", text: o.t,
      on: { click: () => { if (answers[i]) return; pick = o.k; syncPick(); } },
    })));
    function syncPick() {
      [...$("gPick").children].forEach((b) => { const on = b.dataset.k === pick; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); });
      $("gGo").disabled = !answers[i] && !pick;
    }

    function score() {
      const done = answers.filter(Boolean);
      const hit = done.filter((a) => a.hit).length;
      $("gScore").textContent = `${hit} of ${done.length} matched`;
      [...prog.children].forEach((b, j) => { b.className = answers[j] ? (answers[j].hit ? "hit" : "miss") : j === i ? "cur" : ""; });
    }

    function reveal(d, a) {
      const u = usual(d);
      const box = $("gReveal");
      box.hidden = false;
      box.replaceChildren(
        el("p", { class: "g-verdict " + (a.hit ? "hit" : "miss") }, a.hit ? "Same call as the stewards." : `You chose ${label(a.k).toLowerCase()}; they didn't.`,
          a.ptsHit ? null : el("span", { text: d.points ? ` They also gave ${d.points} penalty point${d.points > 1 ? "s" : ""}.` : " They gave no penalty points." })),
        el("dl", { class: "g-fields" },
          el("div", {}, el("dt", { text: "Decision" }), el("dd", { text: `“${d.decision}”` })),
          d.reason ? el("div", {}, el("dt", { text: "Reason (excerpt)" }), el("dd", { text: `“${d.reason}”` })) : null,
          u ? el("div", {}, el("dt", { text: "Usual here" }), el("dd", { class: "plain", text: `Under ${rule(d.article)} in ${d.season}, the register's most common outcome is ${u.usual} (${u.n} decision${u.n > 1 ? "s" : ""}${u.small ? ", a small sample" : ""}).` })) : null),
        el("p", { class: "g-src" }, `${d.event}, ${d.session}. `, pdf(d.url)));
    }

    function show() {
      const d = deck[i], a = answers[i];
      pick = a ? a.k : null;
      $("gPos").textContent = `${i + 1} / ${deck.length}`;
      $("gCase").replaceChildren(
        el("div", { class: "g-meta" }, el("span", { class: "label bare", text: `${d.event} · ${d.session}` }), el("span", { class: "label bare", text: day(d.date) })),
        el("p", { class: "g-who" }, el("b", { text: d.driver || "–" }), el("span", { class: "mono small", text: d.car != null ? ` Car ${d.car}` : "" })),
        el("blockquote", { class: "g-fact", text: `“${d.fact}”` }),
        el("p", { class: "g-rule mono small", text: `Rule cited: ${rule(d.article)}` }));
      $("gPts").checked = a ? a.pts : false;
      $("gPts").disabled = !!a;
      if (a) reveal(d, a); else { $("gReveal").hidden = true; $("gReveal").replaceChildren(); }
      $("gGo").textContent = a ? (i === deck.length - 1 ? "See your result" : "Next case →") : "Decide";
      $("gPrev").disabled = i === 0;
      syncPick(); score();
    }

    function finish() {
      const hit = answers.filter((a) => a && a.hit).length, pts = answers.filter((a) => a && a.ptsHit).length;
      // Only none < 5 s < 10 s can be ranked; a grid drop is a different kind of penalty.
      const rank = { none: 0, "5s": 1, "10s": 2 };
      let harsher = 0, softer = 0, other = 0;
      answers.forEach((a, j) => {
        if (!a || a.hit) return;
        const mine = rank[a.k], theirs = rank[kind(deck[j].outcome)];
        if (mine == null || theirs == null) other += 1; else if (mine > theirs) harsher += 1; else softer += 1;
      });
      const n = (k, w) => `${k} time${k === 1 ? "" : "s"} ${w}`;
      $("gCase").replaceChildren(
        el("p", { class: "label bare", text: "Your result" }),
        el("p", { class: "g-final" }, String(hit), el("em", { text: ` of ${deck.length}` })),
        el("p", { class: "body", text: `You matched the stewards' penalty ${hit} of ${deck.length} times and their call on penalty points ${pts} times.` + (hit < deck.length ? ` Where you differed: ${[harsher && n(harsher, "harsher"), softer && n(softer, "more lenient"), other && n(other, "a different kind of penalty")].filter(Boolean).join(", ")}.` : "") }),
        el("p", { class: "fine", text: "This doesn't show who was right. The stewards saw video, telemetry and both drivers; you saw one sentence. It shows how much a penalty depends on what isn't in the Fact." }));
      $("gPick").hidden = true; $("gReveal").hidden = true; $("gPts").parentElement.hidden = true;
      $("gGo").textContent = "Play again"; $("gGo").disabled = false; $("gPrev").disabled = true;
      $("gPos").textContent = "Done";
      finished = true;
    }
    let finished = false;

    $("gGo").addEventListener("click", () => {
      if (finished) {
        answers.fill(null); i = 0; finished = false;
        $("gPick").hidden = false; $("gPts").parentElement.hidden = false;
        show(); return;
      }
      const d = deck[i];
      if (!answers[i]) {
        if (!pick) return;
        const pts = $("gPts").checked;
        answers[i] = { k: pick, pts, hit: pick === kind(d.outcome), ptsHit: pts === d.points > 0 };
        show(); return;
      }
      if (i === deck.length - 1) { finish(); return; }
      i += 1; show();
    });
    $("gPrev").addEventListener("click", () => { if (i > 0 && !finished) { i -= 1; show(); } });
    show();
  }

  // ------------------------------------------------------------------- register
  function register(r) {
    const ALL = r.decisions;
    const kinds = [...new Set(ALL.map((d) => d.family).filter(Boolean))];
    const names = { collision: "Collisions", impeding: "Impeding", other: "Other" };
    let season = "all", fam = "all", q = "";
    $("kinds").replaceChildren(...["all", ...kinds].map((k) => el("button", {
      type: "button", class: "chip" + (k === "all" ? " on" : ""), "data-k": k, "aria-pressed": String(k === "all"),
      text: k === "all" ? "Every kind" : (names[k] || k),
      on: { click: (e) => { fam = k; [...$("kinds").children].forEach((b) => { const on = b === e.currentTarget; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); }); draw(); } },
    })));
    document.querySelectorAll(".filter .chip[data-season]").forEach((b) => b.addEventListener("click", () => {
      season = b.dataset.season;
      document.querySelectorAll(".filter .chip[data-season]").forEach((o) => { const on = o === b; o.classList.toggle("on", on); o.setAttribute("aria-pressed", String(on)); });
      draw();
    }));
    $("q").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); draw(); });

    function detail(d) {
      const row = (k, v, plain) => (v == null || v === "" ? null : el("div", {}, el("dt", { text: k }), el("dd", { class: plain ? "plain" : "", text: plain ? String(v) : `“${v}”` })));
      return el("tr", { class: "more" }, el("td", { colspan: "7" },
        el("dl", { class: "reg-dl" },
          row("Rule", rule(d.article), true),
          row("Fact", d.fact),
          row("Decision", d.decision),
          row("Reason (excerpt)", d.reason),
          row("Penalty points", d.points ? `${d.points}${d.stated_total != null ? ` (FIA printed total: ${d.stated_total})` : ""}` : "None", true),
          d.problems && d.problems.length ? row("Flagged by the parser", d.problems.join("; "), true) : null),
        pdf(d.url, "Open the FIA document ↗")));
    }

    function draw() {
      const list = ALL.filter((d) => (season === "all" || String(d.season) === season) && (fam === "all" || d.family === fam) &&
        (!q || [d.driver, d.event, d.session, d.fact, d.decision, d.reason, d.outcome].join(" ").toLowerCase().includes(q)));
      const rows = [];
      for (const d of list) {
        const btn = el("button", { type: "button", class: "open", "aria-expanded": "false", "aria-label": `Show every field for ${d.driver || "this decision"}`, text: "+" });
        const tr = el("tr", { class: "row" },
          el("td", { class: "d" }, day(d.date), d.gold ? el("br") : null, d.gold ? el("span", { class: "tag", text: "checked" }) : null),
          el("td", { text: d.event.replace(/^\d{4} /, "") }),
          el("td", { class: "drv" }, el("b", { text: d.driver || "–" }), el("span", { text: d.car != null ? `Car ${d.car}` : "" })),
          el("td", { text: d.session || "–" }),
          el("td", { class: "fact" }, d.fact ? `“${d.fact}”` : el("span", { class: "none", text: "No Fact printed" })),
          el("td", { class: "out" }, el("span", { class: d.points ? "pts" : "", text: d.outcome })),
          el("td", { class: "tog" }, btn));
        let open = null;
        const toggle = () => {
          if (open) { open.remove(); open = null; btn.textContent = "+"; btn.setAttribute("aria-expanded", "false"); tr.classList.remove("is-open"); return; }
          open = detail(d); tr.after(open); btn.textContent = "−"; btn.setAttribute("aria-expanded", "true"); tr.classList.add("is-open");
        };
        btn.addEventListener("click", (e) => { e.stopPropagation(); toggle(); });
        tr.addEventListener("click", (e) => { if (!e.target.closest("a")) toggle(); });
        rows.push(tr);
      }
      $("rows").replaceChildren(...rows);
      if (!list.length) $("rows").append(el("tr", {}, el("td", { colspan: "7", class: "empty", text: "Nothing matches. Try fewer words." })));
      $("regCount").textContent = `${list.length} of ${ALL.length} decisions`;
      if (window.ScrollTrigger) ScrollTrigger.refresh();
    }
    draw();
  }

  // app.js may finish loading the data before this file runs, so take it from either place, once.
  let started = false;
  function start(r) {
    if (started || !r) return;
    started = true;
    try { clock(r); } catch (err) { console.warn("clock", err); }
    try { game(r); } catch (err) { console.warn("game", err); }
    try { register(r); } catch (err) { console.warn("register", err); }
  }
  document.addEventListener("sr:data", (e) => start(e.detail));
  start(window.SR_DATA);
})();
