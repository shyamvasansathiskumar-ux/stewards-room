// Renders report.json. All text from the data goes in with textContent, never as HTML.

const $ = (s) => document.querySelector(s);

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
const day = (iso) => { const [y, m, d] = iso.split("-"); return `${d} ${MONTHS[+m - 1]} ${y}`; };
const safeUrl = (u) => (/^https:\/\/(www\.)?fia\.com\//.test(u) ? u : "#");
const ARTICLE = (a) => (a ? a.replace(/^L-IV-(\d+)([a-z]?)$/, "App. L, Ch. IV, Art. $1 $2)") : "–");

function meter() {
  const m = $("#meter");
  for (let i = 1; i <= 12; i++) m.append(el("span", { class: "seg" + (i <= 8 ? " on" : i <= 11 ? " new" : "") }));
}

function facts(r) {
  const s = r.index.seasons;
  const items = [
    [String(s["2025"].documents + s["2026"].documents), "FIA documents listed, 2025 and 2026"],
    [String(s["2025"].summons + s["2026"].summons), "summonses to the stewards"],
    [String(s["2025"].corrected + s["2026"].corrected), "documents re-issued as “Corrected”"],
    [`${r.parser_score.passed}/${r.parser_score.checks}`, `fields read right on ${r.parser_score.documents} hand-checked decisions`],
  ];
  $("#facts").replaceChildren(...items.map(([b, t]) => el("div", { class: "fact" }, el("b", { text: b }), el("span", { text: t }))));
}

function rate(r) {
  const out = [];
  for (const [season, v] of Object.entries(r.points_rate)) {
    const dots = el("div", { class: "dots", "aria-hidden": "true" });
    for (let i = 0; i < v.penalised; i++) dots.append(el("span", { class: "dot" + (i < v.with_points ? " p" : "") }));
    out.push(el("div", { class: "rate-card" },
      el("div", { class: "yr", text: season }),
      el("div", { class: "big", text: `${v.with_points} of ${v.penalised}` }),
      el("div", { text: "penalised collisions also gave penalty points" }),
      dots,
      v.small ? el("span", { class: "tag", text: "small sample" }) : null));
  }
  $("#rate").replaceChildren(...out);
}

function spread(r) {
  const rows = r.spread.filter((s) => s.article === "L-IV-2d");
  $("#spread").replaceChildren(...rows.map((s) => {
    const chips = el("div", { class: "chips" });
    for (const [o, n] of Object.entries(s.outcomes)) {
      chips.append(el("span", { class: "chip" + (o === s.usual ? " usual" : "") }, o, el("b", { text: "×" + n })));
    }
    const deps = s.departures.map((d) => {
      const state = d.explained === true ? ["yes", "explained"] : d.explained === false ? ["no", "not explained"] : ["unk", "can't tell"];
      const body = el("div", {},
        el("span", { class: "state " + state[0], text: state[1] }),
        `${d.outcome}, where the usual was ${d.usual}. `,
        d.because ? el("q", { text: d.because }) : null,
        " ", el("a", { href: safeUrl(d.url), rel: "noopener", text: "PDF" }));
      return el("div", { class: "dep" }, el("div", { class: "dep-who" }, d.driver || "–", el("small", { text: d.event })), body);
    });
    return el("div", { class: "season" },
      el("div", { class: "season-h" }, String(s.season), el("small", { text: `${s.n} decisions` }),
        s.small ? el("span", { class: "tag", text: "small sample" }) : null),
      el("div", {}, chips, ...(deps.length ? deps : [el("p", { class: "dim", text: "No departures." })])));
  }));
}

function ledger(r) {
  const rows = [];
  for (const a of r.agreements) {
    rows.push(el("div", { class: "lrow match" }, el("span", { class: "ic", text: "=" }),
      el("span", { class: "mono", text: day(a.on) }),
      el("span", {}, `${a.driver}: the FIA printed a total of ${a.fia_says}, and the register's history adds up to ${a.fia_says}. `,
        el("a", { href: safeUrl(a.source), rel: "noopener", text: "PDF" }))));
  }
  for (const d of r.disagreements) {
    rows.push(el("div", { class: "lrow gap" }, el("span", { class: "ic", text: "≠" }),
      el("span", { class: "mono", text: day(d.on) }),
      el("span", {}, `${d.driver}: the FIA printed ${d.fia_says}; the register's history adds up to ${d.ledger_says}. Most likely ${d.missing_points} points come from decisions not yet in the register. `,
        el("a", { href: safeUrl(d.source), rel: "noopener", text: "PDF" }))));
  }
  $("#ledger").replaceChildren(...rows);
}

let ALL = [];
function rows(season) {
  const list = ALL.filter((d) => season === "all" || String(d.season) === season);
  $("#rows").replaceChildren(...list.map((d) => el("tr", {},
    el("td", { class: "num" }, day(d.date), d.gold ? el("br") : null, d.gold ? el("span", { class: "tag", text: "checked" }) : null),
    el("td", { text: d.event.replace(/^\d{4} /, "") }),
    el("td", {}, d.driver || "–", el("br"), el("span", { class: "mono dim", text: `Car ${d.car}` })),
    el("td", { text: d.session || "–" }),
    el("td", { class: "fact-q" }, d.fact ? `“${d.fact}”` : el("span", { class: "missing", text: "No Fact printed" }),
      " ", el("a", { href: safeUrl(d.url), rel: "noopener", text: "PDF" })),
    el("td", { class: "art", text: ARTICLE(d.article) }),
    el("td", {}, el("span", { class: "out" + (d.points ? " pts" : ""), text: d.outcome }))
  )));
}

function filter() {
  for (const b of document.querySelectorAll(".filter button")) {
    b.addEventListener("click", () => {
      for (const o of document.querySelectorAll(".filter button")) o.setAttribute("aria-pressed", String(o === b));
      rows(b.dataset.season);
    });
  }
}

function index(r) {
  const label = { documents: "All documents", summons: "Summonses", decision: "Decisions", infringement: "Infringements", corrected: "Re-issued as “Corrected”", events: "Events" };
  $("#idx").replaceChildren(...Object.entries(r.index.seasons).map(([y, v]) => {
    const dl = el("dl");
    for (const k of ["events", "documents", "summons", "decision", "infringement", "corrected"]) dl.append(el("dt", { text: label[k] }), el("dd", { text: String(v[k]) }));
    return el("div", { class: "idx-card" }, el("h3", { text: y + (y === "2026" ? " (to 11 Oct)" : "") }), dl);
  }));
  $("#notes").replaceChildren(...r.index.notes.map((n) => el("li", { text: n })));
}

async function main() {
  meter();
  let r;
  try {
    const res = await fetch("report.json", { cache: "no-cache" });
    r = await res.json();
  } catch {
    $("#facts").replaceChildren(el("p", { class: "dim", text: "The data file didn't load. Refresh to try again." }));
    return;
  }
  facts(r); rate(r); spread(r); ledger(r); index(r);
  ALL = r.decisions; rows("all"); filter();
  $("#score").textContent = `${r.parser_score.passed} of ${r.parser_score.checks} checks`;
  $("#gen").textContent = `data built ${day(r.generated)}`;
}
main();
