// Stewards' Room: renders report.json into the page. Text from the data is set with textContent,
// never as HTML, and every outbound link must point at fia.com.
(() => {
  const $ = (id) => document.getElementById(id);

  function el(tag, attrs = {}, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else e.setAttribute(k, v);
    }
    for (const k of kids) if (k != null) e.append(typeof k === "string" ? document.createTextNode(k) : k);
    return e;
  }
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const day = (iso) => { const [y, m, d] = String(iso).split("-"); return MONTHS[+m - 1] ? `${d} ${MONTHS[+m - 1]} ${y}` : String(iso); };
  const safeUrl = (u) => (/^https:\/\/(www\.)?fia\.com\//.test(u) ? u : "#");
  const pdf = (u) => el("a", { class: "src", href: safeUrl(u), target: "_blank", rel: "noopener noreferrer", text: "PDF ↗" });
  const fmt = (n) => Number(n).toLocaleString("en-IN");

  // hero meter: eight earlier points plus the three from Spain 2025
  const meter = $("heroMeter");
  for (let i = 1; i <= 12; i++) meter.append(el("i", { class: i <= 8 ? "on" : i <= 11 ? "new" : "" }));

  function rate(r) {
    $("rate").replaceChildren(...Object.entries(r.points_rate).map(([season, v]) => {
      const dots = el("div", { class: "dots", "aria-hidden": "true" });
      for (let i = 0; i < v.penalised; i++) dots.append(el("i", { class: i < v.with_points ? "p" : "" }));
      return el("div", { class: "card" },
        el("span", { class: "yr", text: season }),
        el("div", { class: "big" }, String(v.with_points), el("em", { text: " of " }), String(v.penalised)),
        el("p", { class: "fine", text: "penalised collisions also gave penalty points" }),
        dots,
        v.small ? el("span", { class: "tag", text: "small sample" }) : null);
    }));
  }

  function spread(r) {
    const rows = r.spread.filter((s) => s.article === "L-IV-2d").sort((a, b) => b.season - a.season);
    $("spread").replaceChildren(...rows.map((s) => {
      const chips = el("div", { class: "chips" }, ...Object.entries(s.outcomes).map(([o, n]) =>
        el("span", { class: "out-chip" + (o === s.usual ? " usual" : "") }, o, el("b", { text: "×" + n }))));
      const deps = s.departures.map((d) => {
        const st = d.explained === true ? ["yes", "explained"] : d.explained === false ? ["no", "not explained"] : ["unk", "can't tell yet"];
        return el("div", { class: "dep" },
          el("div", { class: "dep-who" }, el("b", { text: d.driver || "–" }), el("small", { text: d.event })),
          el("div", {}, el("p", {}, el("span", { class: "state " + st[0], text: st[1] }), `${d.outcome}, where the usual was ${d.usual}. `, pdf(d.url)),
            d.because ? el("q", { text: d.because }) : null));
      });
      return el("div", { class: "season" },
        el("div", { class: "season-h" }, String(s.season), el("small", { text: `${s.n} decisions${s.small ? " · small sample" : ""}` })),
        el("div", {}, chips, ...(deps.length ? deps : [el("p", { class: "fine", text: "No departures." })])));
    }));
  }

  function ledger(r) {
    const rows = [
      ...r.agreements.map((a) => el("div", { class: "lrow match" }, el("span", { class: "ic", text: "=" }), el("span", { class: "d", text: day(a.on) }),
        el("p", {}, `${a.driver}: the FIA printed ${a.fia_says}, and the register's own history adds up to ${a.fia_says}. `, pdf(a.source)))),
      ...r.disagreements.map((d) => el("div", { class: "lrow gap" }, el("span", { class: "ic", text: "≠" }), el("span", { class: "d", text: day(d.on) }),
        el("p", {}, `${d.driver}: the FIA printed ${d.fia_says}; the register's history adds up to ${d.ledger_says}. Most likely ${d.missing_points} points come from decisions not yet in the register. `, pdf(d.source)))),
    ];
    $("ledger").replaceChildren(...rows);
  }

  let ALL = [];
  function table(season) {
    const list = ALL.filter((d) => season === "all" || String(d.season) === season);
    $("rows").replaceChildren(...list.map((d) => el("tr", {},
      el("td", { class: "d" }, day(d.date), d.gold ? el("br") : null, d.gold ? el("span", { class: "tag", text: "checked" }) : null),
      el("td", { text: d.event.replace(/^\d{4} /, "") }),
      el("td", { class: "drv" }, el("b", { text: d.driver || "–" }), el("span", { text: d.car != null ? `Car ${d.car}` : "" })),
      el("td", { text: d.session || "–" }),
      el("td", { class: "fact" }, d.fact ? `“${d.fact}” ` : el("span", { class: "none", text: "No Fact printed " }), el("a", { href: safeUrl(d.url), target: "_blank", rel: "noopener noreferrer", text: "PDF ↗" })),
      el("td", { class: "out" }, el("span", { class: d.points ? "pts" : "", text: d.outcome })))));
  }
  function filter() {
    const btns = [...document.querySelectorAll(".filter .chip")];
    btns.forEach((b) => b.addEventListener("click", () => {
      btns.forEach((o) => { const on = o === b; o.classList.toggle("on", on); o.setAttribute("aria-pressed", String(on)); });
      table(b.dataset.season);
    }));
  }

  function index(r) {
    const s = r.index.seasons, total = Object.values(s).reduce((n, v) => n + v.documents, 0);
    $("docCount").textContent = String(total);
    $("docCount").dataset.count = String(total);
    $("metaDocs").textContent = `${fmt(total)} FIA documents indexed`;
    const label = { events: "Events", documents: "All documents", summons: "Summonses", decision: "Decisions", infringement: "Infringements", corrected: "Re-issued as “Corrected”" };
    $("idx").replaceChildren(...Object.entries(s).map(([y, v]) => {
      const dl = el("dl");
      for (const k of Object.keys(label)) dl.append(el("dt", { text: label[k] }), el("dd", { text: fmt(v[k]) }));
      return el("div", { class: "card" }, el("h3", { class: "h3", text: y + (y === "2026" ? ", to 11 Oct" : "") }), dl);
    }));
    $("notes").replaceChildren(...r.index.notes.map((n) => el("li", { text: n })));
    $("score").textContent = `On the hand-checked set it reads ${r.parser_score.passed} of ${r.parser_score.checks} structured fields right.`;
  }

  fetch("report.json", { cache: "no-cache" })
    .then((res) => { if (!res.ok) throw new Error(res.status); return res.json(); })
    .then((r) => { rate(r); spread(r); ledger(r); index(r); ALL = r.decisions; table("all"); filter(); if (window.ScrollTrigger) ScrollTrigger.refresh(); })
    .catch(() => { $("spread").replaceChildren(el("p", { class: "body", text: "The data file didn't load. Refresh to try again." })); });
})();
