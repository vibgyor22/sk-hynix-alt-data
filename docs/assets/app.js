/* SK hynix alt-data site. Plain JS + D3 v7. All numbers come from docs/data/*.json. */
(function () {
  "use strict";

  const RM = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

  // ------------------------------------------------------------------ dates & formats
  const pm = (s) => { const [y, m] = s.split("-").map(Number); return new Date(y, m - 1, 15); };
  const pq = (s) => { const y = +s.slice(0, 4), q = +s.slice(5); return new Date(y, (q - 1) * 3 + 1, 15); };
  const quarterOf = (m) => { const [y, mm] = m.split("-").map(Number); return y + "Q" + (Math.floor((mm - 1) / 3) + 1); };
  const fmtMonth = d3.timeFormat("%b %Y");
  const qLabel = (s) => "Q" + s.slice(5) + " " + s.slice(0, 4);
  const mLabel = (s) => fmtMonth(pm(s));
  const sign = (v) => (v >= 0 ? "+" : "−");
  const tfmt = (d) => (d.getMonth() === 0 ? d3.timeFormat("%Y")(d) : d3.timeFormat("%b")(d));

  const F = {
    q: qLabel, m: mLabel, str: (s) => String(s),
    int: (v) => d3.format(",")(Math.round(v)),
    x2: (v) => v.toFixed(2) + "×", x1: (v) => v.toFixed(1) + "×",
    pct0: (v) => Math.round(v) + "%", pct1: (v) => v.toFixed(1) + "%",
    pct0s: (v) => sign(v) + Math.abs(Math.round(v)) + "%",
    pct1s: (v) => sign(v) + Math.abs(v).toFixed(1) + "%",
    usd2: (v) => "$" + v.toFixed(2),
    tn1: (v) => "₩" + (v / 1e6).toFixed(1) + "tn",
    tn0a: (v) => "~₩" + Math.round(v / 1e6) + "tn",
    f2: (v) => v.toFixed(2),
    krwbn: (v) => "₩" + (v / 1000).toFixed(1) + "bn",
    pct0a: (v) => "about " + Math.round(v) + "%",
    weeks: (v) => "about " + Math.round(v / 7) + " weeks",
  };
  const pctS = (v, n = 1) => (v == null ? "–" : sign(v) + Math.abs(v).toFixed(n) + "%");

  // ------------------------------------------------------------------ tooltip
  const tipEl = $("#tip");
  function placeTip(ev) {
    const pad = 14, r = tipEl.getBoundingClientRect();
    let x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + r.width > window.innerWidth - 8) x = ev.clientX - r.width - pad;
    if (y + r.height > window.innerHeight - 8) y = ev.clientY - r.height - pad;
    tipEl.style.left = Math.max(8, x) + "px";
    tipEl.style.top = Math.max(8, y) + "px";
  }
  function showTip(html, ev) { tipEl.innerHTML = html; tipEl.classList.add("on"); placeTip(ev); }
  function hideTip() { tipEl.classList.remove("on"); }
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const swatch = (s) => s
    ? `<svg viewBox="0 0 16 6"><line x1="1" x2="15" y1="3" y2="3" class="line ${s.cls} ${s.dash || ""}" stroke-width="2"/></svg>`
    : "";
  function tipHtml(title, rows, src) {
    return `<div class="t">${esc(title)}</div>` +
      rows.map((r) => `<div class="r"><span class="k">${swatch(r[2])}${esc(r[0])}</span><span>${esc(r[1])}</span></div>`).join("") +
      (src ? `<div class="s">${src}</div>` : "");
  }

  // ------------------------------------------------------------------ animation helpers
  function hidePath(node) {
    if (RM) return;
    const L = node.getTotalLength();
    d3.select(node).style("stroke-dasharray", `${L} ${L}`).style("stroke-dashoffset", L);
    node.__hidden = true;
  }
  function drawIn(node, delay) {
    if (RM || !node.__hidden) return;
    node.__hidden = false;
    const L = node.getTotalLength();
    d3.select(node).style("stroke-dasharray", `${L} ${L}`).style("stroke-dashoffset", L)
      .transition().delay(delay || 0).duration(1500).ease(d3.easeCubicOut)
      .style("stroke-dashoffset", 0)
      .on("end", function () { d3.select(this).style("stroke-dasharray", null).style("stroke-dashoffset", null); });
  }
  function logTicks(y) {
    const [a, b] = y.domain();
    const c = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000].filter((v) => v >= a && v <= b);
    return c.length >= 2 ? c : y.ticks(4);
  }
  function margins(w, mr) {
    const narrow = w < 560;
    return { t: 22, r: narrow ? Math.min(mr, 74) : mr, b: 26, l: narrow ? 40 : 54, narrow };
  }

  // ------------------------------------------------------------------ generic line chart
  function LineChart(el, o) {
    const svg = d3.select(el).append("svg").attr("role", "img").attr("aria-label", o.aria || "chart");
    const defs = svg.append("defs");
    const cid = "clip" + Math.random().toString(36).slice(2, 8);
    const clipRect = defs.append("clipPath").attr("id", cid).append("rect");
    const gGrid = svg.append("g").attr("class", "grid");
    const gX = svg.append("g").attr("class", "axis");
    const gY = svg.append("g").attr("class", "axis");
    const gRef = svg.append("g");
    const gLines = svg.append("g").attr("clip-path", `url(#${cid})`);
    const gAnn = svg.append("g");
    const gEnd = svg.append("g");
    const gHover = svg.append("g").style("pointer-events", "none");
    const overlay = svg.append("rect").attr("fill", "transparent").style("touch-action", "pan-y");
    const st = { xDom: null, visible: false, x: null, y: null, S: [], dates: [] };

    function render(anim) {
      const w = el.clientWidth || 600, h = o.height(w), m = margins(w, o.mr || 120);
      svg.attr("viewBox", `0 0 ${w} ${h}`).attr("width", w).attr("height", h);
      const S = o.series().filter((s) => s.on !== false);
      S.forEach((s) => { s.byT = new Map(s.points.map((p) => [+p.d, p])); });
      const all = S.flatMap((s) => s.points);
      const full = o.xFull ? o.xFull() : d3.extent(all, (p) => p.d);
      const xd = st.xDom || full;
      const x = d3.scaleTime().domain(xd).range([m.l, w - m.r]);
      const vis = all.filter((p) => p.y != null && p.d >= xd[0] && p.d <= xd[1]);
      let y0 = d3.min(vis, (p) => p.y), y1 = d3.max(vis, (p) => p.y);
      if (y0 == null) { y0 = o.yType === "log" ? 50 : 0; y1 = o.yType === "log" ? 200 : 1; }
      if (o.includeZero) { y0 = Math.min(y0, 0); y1 = Math.max(y1, 0); }
      if (o.ref && o.yType !== "log") { y0 = Math.min(y0, o.ref.v); y1 = Math.max(y1, o.ref.v); }
      let y;
      if (o.yType === "log") {
        if (o.ref) { y0 = Math.min(y0, o.ref.v); y1 = Math.max(y1, o.ref.v); }
        y = d3.scaleLog().domain([y0 / 1.18, y1 * 1.18]).range([h - m.b, m.t]);
      } else {
        const pad = (y1 - y0) * 0.06 || 1;
        y = d3.scaleLinear().domain([o.includeZero && y0 >= 0 ? 0 : y0 - pad, y1 + pad]).nice().range([h - m.b, m.t]);
      }
      st.x = x; st.y = y; st.S = S;
      const T = anim && !RM ? d3.transition().duration(750).ease(d3.easeCubicInOut) : null;
      const tr = (sel) => (T ? sel.transition(T) : sel);
      clipRect.attr("x", m.l).attr("y", 0).attr("width", Math.max(0, w - m.l - m.r) + 2).attr("height", h);

      tr(gX.attr("transform", `translate(0,${h - m.b})`)).call(d3.axisBottom(x).ticks(m.narrow ? 4 : 7).tickSizeOuter(0).tickSize(4).tickFormat(tfmt));
      const yt = o.yType === "log" ? logTicks(y) : y.ticks(m.narrow ? 4 : 6);
      tr(gY.attr("transform", `translate(${m.l},0)`)).call(d3.axisLeft(y).tickValues(yt).tickFormat(o.yFmt).tickSize(0).tickPadding(8));
      const gl = gGrid.selectAll("line").data(yt, (d) => d)
        .join((en) => en.append("line").attr("y1", (d) => y(d)).attr("y2", (d) => y(d)), (u) => u, (ex) => ex.remove())
        .attr("x1", m.l).attr("x2", w - m.r);
      tr(gl).attr("y1", (d) => y(d)).attr("y2", (d) => y(d));

      // reference line
      gRef.selectAll("*").remove();
      if (o.ref) {
        const yy = y(o.ref.v);
        gRef.append("line").attr("class", o.ref.cls || "zero").attr("x1", m.l).attr("x2", w - m.r).attr("y1", yy).attr("y2", yy);
        if (o.ref.label) gRef.append("text").attr("class", o.ref.cls === "kill" ? "kill-lab" : "annot")
          .attr("x", m.l + (w - m.l - m.r) * (o.ref.at == null ? 0 : o.ref.at) + 6).attr("y", yy + (o.ref.below ? 15 : -6)).text(o.ref.label);
      }

      // lines
      const line = d3.line().defined((p) => p.y != null).x((p) => x(p.d)).y((p) => y(p.y)).curve(d3.curveMonotoneX);
      const sel = gLines.selectAll("path.line").data(S, (s) => s.id);
      sel.exit().each(function () { d3.select(this).interrupt(); }).remove();
      const en = sel.enter().append("path").each(function () { this.__new = true; });
      en.merge(sel).attr("class", (s) => `line ${s.cls} ${s.dash || ""}`).attr("stroke-width", (s) => s.width || 2)
        .each(function (s, i) {
          const p = d3.select(this), d = line(s.points);
          const same = this.__sig === s.sig;
          if (T && same && !this.__new) { p.transition(T).attr("d", d); }
          else {
            p.interrupt().attr("d", d);
            if (!same || this.__new) {
              if (!RM) {
                hidePath(this);
                if (st.visible) drawIn(this, i * 180);
              }
            }
          }
          this.__sig = s.sig; this.__new = false;
        });

      // end labels
      const ends = [];
      S.forEach((s) => {
        const pts = s.points.filter((p) => p.y != null && p.d >= xd[0] && p.d <= xd[1]);
        if (!pts.length) return;
        const p = pts[pts.length - 1];
        ends.push({ s, p, x: x(p.d), y: y(p.y) });
      });
      ends.sort((a, b) => a.y - b.y);
      for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
      const lx = d3.max(ends, (e) => e.x) + 8;
      const eg = gEnd.selectAll("g").data(ends, (e) => e.s.id).join((en2) => {
        const g = en2.append("g");
        g.append("circle").attr("r", 3);
        g.append("text").attr("class", "endlab");
        return g;
      });
      eg.select("circle").attr("class", (e) => e.s.cls.replace("s-", "f-")).attr("cx", (e) => e.x).attr("cy", (e) => y(e.p.y));
      eg.select("text").attr("x", lx).attr("y", (e) => e.y + 4)
        .each(function (e) {
          const t = d3.select(this); t.selectAll("*").remove();
          t.append("tspan").attr("class", "v").text(o.endFmt ? o.endFmt(e.p, e.s) : "");
          if (!m.narrow) t.append("tspan").attr("dx", 6).text(e.s.short || e.s.label);
        });

      // annotations
      const ann = o.annotations ? o.annotations().filter((a) => a.d >= xd[0] && a.d <= xd[1]) : [];
      const ag = gAnn.selectAll("g").data(ann, (a) => a.key).join((en3) => {
        const g = en3.append("g");
        g.append("line").attr("class", "annot-line");
        g.append("text").attr("class", "annot");
        return g;
      });
      ag.each(function (a) {
        const g = d3.select(this), ax = x(a.d), ay = y(a.y), up = a.dy || -22;
        const anchor = ax > w - m.r - 90 ? "end" : ax < m.l + 90 ? "start" : "middle";
        g.select("line").attr("x1", ax).attr("x2", ax).attr("y1", ay + (up < 0 ? -5 : 5)).attr("y2", ay + up + (up < 0 ? 4 : -10));
        g.select("text").attr("x", ax).attr("y", ay + up).attr("text-anchor", anchor).text(a.text);
      });

      // hover
      st.dates = Array.from(new Set(S.flatMap((s) => s.points.filter((p) => p.y != null).map((p) => +p.d)))).sort((a, b) => a - b);
      overlay.attr("x", m.l).attr("y", m.t).attr("width", Math.max(0, w - m.l - m.r)).attr("height", Math.max(0, h - m.t - m.b));
    }

    overlay.on("pointermove", (ev) => {
      if (!st.x || !st.dates.length) return;
      const [mx] = d3.pointer(ev);
      const d0 = +st.x.invert(mx);
      const xd = st.x.domain();
      const ds = st.dates.filter((t) => t >= +xd[0] && t <= +xd[1]);
      if (!ds.length) return;
      const t = ds[d3.bisector((v) => v).center(ds, d0)];
      const xx = st.x(new Date(t));
      gHover.selectAll("*").remove();
      gHover.append("line").attr("class", "cross").attr("x1", xx).attr("x2", xx).attr("y1", st.y.range()[1]).attr("y2", st.y.range()[0]);
      st.S.forEach((s) => {
        const p = s.byT.get(t);
        if (p && p.y != null) gHover.append("circle").attr("class", "hoverdot " + s.cls.replace("s-", "f-")).attr("r", 4.5).attr("cx", xx).attr("cy", st.y(p.y));
      });
      showTip(o.tip(new Date(t), st.S), ev);
    }).on("pointerleave", () => { gHover.selectAll("*").remove(); hideTip(); });

    return {
      render,
      setX(dom) { st.xDom = dom; render(false); },
      reveal() {
        if (st.visible) return;
        st.visible = true;
        gLines.selectAll("path.line").each(function (s, i) { drawIn(this, i * 180); });
      },
    };
  }

  // ------------------------------------------------------------------ brush
  function Brush(el, o) {
    const svg = d3.select(el).append("svg");
    const gArea = svg.append("g");
    const gX = svg.append("g").attr("class", "axis");
    const gB = svg.append("g").attr("class", "brush");
    let x, dom = o.init || null, brush;
    function render() {
      const w = el.clientWidth || 600, h = 52, m = margins(w, o.mr || 120);
      svg.attr("viewBox", `0 0 ${w} ${h}`).attr("width", w).attr("height", h);
      const pts = o.points.filter((p) => p.y != null);
      const full = o.full;
      x = d3.scaleTime().domain(full).range([m.l, w - m.r]);
      const y = d3.scaleLinear().domain([0, d3.max(pts, (p) => p.y)]).range([h - 16, 4]);
      gArea.selectAll("*").remove();
      gArea.append("path").attr("class", "brusharea").attr("d", d3.area().x((p) => x(p.d)).y0(h - 16).y1((p) => y(p.y)).curve(d3.curveMonotoneX)(pts));
      gArea.append("path").attr("class", "brushline").attr("d", d3.line().x((p) => x(p.d)).y((p) => y(p.y)).curve(d3.curveMonotoneX)(pts));
      gX.attr("transform", `translate(0,${h - 16})`).call(d3.axisBottom(x).ticks(m.narrow ? 4 : 8).tickSize(3).tickSizeOuter(0).tickFormat(tfmt));
      brush = d3.brushX().extent([[m.l, 2], [w - m.r, h - 16]]).on("brush end", (ev) => {
        if (!ev.sourceEvent) return;
        if (!ev.selection) { dom = null; o.onChange(full); return; }
        dom = ev.selection.map(x.invert);
        o.onChange(dom);
      });
      gB.call(brush);
      gB.call(brush.move, (dom || full).map(x));
    }
    return { render };
  }

  // ------------------------------------------------------------------ segmented controls / chips
  function seg(name, onChange) {
    const g = $(`[data-ctl="${name}"]`);
    g.addEventListener("click", (ev) => {
      const b = ev.target.closest("button"); if (!b) return;
      $$("button", g).forEach((x) => x.setAttribute("aria-pressed", x === b ? "true" : "false"));
      onChange(b.dataset.v);
    });
  }
  function chips(el, series, onToggle) {
    el.innerHTML = "";
    series.forEach((s) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "chip"; b.setAttribute("aria-pressed", s.on === false ? "false" : "true");
      b.innerHTML = `<svg viewBox="0 0 22 8"><line x1="1" x2="21" y1="4" y2="4" class="line ${s.cls} ${s.dash || ""}" stroke-width="2"/></svg>${esc(s.label)}`;
      b.addEventListener("click", () => {
        const on = b.getAttribute("aria-pressed") !== "true";
        const others = series.filter((x) => x !== s && x.on !== false).length;
        if (!on && others === 0) return; // keep at least one series
        b.setAttribute("aria-pressed", on ? "true" : "false");
        onToggle(s.id, on);
      });
      el.appendChild(b);
    });
  }

  // ------------------------------------------------------------------ load
  const FILES = ["meta", "exports_monthly", "exports_quarterly", "lines", "contract", "retail", "financials", "satellite"];
  Promise.all(FILES.map((f) => fetch(`data/${f}.json`).then((r) => { if (!r.ok) throw new Error(f + ": " + r.status); return r.json(); })))
    .then((arr) => { const D = {}; FILES.forEach((f, i) => { D[f] = arr[i]; }); init(D); })
    .catch((e) => {
      console.error(e);
      document.querySelectorAll("[data-plot]").forEach((el) => { el.innerHTML = `<div class="loading err">Data failed to load (${esc(e.message)}). Serve the docs/ folder over http.</div>`; });
    });

  // ------------------------------------------------------------------ init
  function init(D) {
    const FACTS = buildFacts(D);
    bindFacts(FACTS);
    const charts = [];
    charts.push(...splitChart(D));
    charts.push(mixChart(D));
    charts.push(...priceCharts(D));
    charts.push(...nowcastCharts(D));
    const sat = satellite(D);
    if (sat) charts.push(sat);
    charts.push(dashboard(D));
    tables(D);
    charts.forEach((c) => c.render(false));
    observe(charts, FACTS);
    let lastW = window.innerWidth, t;
    window.addEventListener("resize", () => {
      clearTimeout(t);
      t = setTimeout(() => { if (window.innerWidth !== lastW) { lastW = window.innerWidth; charts.forEach((c) => c.render(false)); } }, 150);
    });
  }

  // ------------------------------------------------------------------ overview dashboard (hero tiles)
  // Small, static versions of the main figures. Same data, no controls.
  function dashboard(D) {
    const box = (key) => $(`[data-mini="${key}"]`);
    const size = (el) => { const r = el.getBoundingClientRect(); return [Math.max(120, r.width), Math.max(120, r.height)]; };
    const svgIn = (el, w, h) => { el.innerHTML = ""; return d3.select(el).append("svg").attr("viewBox", `0 0 ${w} ${h}`).attr("preserveAspectRatio", "none"); };
    const endLab = (g, x, y, txt, ink) => g.append("text").attr("class", "mini-lab" + (ink ? " ink" : "")).attr("x", x).attr("y", y).attr("text-anchor", "end").text(txt);

    function demand() {
      const el = box("demand"); if (!el) return;
      const Q = D.exports_quarterly.filter((r) => r.quarter >= "2021Q4" && r.value_usd && r.weight_kg);
      const b = Q[0], pts = Q.map((r) => ({ d: pq(r.quarter), v: (r.value_usd / b.value_usd) * 100, w: (r.weight_kg / b.weight_kg) * 100 }));
      const [w, h] = size(el), m = { t: 8, r: 4, b: 16, l: 4 };
      const x = d3.scaleTime().domain(d3.extent(pts, (p) => p.d)).range([m.l, w - m.r]);
      const y = d3.scaleLog().domain([Math.min(60, d3.min(pts, (p) => Math.min(p.v, p.w))), d3.max(pts, (p) => p.v) * 1.1]).range([h - m.b, m.t]);
      const s = svgIn(el, w, h);
      s.append("line").attr("class", "zero").attr("x1", m.l).attr("x2", w - m.r).attr("y1", y(100)).attr("y2", y(100)).attr("stroke-dasharray", "2 3");
      s.append("path").datum(pts).attr("fill", "none").attr("stroke", "var(--muted)").attr("stroke-width", 1.2).attr("vector-effect", "non-scaling-stroke").attr("d", d3.line().x((p) => x(p.d)).y((p) => y(p.w)));
      s.append("path").datum(pts).attr("fill", "none").attr("stroke", "var(--ink)").attr("stroke-width", 1.6).attr("vector-effect", "non-scaling-stroke").attr("d", d3.line().x((p) => x(p.d)).y((p) => y(p.v)));
      const L = pts[pts.length - 1];
      endLab(s, w - m.r, y(L.v) - 6, "value", true); endLab(s, w - m.r, y(L.w) - 6, "weight");
      s.append("text").attr("class", "mini-lab").attr("x", m.l).attr("y", h - 3).text(qLabel(Q[0].quarter) + " = 100");
      endLab(s, w - m.r, h - 3, qLabel(Q[Q.length - 1].quarter));
    }

    function cycle() {
      const el = box("cycle"); if (!el) return;
      const C = D.contract.filter((r) => r.mom3_pct != null);
      const [w, h] = size(el), m = { t: 10, r: 4, b: 16, l: 4 };
      const x = d3.scaleBand().domain(C.map((r) => r.month)).range([m.l, w - m.r]).padding(0.25);
      const y = d3.scaleLinear().domain([Math.min(0, d3.min(C, (r) => r.mom3_pct)), d3.max(C, (r) => r.mom3_pct) * 1.08]).range([h - m.b, m.t]);
      const s = svgIn(el, w, h), last = C[C.length - 1], peak = C.reduce((a, r) => (r.mom3_pct > a.mom3_pct ? r : a));
      s.selectAll("rect").data(C).join("rect").attr("x", (r) => x(r.month)).attr("width", x.bandwidth())
        .attr("y", (r) => y(Math.max(0, r.mom3_pct))).attr("height", (r) => Math.abs(y(r.mom3_pct) - y(0)))
        .attr("fill", (r) => (r === last ? "var(--ink)" : "var(--faint)"));
      s.append("line").attr("class", "kill").attr("x1", m.l).attr("x2", w - m.r).attr("y1", y(0)).attr("y2", y(0));
      s.append("text").attr("class", "mini-lab").attr("x", x(peak.month)).attr("y", y(peak.mom3_pct) - 3).text("peak " + pctS(peak.mom3_pct, 0));
      endLab(s, w - m.r, y(last.mom3_pct) - 4, pctS(last.mom3_pct), true);
      s.append("text").attr("class", "mini-lab").attr("x", m.l).attr("y", h - 3).text(mLabel(C[0].month));
      endLab(s, w - m.r, h - 3, mLabel(last.month));
    }

    function nowcast() {
      const el = box("nowcast"); if (!el) return;
      const B = D.financials.quarters.filter((r) => r.m2 != null);
      const [w, h] = size(el), m = { t: 8, r: 4, b: 16, l: 4 };
      const x = d3.scaleTime().domain(d3.extent(B, (r) => pq(r.quarter))).range([m.l, w - m.r]);
      const y = d3.scaleLinear().domain([0, d3.max(B, (r) => Math.max(r.actual_tn, r.m2)) * 1.08]).range([h - m.b, m.t]);
      const s = svgIn(el, w, h);
      s.append("path").datum(B).attr("fill", "none").attr("stroke", "var(--ink)").attr("stroke-width", 1.6).attr("vector-effect", "non-scaling-stroke").attr("d", d3.line().x((r) => x(pq(r.quarter))).y((r) => y(r.actual_tn)));
      s.selectAll("circle").data(B).join("circle").attr("cx", (r) => x(pq(r.quarter))).attr("cy", (r) => y(r.m2)).attr("r", 2.2)
        .attr("fill", "var(--bg)").attr("stroke", "var(--ink-2)");
      const L = B[B.length - 1];
      s.append("text").attr("class", "mini-lab ink").attr("x", m.l).attr("y", m.t + 6).text(`— actual  ${qLabel(L.quarter)} ₩${L.actual_tn.toFixed(1)}tn`);
      s.append("text").attr("class", "mini-lab").attr("x", m.l).attr("y", m.t + 20).text(`○ forecast after month 2  ₩${L.m2.toFixed(1)}tn`);
      s.append("text").attr("class", "mini-lab").attr("x", m.l).attr("y", h - 3).text(qLabel(B[0].quarter));
      endLab(s, w - m.r, h - 3, qLabel(L.quarter));
    }

    function supply() {
      const el = box("supply"); if (!el || !D.satellite.frames.length) return;
      const S = D.satellite, B = S.bounds, P = S.footprint;
      const fr = [S.frames.find((f) => f.quarter === "2022Q2") || S.frames[0], S.frames[S.frames.length - 1]];
      const pct = { l: (P.lon_min - B.lon_min) / (B.lon_max - B.lon_min) * 100, w: (P.lon_max - P.lon_min) / (B.lon_max - B.lon_min) * 100,
        t: (B.lat_max - P.lat_max) / (B.lat_max - B.lat_min) * 100, h: (P.lat_max - P.lat_min) / (B.lat_max - B.lat_min) * 100 };
      el.innerHTML = `<div class="pair">${fr.map((f) => `<figure><img src="${f.img}" alt="Sentinel-2, M15X area, ${f.date}" loading="eager">
        <span class="fp" style="left:${pct.l}%;top:${pct.t}%;width:${pct.w}%;height:${pct.h}%"></span>
        <figcaption>${qLabel(f.quarter)}</figcaption></figure>`).join("")}</div>`;
      // keep the footprint box aligned: images fill each cell without cropping
      $$(".pair img", el).forEach((im) => { im.style.objectFit = "fill"; });
    }

    let drawn = false;
    return {
      el: $(".dash"),
      render() { demand(); cycle(); nowcast(); if (!drawn) { supply(); drawn = true; } },
      reveal() {},
    };
  }

  function buildFacts(D) {
    const h = D.meta.headline, e = h.exports, c = h.contract, u = h.export_uv_momentum, L = D.financials.last;
    const sc = Object.fromEntries(D.financials.scorecard.map((s) => [s.model, s]));
    const rd = D.financials.revenue_file_differences[0];
    const S = D.meta.series;
    return {
      eQ: [e.quarter, "q"], ePQ: [e.prior_quarter, "q"],
      valMult: [e.value_multiple, "x2"], valYoy: [e.yoy_value_pct, "pct1s"], wtYoy: [e.yoy_weight_pct, "pct1s"],
      uv: [e.usd_per_g, "usd2"], uvPrior: [e.usd_per_g_prior, "usd2"], uvShare: [e.share_from_unitvalue_pct, "pct0"],
      uvYoyQ: [e.yoy_uv_pct, "pct0s"],
      dramUv: [e.dram_usd_per_g, "usd2"], dramUvPrior: [e.dram_usd_per_g_prior, "usd2"],
      dramMult: [e.dram_usd_per_g / e.dram_usd_per_g_prior, "x1"],
      dramContrib: [e.line_contribution_pct["DRAM"], "pct0"], compContrib: [e.line_contribution_pct["Composite-chip ICs"], "pct0"],
      dramQoq: [e.dram_uv_qoq_pct, "pct1s"],
      cFirstM: [c.first_month, "m"], cFirst: [c.first_usd, "usd2"], cLastM: [c.last_month, "m"], cLast: [c.last_usd, "usd2"],
      m3Peak: [c.mom3_peak_pct, "pct0s"], m3PeakM: [c.mom3_peak_month, "m"], m3Last: [c.mom3_last_pct, "pct1s"], m3LastM: [c.mom3_last_month, "m"],
      rampFrom: [c.ramp_from_usd, "usd2"], rampFromM: [c.ramp_from_month, "m"],
      uvmPeak: [u.peak_pct, "pct1s"], uvmPeakM: [u.peak_month, "m"], uvmLast: [u.last_pct, "pct1s"], uvmLastM: [u.last_month, "m"],
      ncQ: [L.quarter, "q"], actual: [L.actual_tn * 1e6, "tn1"],
      lM1: [L.m1 * 1e6, "tn1"], lM2: [L.m2 * 1e6, "tn1"], lM3: [L.m3 * 1e6, "tn1"],
      release: [L.earnings_release_date, "str"],
      leadM2: [L.lead.m2.days, "int"], leadM2W: [L.lead.m2.days, "weeks"],
      mapeM1: [sc.m1.mape, "pct1"], mapeM2: [sc.m2.mape, "pct1"], mapeM3: [sc.m3.mape, "pct1"], mapeBase: [sc.baseline.mape, "pct1"],
      hitsM1: [sc.m1.hits, "int"], hitsM2: [sc.m2.hits, "int"], hitsM3: [sc.m3.hits, "int"], hitsBase: [sc.baseline.hits, "int"],
      worstM2: [sc.m2.worst_ape, "pct0a"], nQtd: [sc.m2.n, "int"],
      btFirst: [S.qtd_backtest.first, "q"], btLast: [S.qtd_backtest.last, "q"],
      exportsLastM: [S.korean_exports_hs854232.last, "m"], exFirst: [S.korean_exports_hs854232.first, "m"],
      asOf: [D.meta.as_of, "str"], generated: [D.meta.generated_utc.slice(0, 10), "str"],
      revDiff: [rd ? Math.abs(rd.company_file - rd.stockanalysis) : 0, "krwbn"],
      satFirst: [S.m15x_sentinel2.first, "q"], satLast: [S.m15x_sentinel2.last, "q"], satLastDate: [S.m15x_sentinel2.last_scene_date, "str"],
      satMinClear: [D.satellite.min_site_clear * 100, "pct0"],
      satPx: [D.satellite.site_pixels, "int"],
      satKm: [D.satellite.extent_km.ew.toFixed(1) + " × " + D.satellite.extent_km.ns.toFixed(1) + " km", "str"],
      // states for the kill-signal table
      _state: {
        m3Last: c.mom3_last_pct < 0, uvmLast: u.last_pct < 0,
        mixShift: e.yoy_uv_pct < e.yoy_weight_pct, dramQoq: e.dram_uv_qoq_pct < 0,
      },
    };
  }

  function bindFacts(FACTS) {
    $$("[data-f]").forEach((el) => {
      const f = FACTS[el.dataset.f];
      if (!f || f[0] == null) { el.textContent = "–"; console.warn("missing fact", el.dataset.f); return; }
      el.textContent = F[f[1]](f[0]);
    });
    $$("[data-state]").forEach((el) => {
      const trig = FACTS._state[el.dataset.state];
      el.textContent = trig ? "Triggered" : "Not triggered";
      el.classList.add(trig ? "watch" : "ok");
    });
  }

  function countUp(el, FACTS) {
    const f = FACTS[el.dataset.f];
    if (!f || typeof f[0] !== "number" || RM) return;
    const [v, fmt] = f;
    d3.select(el).transition().duration(1600).ease(d3.easeCubicOut)
      .tween("text", () => { const i = d3.interpolateNumber(0, v); return (t) => { el.textContent = F[fmt](i(t)); }; });
  }

  function observe(charts, FACTS) {
    const byEl = new Map();
    charts.forEach((c) => { if (c.el) byEl.set(c.el, c); });
    if (!("IntersectionObserver" in window)) {
      charts.forEach((c) => c.reveal && c.reveal());
      $$(".reveal").forEach((e) => e.classList.add("in"));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        const t = en.target;
        io.unobserve(t);
        if (t.classList.contains("reveal")) t.classList.add("in");
        if (byEl.has(t)) byEl.get(t).reveal();
        $$("[data-count]", t).forEach((x) => countUp(x, FACTS));
      });
    }, { threshold: 0.2 });
    $$(".reveal").forEach((e) => io.observe(e));
    byEl.forEach((c, el) => io.observe(el));
    $$(".stats").forEach((e) => io.observe(e));
  }

  // ------------------------------------------------------------------ FIG 1.1 split
  function splitChart(D) {
    const fig = $("#fig-split"), el = $("[data-plot]", fig), bel = $("[data-brush]", fig);
    const Q = D.exports_quarterly.filter((r) => r.dln_value != null).map((r) => ({
      key: r.quarter, d: pq(r.quarter), w: r.dln_weight, u: r.dln_unitvalue, v: r.dln_value,
      lab: qLabel(r.quarter) + " vs " + qLabel((+r.quarter.slice(0, 4) - 1) + r.quarter.slice(4)),
      vy: r.yoy_value_pct, wy: r.yoy_weight_pct, uy: r.yoy_uv_pct, usd: r.value_usd, upg: r.usd_per_g, days: 91,
    }));
    const M = D.exports_monthly.filter((r) => r.r3_yoy_val_pct != null).map((r) => ({
      key: r.month, d: pm(r.month), w: Math.log(1 + r.r3_yoy_wt_pct / 100), u: Math.log(1 + r.r3_yoy_uv_pct / 100),
      v: Math.log(1 + r.r3_yoy_val_pct / 100), lab: "3 months to " + mLabel(r.month) + ", YoY",
      vy: r.r3_yoy_val_pct, wy: r.r3_yoy_wt_pct, uy: r.r3_yoy_uv_pct, usd: r.r3_value_usd, upg: r.r3_usd_per_g, days: 30.4,
    }));
    const full = [pm(D.exports_monthly[0].month), pm(D.exports_monthly[D.exports_monthly.length - 1].month)];
    const st = { freq: "Q", xDom: [new Date(2017, 0, 1), full[1]], visible: false };

    const svg = d3.select(el).append("svg").attr("role", "img").attr("aria-label", "Export value growth split into weight and unit value");
    const cid = "clipsplit";
    const clip = svg.append("defs").append("clipPath").attr("id", cid).append("rect");
    const gGrid = svg.append("g").attr("class", "grid"), gX = svg.append("g").attr("class", "axis"), gY = svg.append("g").attr("class", "axis");
    const gBars = svg.append("g").attr("clip-path", `url(#${cid})`);
    const gZero = svg.append("g"), gTot = svg.append("g").attr("clip-path", `url(#${cid})`), gLeg = svg.append("g"), gAnn = svg.append("g");
    const gHover = svg.append("g").style("pointer-events", "none");
    const overlay = svg.append("rect").attr("fill", "transparent").style("touch-action", "pan-y");
    let cur = {};

    const pctTicks = [-0.75, -0.5, 0, 0.5, 1, 2, 3, 4, 5];
    function render(anim) {
      const w = el.clientWidth || 600, h = Math.max(300, Math.min(520, w * 0.48)), m = margins(w, 28);
      svg.attr("viewBox", `0 0 ${w} ${h}`).attr("width", w).attr("height", h);
      const data = st.freq === "Q" ? Q : M;
      const x = d3.scaleTime().domain(st.xDom).range([m.l, w - m.r]);
      const vis = data.filter((r) => r.d >= st.xDom[0] && r.d <= st.xDom[1]);
      const stacks = (r) => { let pos = 0, neg = 0; return [["w", r.w], ["u", r.u]].map(([k, v]) => { let a, b; if (v >= 0) { a = pos; b = pos + v; pos = b; } else { a = neg; b = neg + v; neg = b; } return { k, a, b, r }; }); };
      const lo = d3.min(vis, (r) => Math.min(0, r.w < 0 ? r.w : 0) + Math.min(0, r.u < 0 ? r.u : 0)) || -0.2;
      const hi = d3.max(vis, (r) => Math.max(0, r.w) + Math.max(0, r.u)) || 0.2;
      const y = d3.scaleLinear().domain([Math.min(lo, d3.min(vis, (r) => r.v) || 0) * 1.08, Math.max(hi, d3.max(vis, (r) => r.v) || 0) * 1.08]).range([h - m.b, m.t + 26]);
      cur = { x, y, data: vis, m, w, h };
      const T = anim && !RM ? d3.transition().duration(750).ease(d3.easeCubicInOut) : null;
      const tr = (s) => (T ? s.transition(T) : s);
      clip.attr("x", m.l).attr("y", 0).attr("width", w - m.l - m.r).attr("height", h);
      tr(gX.attr("transform", `translate(0,${h - m.b})`)).call(d3.axisBottom(x).ticks(m.narrow ? 4 : 8).tickSize(4).tickSizeOuter(0));
      const yt = pctTicks.map((p) => Math.log(1 + p)).filter((v) => v >= y.domain()[0] && v <= y.domain()[1]);
      tr(gY.attr("transform", `translate(${m.l},0)`)).call(d3.axisLeft(y).tickValues(yt).tickSize(0).tickPadding(8)
        .tickFormat((v) => { const p = Math.round((Math.exp(v) - 1) * 100); return (p > 0 ? "+" : p < 0 ? "−" : "") + Math.abs(p) + "%"; }));
      const gl = gGrid.selectAll("line").data(yt, (d) => d).join("line").attr("x1", m.l).attr("x2", w - m.r);
      tr(gl).attr("y1", (d) => y(d)).attr("y2", (d) => y(d));
      gZero.selectAll("line").data([0]).join("line").attr("class", "zero").attr("x1", m.l).attr("x2", w - m.r);
      tr(gZero.selectAll("line")).attr("y1", y(0)).attr("y2", y(0));

      const px = (r) => x(new Date(+r.d + r.days * 864e5)) - x(r.d);
      const bw = (r) => Math.max(1, px(r) * (st.freq === "Q" ? 0.7 : 0.78));
      const segs = data.flatMap(stacks);
      const hidden = !st.visible && !RM;
      const bars = gBars.selectAll("rect").data(segs, (s) => st.freq + s.r.key + s.k);
      bars.exit().remove();
      const benter = bars.enter().append("rect")
        .attr("fill", (s) => (s.k === "u" ? "#e8e8e4" : "#5d5d59"))
        .attr("x", (s) => x(s.r.d) - bw(s.r) / 2).attr("width", (s) => bw(s.r))
        .attr("y", y(0)).attr("height", 0);
      const ball = benter.merge(bars);
      ball.attr("x", (s) => x(s.r.d) - bw(s.r) / 2).attr("width", (s) => bw(s.r));
      const setY = (sel) => sel.attr("y", (s) => y(Math.max(s.a, s.b))).attr("height", (s) => Math.max(0, Math.abs(y(s.a) - y(s.b)) - (s.k === "u" && s.a !== 0 ? 1 : 0)));
      if (hidden) { /* grow on reveal */ }
      else if (T) setY(ball.transition(T).delay((s, i) => (benter.nodes().includes(ball.nodes()[i]) ? 0 : 0)));
      else setY(ball);
      if (!hidden && !T) setY(benter);

      const tot = gTot.selectAll("circle").data(data, (r) => st.freq + r.key);
      tot.exit().remove();
      const tall = tot.enter().append("circle").attr("class", "f-accent").attr("r", st.freq === "Q" ? 3.2 : 1.8).attr("opacity", 0).merge(tot);
      tall.attr("cx", (r) => x(r.d)).attr("cy", (r) => y(r.v)).attr("r", st.freq === "Q" ? 3.2 : 1.8);
      if (!hidden) (T ? tall.transition(T) : tall).attr("opacity", 1);

      // legend
      gLeg.selectAll("*").remove();
      const items = [["Unit value", "rect", "#e8e8e4"], ["Weight", "rect", "#5d5d59"], ["Value (sum)", "dot", null]];
      let lx = m.l;
      items.forEach(([t, kind, c]) => {
        const g = gLeg.append("g").attr("transform", `translate(${lx},8)`);
        if (kind === "rect") g.append("rect").attr("width", 10).attr("height", 10).attr("fill", c);
        else g.append("circle").attr("class", "f-accent").attr("cx", 5).attr("cy", 5).attr("r", 3.5);
        g.append("text").attr("class", "annot").attr("x", 16).attr("y", 9).text(t);
        lx += 16 + t.length * 6.6 + 18;
      });

      // annotation on latest
      const last = vis[vis.length - 1];
      gAnn.selectAll("*").remove();
      if (last) {
        const ax = x(last.d), ay = y(Math.max(last.v, last.w + last.u));
        gAnn.append("text").attr("class", "annot").attr("x", ax).attr("y", ay - 10).attr("text-anchor", "end")
          .text(`${st.freq === "Q" ? qLabel(last.key) : mLabel(last.key)}: value ${pctS(last.vy, 0)}, weight ${pctS(last.wy, 0)}`);
      }
      overlay.attr("x", m.l).attr("y", m.t).attr("width", w - m.l - m.r).attr("height", h - m.t - m.b);
      cur.setY = setY; cur.ball = ball; cur.tall = tall;
    }
    overlay.on("pointermove", (ev) => {
      const { x, y, data } = cur; if (!data || !data.length) return;
      const [mx] = d3.pointer(ev);
      const i = d3.bisector((r) => +r.d).center(data, +x.invert(mx));
      const r = data[i];
      gHover.selectAll("*").remove();
      gHover.append("line").attr("class", "cross").attr("x1", x(r.d)).attr("x2", x(r.d)).attr("y1", y.range()[1]).attr("y2", y.range()[0]);
      showTip(tipHtml(r.lab, [
        ["Value", pctS(r.vy)], ["Weight", pctS(r.wy)], ["Unit value", pctS(r.uy)],
        ["Exports", "$" + (r.usd / 1e9).toFixed(1) + "bn"], ["$ per gram", "$" + r.upg.toFixed(2)],
      ], "HS 854232 · " + (r.d < new Date(2021, 9, 1) ? "UN Comtrade" : "Korea Customs Service")), ev);
    }).on("pointerleave", () => { gHover.selectAll("*").remove(); hideTip(); });

    seg("split-freq", (v) => { st.freq = v; render(true); });
    const brush = Brush(bel, {
      points: D.exports_monthly.map((r) => ({ d: pm(r.month), y: r.value_usd / 1e9 })), full, init: st.xDom, mr: 28,
      onChange: (dom) => { st.xDom = dom; render(false); },
    });
    const chart = {
      el: fig, render,
      reveal() {
        if (st.visible) return; st.visible = true;
        if (RM) { render(false); return; }
        const n = cur.ball.size();
        cur.setY(cur.ball.transition().duration(900).delay((s, i) => (i / n) * 700).ease(d3.easeCubicOut));
        cur.tall.transition().delay(900).duration(600).attr("opacity", 1);
      },
    };
    return [chart, { render: () => brush.render() }];
  }

  // ------------------------------------------------------------------ FIG 1.2 mix
  function mixChart(D) {
    const fig = $("#fig-mix"), el = $("[data-plot]", fig);
    const L = D.lines;
    const style = {
      "DRAM": { cls: "s-accent", dash: "" },
      "Composite-chip ICs": { cls: "s-ink", dash: "" },
      "Flash": { cls: "s-grey", dash: "s-dash" },
      "Other": { cls: "s-dim", dash: "s-dot" },
    };
    const st = { metric: "uv", freq: "Q", on: { "DRAM": true, "Composite-chip ICs": true, "Flash": true, "Other": true } };
    const MET = {
      uv: { f: (p) => p.uv, unit: "$ per gram", fmt: (v) => "$" + v.toFixed(2), axis: (v) => "$" + v },
      v: { f: (p) => p.v / 1e9, unit: "Export value, $bn per " + "period", fmt: (v) => "$" + v.toFixed(2) + "bn", axis: (v) => "$" + v },
      w: { f: (p) => p.w / 1e3, unit: "Export weight, tonnes per period", fmt: (v) => v.toFixed(1) + " t", axis: (v) => v },
    };
    const series = () => L.groups.map((g) => {
      const src = st.freq === "Q" ? L.quarterly[g] : L.monthly_r3[g];
      return {
        id: g, label: g, short: g === "Composite-chip ICs" ? "Composite" : g, cls: style[g].cls, dash: style[g].dash, on: st.on[g],
        sig: st.metric + st.freq,
        points: src.map((p) => ({ d: st.freq === "Q" ? pq(p.p) : pm(p.p), y: p.w ? MET[st.metric].f(p) : null, raw: p })),
      };
    });
    const chart = LineChart(el, {
      aria: "Export unit value by HS10 line",
      height: (w) => Math.max(280, Math.min(460, w * 0.42)), mr: 130, includeZero: true,
      series, yFmt: (v) => MET[st.metric].axis(v),
      endFmt: (p) => MET[st.metric].fmt(p.y),
      tip: (d, S) => {
        const any = S.map((s) => s.byT.get(+d)).find(Boolean);
        const title = st.freq === "Q" ? qLabel(any.raw.p) : "3 months to " + mLabel(any.raw.p);
        return tipHtml(title, S.map((s) => { const p = s.byT.get(+d); return [s.label, p && p.y != null ? MET[st.metric].fmt(p.y) : "–", s]; }),
          "Korea Customs Service, HS10 lines; value and weight summed before dividing");
      },
    });
    const unit = $("[data-unit]", fig);
    const setUnit = () => { unit.textContent = MET[st.metric].unit.replace("period", st.freq === "Q" ? "quarter" : "3 months") + (st.freq === "M" ? " · rolling 3-month sums" : ""); };
    chips($("[data-chips]", fig), L.groups.map((g) => ({ id: g, label: g, cls: style[g].cls, dash: style[g].dash, on: true })),
      (id, on) => { st.on[id] = on; chart.render(true); });
    seg("mix-metric", (v) => { st.metric = v; setUnit(); chart.render(true); });
    seg("mix-freq", (v) => { st.freq = v; setUnit(); chart.render(true); });
    setUnit();
    return { el: fig, render: chart.render, reveal: chart.reveal };
  }

  // ------------------------------------------------------------------ FIG 2.1 / 2.2 prices & momentum
  function priceCharts(D) {
    const fig1 = $("#fig-price"), fig2 = $("#fig-mom");
    const C = D.contract, EM = D.exports_monthly, EQ = D.exports_quarterly, R = D.retail;
    const startM = "2024-08";
    const st = { freq: "M", on: { contract: true, export: true, ddr4: true, ddr5: true } };

    // monthly raw series
    const mC = C.map((r) => ({ k: r.month, v: r.avg_usd, src: r }));
    const mE = EM.filter((r) => r.month >= startM).map((r) => ({ k: r.month, v: r.r3_usd_per_g, mom: r.r3_uv_mom3_pct }));
    const mR4 = R["DDR4 (Keepa)"].filter((r) => r.month >= startM).map((r) => ({ k: r.month, v: r.usd_per_gb }));
    const mR5 = R["DDR5 (Keepa)"].filter((r) => r.month >= startM).map((r) => ({ k: r.month, v: r.usd_per_gb }));
    // quarterly: averages of available months (contract, retail); sums-then-divide for exports
    const qAvg = (rows) => {
      const g = d3.groups(rows.filter((r) => r.v != null), (r) => quarterOf(r.k));
      return g.map(([q, rs]) => ({ k: q, v: d3.mean(rs, (r) => r.v), n: rs.length })).sort((a, b) => d3.ascending(a.k, b.k));
    };
    const qC = qAvg(mC), qR4 = qAvg(mR4), qR5 = qAvg(mR5);
    const qE = EQ.filter((r) => r.quarter >= "2024Q3").map((r) => ({ k: r.quarter, v: r.usd_per_g, n: 3, qoq: r.uv_qoq_pct }));
    const base = (rows, key) => { const b = rows.find((r) => r.k === key); return b ? b.v : null; };

    const defs = {
      contract: { label: "DDR4 8Gb contract", short: "Contract", cls: "s-ink", dash: "", unit: (v) => "$" + v.toFixed(2) },
      export: { label: "Export unit value", short: "Export UV", cls: "s-grey", dash: "s-dash", unit: (v) => "$" + v.toFixed(2) + "/g" },
      ddr4: { label: "Retail DDR4 (Keepa)", short: "Retail DDR4", cls: "s-dim", dash: "s-dot", unit: (v) => "$" + v.toFixed(2) + "/GB" },
      ddr5: { label: "Retail DDR5 (Keepa)", short: "Retail DDR5", cls: "s-dim", dash: "", unit: (v) => "$" + v.toFixed(2) + "/GB", width: 1.25 },
    };
    function priceSeries() {
      const Qm = st.freq === "Q";
      const raw = Qm ? { contract: qC, export: qE, ddr4: qR4, ddr5: qR5 } : { contract: mC, export: mE, ddr4: mR4, ddr5: mR5 };
      const bk = Qm ? "2025Q1" : "2025-01";
      return Object.keys(defs).map((id) => {
        const b = base(raw[id], bk);
        return Object.assign({ id, on: st.on[id], sig: st.freq }, defs[id], {
          points: raw[id].map((r) => ({ d: Qm ? pq(r.k) : pm(r.k), y: r.v != null && b ? (r.v / b) * 100 : null, raw: r })),
        });
      });
    }
    const domFull = [pm(startM), pm(C[C.length - 1].month)];
    const priceTip = (d, S) => {
      const Qm = st.freq === "Q";
      const any = S.map((s) => s.byT.get(+d)).find(Boolean);
      const k = any.raw.k;
      const rows = S.map((s) => {
        const p = s.byT.get(+d);
        if (!p || p.y == null) return [s.short, "–", s];
        let txt = s.unit(p.raw.v) + " · " + Math.round(p.y);
        if (Qm && p.raw.n != null && p.raw.n < 3) txt += ` (${p.raw.n}/3 mo)`;
        return [s.short, txt, s];
      });
      let src = "Index = 100 at " + (Qm ? "2025Q1" : "Jan 2025") + ".";
      const c = S.find((s) => s.id === "contract");
      const cp = c && c.byT.get(+d);
      if (!Qm && cp && cp.raw.src && cp.raw.src.source) {
        const r = cp.raw.src;
        src += `<br>Contract: ${esc(r.source)}, published ${esc(r.publication_date)}` + (r.flag ? `<br>Note: ${esc(r.flag)}` : "");
      }
      src += "<br>Export UV: Korea Customs, HS 854232" + (Qm ? "" : ", 3-month sums") + ". Retail: Keepa via Stanford DAM.";
      return tipHtml(Qm ? qLabel(k) : mLabel(k), rows, src);
    };
    const price = LineChart($("[data-plot]", fig1), {
      aria: "Indexed DDR4 contract price, export unit value and retail prices",
      height: (w) => Math.max(300, Math.min(500, w * 0.46)), mr: 150, yType: "log",
      xFull: () => domFull, series: priceSeries, yFmt: (v) => d3.format(",")(v),
      ref: { v: 100, cls: "zero", label: "" },
      endFmt: (p) => d3.format(",")(Math.round(p.y)),
      tip: priceTip,
    });
    chips($("[data-chips]", fig1), Object.keys(defs).map((id) => Object.assign({ id, on: true }, defs[id])),
      (id, on) => { st.on[id] = on; price.render(true); });

    // momentum
    const momSeries = () => {
      const Qm = st.freq === "Q";
      let cpts, epts;
      if (Qm) {
        cpts = qC.map((r, i) => ({ d: pq(r.k), y: i > 0 ? (r.v / qC[i - 1].v - 1) * 100 : null, raw: r }));
        epts = qE.map((r) => ({ d: pq(r.k), y: r.qoq, raw: r }));
      } else {
        cpts = C.map((r) => ({ d: pm(r.month), y: r.mom3_pct, raw: { k: r.month, v: r.avg_usd } }));
        epts = mE.map((r) => ({ d: pm(r.k), y: r.mom, raw: r }));
      }
      return [
        { id: "c", label: "DDR4 8Gb contract", short: "Contract", cls: "s-ink", dash: "", points: cpts, sig: st.freq },
        { id: "e", label: "Export unit value", short: "Export UV", cls: "s-grey", dash: "s-dash", points: epts, sig: st.freq },
      ];
    };
    const H = D.meta.headline;
    const mom = LineChart($("[data-plot]", fig2), {
      aria: "Three-month momentum of contract price and export unit value",
      height: (w) => Math.max(260, Math.min(420, w * 0.36)), mr: 150, xFull: () => domFull,
      series: momSeries, yFmt: (v) => (v > 0 ? "+" : "") + v + "%",
      ref: { v: 0, cls: "kill", label: "Kill signal: below 0%", at: 0.55, below: true },
      endFmt: (p) => pctS(p.y),
      annotations: () => st.freq === "Q" ? [] : [
        { key: "cp", d: pm(H.contract.mom3_peak_month), y: H.contract.mom3_peak_pct, text: "Contract peak " + pctS(H.contract.mom3_peak_pct, 0), dy: -16 },
        { key: "ep", d: pm(H.export_uv_momentum.peak_month), y: H.export_uv_momentum.peak_pct, text: "Export peak " + pctS(H.export_uv_momentum.peak_pct, 0), dy: -26 },
      ],
      tip: (d, S) => {
        const Qm = st.freq === "Q";
        const any = S.map((s) => s.byT.get(+d)).find(Boolean);
        const rows = S.map((s) => { const p = s.byT.get(+d); return [s.short, p && p.y != null ? pctS(p.y) : "–", s]; });
        const note = Qm ? "Quarter-on-quarter change. Contract uses the average of reported months." : "Change vs 3 months earlier. Contract blank where a month is missing.";
        return tipHtml(Qm ? qLabel(any.raw.k) : mLabel(any.raw.k), rows, note);
      },
    });
    const momUnit = $("[data-unit]", fig2);
    seg("price-freq", (v) => {
      st.freq = v;
      momUnit.textContent = v === "Q" ? "% change vs previous quarter" : "% change vs 3 months earlier";
      $("[data-unit]", fig1).textContent = (v === "Q" ? "Index, 2025Q1 = 100" : "Index, Jan 2025 = 100") + " · log scale";
      price.render(true); mom.render(true);
    });
    const brush = Brush($("[data-brush]", fig2), {
      points: C.map((r) => ({ d: pm(r.month), y: r.avg_usd })).concat([]), full: domFull, mr: 150,
      onChange: (dom) => { price.setX(dom); mom.setX(dom); },
    });
    return [
      { el: fig1, render: price.render, reveal: price.reveal },
      { el: fig2, render: mom.render, reveal: mom.reveal },
      { render: () => brush.render() },
    ];
  }

  // ------------------------------------------------------------------ FIG 3.1 / 3.2 quarter-to-date forecast
  function nowcastCharts(D) {
    const FQ = D.financials.quarters.filter((q) => q.m1 != null);
    const SC = Object.fromEntries(D.financials.scorecard.map((s) => [s.model, s]));
    const MLAB = { m1: "After month 1", m2: "After month 2", m3: "Full quarter" };

    // ---- FIG 3.1 error by month
    const efig = $("#fig-err"), eel = $("[data-plot]", efig);
    const esvg = d3.select(eel).append("svg").attr("role", "img").attr("aria-label", "Forecast error after one, two and three months");
    let eVisible = false, eCur = {};
    function renderErr() {
      const w = eel.clientWidth || 600, h = Math.max(260, Math.min(400, w * 0.36)), m = margins(w, 20);
      m.r = m.narrow ? 12 : 24; m.t = 34;
      esvg.attr("viewBox", `0 0 ${w} ${h}`).attr("width", w).attr("height", h);
      esvg.selectAll("*").remove();
      const keys = ["m1", "m2", "m3"];
      const x = d3.scaleBand().domain(keys).range([m.l, w - m.r]).padding(m.narrow ? 0.35 : 0.5);
      const ymax = d3.max(keys.concat("baseline"), (k) => (k === "baseline" ? SC[k].mape : SC[k].worst_ape));
      const y = d3.scaleLinear().domain([0, ymax * 1.15]).nice().range([h - m.b - 16, m.t]);
      const yt = y.ticks(m.narrow ? 4 : 5);
      esvg.append("g").attr("class", "grid").selectAll("line").data(yt).join("line").attr("x1", m.l).attr("x2", w - m.r).attr("y1", (d) => y(d)).attr("y2", (d) => y(d));
      esvg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).tickValues(yt).tickSize(0).tickPadding(8).tickFormat((v) => v + "%"));
      esvg.append("g").attr("class", "axis").attr("transform", `translate(0,${h - m.b - 16})`).call(d3.axisBottom(x).tickSize(0).tickPadding(8).tickFormat((k) => MLAB[k]));
      esvg.append("g").selectAll("text").data(keys).join("text").attr("class", "annot").attr("text-anchor", "middle")
        .attr("x", (k) => x(k) + x.bandwidth() / 2).attr("y", h - 6).text((k) => `${SC[k].hits}/${SC[k].n} up/down right`);
      const bars = esvg.append("g").selectAll("rect").data(keys).join("rect")
        .attr("x", (k) => x(k)).attr("width", x.bandwidth())
        .attr("fill", (k) => (k === "m2" ? "#e8e8e4" : "#5d5d59"))
        .attr("y", y(0)).attr("height", 0);
      const worst = esvg.append("g").attr("opacity", 0);
      keys.forEach((k) => {
        const cx = x(k) + x.bandwidth() / 2, wy = y(SC[k].worst_ape);
        worst.append("line").attr("x1", cx).attr("x2", cx).attr("y1", y(SC[k].mape)).attr("y2", wy).attr("class", "annot-line").attr("stroke-dasharray", "2 2");
        worst.append("line").attr("x1", cx - 8).attr("x2", cx + 8).attr("y1", wy).attr("y2", wy).attr("stroke", "#9b9b97").attr("stroke-width", 1.5);
        worst.append("text").attr("class", "annot").attr("x", cx + 12).attr("y", wy + 4).text((m.narrow ? "" : "worst ") + SC[k].worst_ape.toFixed(1) + "%");
      });
      const vals = esvg.append("g").attr("opacity", 0);
      keys.forEach((k) => vals.append("text").attr("class", "endlab").attr("text-anchor", "middle")
        .attr("x", x(k) + x.bandwidth() / 2).attr("y", y(SC[k].mape) - 8).append("tspan").attr("class", "v").text(SC[k].mape.toFixed(1) + "%"));
      const by = y(SC.baseline.mape);
      esvg.append("line").attr("class", "kill").attr("x1", m.l).attr("x2", w - m.r).attr("y1", by).attr("y2", by);
      esvg.append("text").attr("class", "kill-lab").attr("x", m.l + 6).attr("y", by + 15)
        .text(m.narrow ? `Baseline ${SC.baseline.mape.toFixed(1)}%` : `Baseline (last growth repeats) ${SC.baseline.mape.toFixed(1)}% · ${SC.baseline.hits}/${SC.baseline.n} right`);
      esvg.append("g").selectAll("rect").data(keys).join("rect").attr("fill", "transparent")
        .attr("x", (k) => x(k) - 10).attr("width", x.bandwidth() + 20).attr("y", m.t).attr("height", h - m.t - m.b)
        .on("pointermove", (ev, k) => showTip(tipHtml(MLAB[k], [["Mean abs. error", SC[k].mape.toFixed(1) + "%"], ["Median", SC[k].median_ape.toFixed(1) + "%"],
          ["Worst quarter", SC[k].worst_ape.toFixed(1) + "%"], ["Up/down right", SC[k].hits + "/" + SC[k].n]], `${SC[k].n} quarters, ${D.financials.backtest_first}–${D.financials.backtest_last}`), ev))
        .on("pointerleave", hideTip);
      eCur = { bars, worst, vals, y };
      if (eVisible || RM) show(false);
    }
    function show(anim) {
      const { bars, worst, vals, y } = eCur;
      const set = (s) => s.attr("y", (k) => y(SC[k].mape)).attr("height", (k) => y(0) - y(SC[k].mape));
      if (anim && !RM) {
        set(bars.transition().duration(900).delay((k, i) => i * 160).ease(d3.easeCubicOut));
        worst.transition().delay(800).duration(500).attr("opacity", 1);
        vals.transition().delay(800).duration(500).attr("opacity", 1);
      } else { set(bars); worst.attr("opacity", 1); vals.attr("opacity", 1); }
    }
    const errChart = { el: efig, render: renderErr, reveal() { if (eVisible) return; eVisible = true; show(true); } };

    // ---- FIG 3.2 forecast vs actual
    const fig = $("#fig-nowcast"), el = $("[data-plot]", fig);
    const st = { model: "m2", visible: false };
    const svg = d3.select(el).append("svg").attr("role", "img").attr("aria-label", "SK hynix revenue vs quarter-to-date forecast");
    svg.append("defs").append("pattern").attr("id", "hatch").attr("width", 6).attr("height", 6).attr("patternUnits", "userSpaceOnUse").attr("patternTransform", "rotate(45)")
      .call((p) => { p.append("rect").attr("width", 6).attr("height", 6).attr("fill", "#2a2a28"); p.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 6).attr("stroke", "#6a6a66").attr("stroke-width", 2); });
    const gGrid = svg.append("g").attr("class", "grid"), gX = svg.append("g").attr("class", "axis"), gY = svg.append("g").attr("class", "axis");
    const gBars = svg.append("g"), gNc = svg.append("g"), gLab = svg.append("g"), gLeg = svg.append("g"), gHit = svg.append("g");
    let cur = {};
    function render(anim) {
      const w = el.clientWidth || 600, h = Math.max(300, Math.min(480, w * 0.44)), m = margins(w, 20);
      m.r = m.narrow ? 12 : 20; m.t = 30;
      svg.attr("viewBox", `0 0 ${w} ${h}`).attr("width", w).attr("height", h);
      const x = d3.scaleBand().domain(FQ.map((q) => q.quarter)).range([m.l, w - m.r]).padding(0.28);
      const key = st.model;
      const ymax = d3.max(FQ, (q) => Math.max(q.actual_tn, q.m1, q.m2, q.m3));
      const y = d3.scaleLinear().domain([0, ymax * 1.08]).nice().range([h - m.b, m.t + 10]);
      cur = { x, y };
      const T = anim && !RM ? d3.transition().duration(700).ease(d3.easeCubicInOut) : null;
      const tr = (s) => (T ? s.transition(T) : s);
      gX.attr("transform", `translate(0,${h - m.b})`).call(d3.axisBottom(x).tickSize(0).tickPadding(8)
        .tickValues(FQ.map((q) => q.quarter).filter((q, i) => (m.narrow ? q.endsWith("Q1") || i === FQ.length - 1 : q.endsWith("Q1") || q.endsWith("Q3"))))
        .tickFormat((q) => (q.endsWith("Q1") ? q.slice(0, 4) : q.slice(4))));
      const yt = y.ticks(m.narrow ? 4 : 6);
      gY.attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).tickValues(yt).tickSize(0).tickPadding(8).tickFormat((v) => "₩" + v));
      gGrid.selectAll("line").data(yt, (d) => d).join("line").attr("x1", m.l).attr("x2", w - m.r).attr("y1", (d) => y(d)).attr("y2", (d) => y(d));

      const hidden = !st.visible && !RM;
      const bars = gBars.selectAll("rect").data(FQ, (q) => q.quarter).join("rect")
        .attr("fill", (q) => (q.preliminary ? "url(#hatch)" : "#2a2a28"))
        .attr("stroke", (q) => (q.preliminary ? "#6a6a66" : "none"))
        .attr("x", (q) => x(q.quarter)).attr("width", x.bandwidth());
      if (hidden) bars.attr("y", y(0)).attr("height", 0);
      else bars.attr("y", (q) => y(q.actual_tn)).attr("height", (q) => y(0) - y(q.actual_tn));
      cur.bars = bars;

      const tw = Math.min(x.bandwidth() + 8, 40);
      const nc = gNc.selectAll("g").data(FQ, (q) => q.quarter).join((en) => {
        const g = en.append("g"); g.append("line").attr("stroke", "#f2f2f0").attr("stroke-width", 2); g.append("circle").attr("r", 3).attr("class", "f-ink"); return g;
      });
      const ncY = (q) => y(q[key]);
      nc.select("line").attr("x1", (q) => x(q.quarter) + x.bandwidth() / 2 - tw / 2).attr("x2", (q) => x(q.quarter) + x.bandwidth() / 2 + tw / 2);
      nc.select("circle").attr("cx", (q) => x(q.quarter) + x.bandwidth() / 2);
      tr(nc.select("line")).attr("y1", ncY).attr("y2", ncY);
      tr(nc.select("circle")).attr("cy", ncY);
      gNc.attr("opacity", hidden ? 0 : 1);

      const lastQ = FQ[FQ.length - 1];
      gLab.selectAll("*").remove();
      const labs = [
        { y: y(lastQ.actual_tn), t: "Actual " + F.tn1(lastQ.actual_tn * 1e6) + (lastQ.preliminary ? " (prelim.)" : "") },
        { y: y(lastQ[key]), t: "Forecast " + F.tn1(lastQ[key] * 1e6) + " (" + pctS(lastQ[key + "_err"]) + ")" },
      ].sort((a, b) => a.y - b.y);
      for (let i = 1; i < labs.length; i++) if (labs[i].y - labs[i - 1].y < 14) labs[i].y = labs[i - 1].y + 14;
      if (!m.narrow) labs.forEach((l) => gLab.append("text").attr("class", "annot").attr("x", x(lastQ.quarter) - 8).attr("y", l.y + 4).attr("text-anchor", "end").text(l.t));
      gLab.attr("opacity", hidden ? 0 : 1);

      gLeg.selectAll("*").remove();
      const items = [["bar", "Revenue"], ["tick", "Forecast, " + MLAB[key].toLowerCase()]];
      let lx = m.l;
      items.forEach(([k, t]) => {
        const g = gLeg.append("g").attr("transform", `translate(${lx},6)`);
        if (k === "bar") g.append("rect").attr("width", 10).attr("height", 10).attr("fill", "#2a2a28").attr("stroke", "#555");
        else g.append("line").attr("x1", 0).attr("x2", 12).attr("y1", 5).attr("y2", 5).attr("stroke", "#f2f2f0").attr("stroke-width", 2);
        g.append("text").attr("class", "annot").attr("x", 16).attr("y", 9).text(t);
        lx += 16 + t.length * 6.6 + 18;
      });

      gHit.selectAll("rect").data(FQ, (q) => q.quarter).join("rect").attr("fill", "transparent")
        .attr("x", (q) => x(q.quarter) - (x.step() * x.paddingInner()) / 2).attr("width", x.step()).attr("y", m.t).attr("height", h - m.t - m.b)
        .on("pointermove", (ev, q) => {
          const up = (v) => (v > q.prev_tn ? "up" : "down");
          showTip(tipHtml(qLabel(q.quarter), [
            ["Revenue", F.tn1(q.actual_tn * 1e6) + (q.preliminary ? " (prelim.)" : "")],
            ["Previous quarter", F.tn1(q.prev_tn * 1e6)],
            ["After m1", F.tn1(q.m1 * 1e6) + " (" + pctS(q.m1_err) + ")"],
            ["After m2", F.tn1(q.m2 * 1e6) + " (" + pctS(q.m2_err) + ")"],
            ["Full quarter", F.tn1(q.m3 * 1e6) + " (" + pctS(q.m3_err) + ")"],
            ["Baseline", F.tn1(q.baseline * 1e6) + " (" + pctS(q.baseline_err) + ")"],
            ["Call / actual", up(q[key]) + " / " + up(q.actual_tn)],
          ], "Forecast = last quarter's revenue × exports so far this quarter ÷ same months last quarter (KRW)."), ev);
        })
        .on("pointerleave", hideTip);
    }
    seg("nc-model", (v) => { st.model = v; render(true); });
    const ncChart = {
      el: fig, render,
      reveal() {
        if (st.visible) return; st.visible = true;
        if (RM) { render(false); return; }
        const { y } = cur;
        cur.bars.transition().duration(900).delay((q, i) => i * 40).ease(d3.easeCubicOut)
          .attr("y", (q) => y(q.actual_tn)).attr("height", (q) => y(0) - y(q.actual_tn));
        [gNc, gLab].forEach((g) => g.transition().delay(900).duration(500).attr("opacity", 1));
      },
    };
    return [errChart, ncChart];
  }

  // ------------------------------------------------------------------ FIG 4 satellite
  function satellite(D) {
    const S = D.satellite, fig = $("#fig-sat"), fig2 = $("#fig-swipe");
    if (!S || !fig) return null;
    const fr = S.frames, b = S.bounds, fp = S.footprint;
    const ar = `${S.width} / ${S.height}`;
    const box = {
      left: ((fp.lon_min - b.lon_min) / (b.lon_max - b.lon_min)) * 100,
      width: ((fp.lon_max - fp.lon_min) / (b.lon_max - b.lon_min)) * 100,
      top: ((b.lat_max - fp.lat_max) / (b.lat_max - b.lat_min)) * 100,
      height: ((fp.lat_max - fp.lat_min) / (b.lat_max - b.lat_min)) * 100,
    };
    $$("[data-fp]").forEach((el) => {
      el.style.left = box.left + "%"; el.style.top = box.top + "%"; el.style.width = box.width + "%"; el.style.height = box.height + "%";
    });
    $$(".satframe, .swipe").forEach((el) => el.style.setProperty("--ar", ar));
    fr.forEach((f) => { const im = new Image(); im.src = f.img; });

    const img = $("[data-img]", fig), cap = $("[data-cap]", fig), range = $("[data-range]", fig), stripEl = $("[data-strip]", fig);
    range.max = fr.length - 1;
    let idx = RM ? fr.length - 1 : 0, timer = null;
    const msByDate = S.milestones.map((m) => ({ ...m, d: pm(m.date) }));
    function show(i) {
      idx = Math.max(0, Math.min(fr.length - 1, i));
      const f = fr[idx];
      img.src = f.img;
      img.alt = `Sentinel-2 greyscale image of the M15X site, ${f.quarter}, ${f.date}`;
      cap.innerHTML = `<span><b>${esc(f.quarter.slice(0, 4) + " " + f.quarter.slice(4))}</b>${esc(f.date)}</span><span>${esc(f.scene)}</span>`;
      range.value = idx;
      stripSvg.selectAll(".tick-q").classed("on", (d, j) => j === idx);
      stripSvg.select(".cursor").attr("x1", sx(pm(f.date.slice(0, 7)))).attr("x2", sx(pm(f.date.slice(0, 7))));
    }
    range.addEventListener("input", () => { stop(); show(+range.value); });
    const playBtn = $("[data-play]", fig);
    function stop() { if (timer) { clearInterval(timer); timer = null; playBtn.textContent = "▶ Play"; playBtn.setAttribute("aria-pressed", "false"); } }
    playBtn.addEventListener("click", () => {
      if (timer) { stop(); return; }
      if (idx >= fr.length - 1) show(0);
      playBtn.textContent = "❚❚ Pause"; playBtn.setAttribute("aria-pressed", "true");
      timer = setInterval(() => { if (idx >= fr.length - 1) { stop(); return; } show(idx + 1); }, 650);
    });

    // milestone strip
    const stripSvg = d3.select(stripEl).append("svg").attr("class", "strip").attr("role", "img").attr("aria-label", "M15X milestones and image dates");
    let sx = d3.scaleTime();
    function renderStrip() {
      const w = stripEl.clientWidth || 600, narrow = w < 560;
      const rowH = 30, top = 34, h = top + 14 + msByDate.length * rowH;
      stripSvg.attr("viewBox", `0 0 ${w} ${h}`).attr("width", w).attr("height", h);
      stripSvg.selectAll("*").remove();
      const d0 = new Date(+pm(fr[0].date.slice(0, 7)) - 40 * 864e5), d1 = new Date(+pm(fr[fr.length - 1].date.slice(0, 7)) + 40 * 864e5);
      sx = d3.scaleTime().domain([d0, d1]).range([8, w - 8]);
      stripSvg.append("g").attr("class", "axis").attr("transform", `translate(0,${top})`)
        .call(d3.axisBottom(sx).ticks(d3.timeYear.every(1)).tickFormat(d3.timeFormat("%Y")).tickSize(4));
      stripSvg.append("line").attr("x1", 8).attr("x2", w - 8).attr("y1", top).attr("y2", top).attr("stroke", "#3a3a38");
      stripSvg.append("line").attr("class", "cursor").attr("y1", 4).attr("y2", top).attr("stroke", "var(--ink)").attr("stroke-width", 1);
      stripSvg.selectAll(".tick-q").data(fr).join("line").attr("class", "tick-q")
        .attr("x1", (f) => sx(pm(f.date.slice(0, 7)))).attr("x2", (f) => sx(pm(f.date.slice(0, 7)))).attr("y1", top - 12).attr("y2", top);
      stripSvg.selectAll(".hit").data(fr).join("rect").attr("class", "hit")
        .attr("x", (f) => sx(pm(f.date.slice(0, 7))) - 8).attr("width", 16).attr("y", 0).attr("height", top + 2)
        .on("click", (ev, f) => { stop(); show(fr.indexOf(f)); })
        .on("pointermove", (ev, f) => showTip(tipHtml(f.quarter, [["Scene date", f.date], ["Site clear", Math.round(f.site_clear * 100) + "%"]], esc(f.scene)), ev))
        .on("pointerleave", hideTip);
      msByDate.forEach((ms, i) => {
        const x = sx(ms.d), y = top + 14 + i * rowH + 10;
        const right = x > w * 0.55;
        stripSvg.append("line").attr("class", "ms-line").attr("x1", x).attr("x2", x).attr("y1", top).attr("y2", y);
        stripSvg.append("circle").attr("class", "ms-dot " + ms.kind).attr("cx", x).attr("cy", top).attr("r", 4.5);
        const t = stripSvg.append("text").attr("x", right ? x - 7 : x + 7).attr("y", y + 4).attr("text-anchor", right ? "end" : "start");
        t.append("tspan").attr("class", "ms-lab").text(ms.when + " · " + ms.label);
        if (!narrow) t.append("tspan").attr("class", "ms-src").attr("dx", 8).text(ms.source);
        stripSvg.append("rect").attr("fill", "transparent").attr("x", Math.min(x, right ? x - 260 : x)).attr("width", 260).attr("y", y - 10).attr("height", 20)
          .on("pointermove", (ev) => showTip(tipHtml(ms.detail, [["Type", ms.kind], ["Source", ms.source]]), ev))
          .on("pointerleave", hideTip);
      });
      show(idx);
    }

    // swipe
    const before = fr.find((f) => f.quarter === "2022Q2") || fr[0], after = fr[fr.length - 1];
    $("[data-before]", fig2).src = before.img; $("[data-after]", fig2).src = after.img;
    $("[data-a]", fig2).textContent = before.quarter; $("[data-b]", fig2).textContent = after.quarter;
    $("[data-la]", fig2).textContent = `${before.quarter} · ${before.date}`;
    $("[data-lb]", fig2).textContent = `${after.quarter} · ${after.date}`;
    const swr = $("[data-swr]", fig2), top = $("[data-top]", fig2), bar = $("[data-bar]", fig2);
    const setSwipe = (v) => { top.style.clipPath = `inset(0 ${100 - v}% 0 0)`; bar.style.left = v + "%"; };
    swr.addEventListener("input", () => setSwipe(+swr.value));
    setSwipe(50);

    let revealed = false;
    return {
      el: fig, render: renderStrip,
      reveal() {
        if (revealed || RM) return; revealed = true;
        // one gentle pass through the archive the first time it is seen, ending on the latest frame
        let i = 0; show(0);
        timer = setInterval(() => { i++; if (i >= fr.length) { stop(); return; } show(i); }, 160);
        playBtn.textContent = "❚❚ Pause"; playBtn.setAttribute("aria-pressed", "true");
      },
      init() { show(fr.length - 1); },
    };
  }

  // ------------------------------------------------------------------ tables
  function tables(D) {
    const tb = $("#src-table tbody");
    tb.innerHTML = D.contract.map((r) => `<tr><td>${esc(r.month)}</td><td class="n">${r.avg_usd == null ? "–" : "$" + r.avg_usd.toFixed(2)}</td>` +
      `<td class="n">${r.mom_pct == null ? "–" : pctS(r.mom_pct)}</td><td class="n">${r.mom3_pct == null ? "–" : pctS(r.mom3_pct)}</td>` +
      `<td>${esc(r.publication_date || "")}</td><td>${r.source_url ? `<a href="${esc(r.source_url)}" target="_blank" rel="noopener" title="${esc(r.quote || "")}">${esc(r.source)}</a>` : "not found"}</td>` +
      `<td>${esc(r.flag || "")}</td></tr>`).join("");
    const bt = $("#bt-table tbody");
    const f2 = (v) => v.toFixed(2);
    bt.innerHTML = D.financials.quarters.filter((q) => q.m1 != null).map((q) =>
      `<tr${q.preliminary ? ' class="hl"' : ""}><td>${q.quarter}${q.preliminary ? " (prelim.)" : ""}</td><td class="n">${f2(q.actual_tn)}</td>` +
      `<td class="n">${f2(q.m1)}</td><td class="n">${pctS(q.m1_err)}</td><td class="n">${f2(q.m2)}</td><td class="n">${pctS(q.m2_err)}</td>` +
      `<td class="n">${f2(q.m3)}</td><td class="n">${pctS(q.m3_err)}</td><td class="n">${pctS(q.baseline_err)}</td></tr>`).join("");
  }
})();
