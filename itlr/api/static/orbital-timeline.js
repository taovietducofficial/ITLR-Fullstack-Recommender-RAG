/* Orbital timeline — engine vanilla (port từ component React radial-orbital-timeline).
 * Không phụ thuộc React/Tailwind. Dùng:
 *   initOrbitalTimeline(hostEl, data, { onAsk })
 * data[]: { id, title, date, level('Cơ bản'|'Trung cấp'|'Nâng cao'), content, icon, relatedIds[], energy }
 */
(function () {
  "use strict";

  var REDUCE = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // SVG icon (KHÔNG dùng emoji làm icon cấu trúc) — stroke đồng nhất 2px, kế thừa currentColor.
  var ICONS = {
    cpu:'<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v2M15 2v2M9 20v2M15 20v2M20 9h2M20 15h2M2 9h2M2 15h2"/>',
    code:'<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    sigma:'<path d="M18 7V4H6l6 8-6 8h12v-3"/>',
    globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 4 9 14 14 0 0 1-4 9 14 14 0 0 1-4-9 14 14 0 0 1 4-9z"/>',
    database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    sparkles:'<path d="M12 3l1.8 4.5L18 9.3l-4.2 1.8L12 16l-1.8-4.9L6 9.3l4.2-1.8L12 3z"/>'
  };
  function svg(name) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICONS[name] || ICONS.code) + '</svg>';
  }

  var LV = { "Cơ bản": 0, "Trung cấp": 1, "Nâng cao": 2 };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // Vị trí node trên quỹ đạo (giống calculateNodePosition của bản React).
  function calc(i, total, rot, radius) {
    var ang = ((i / total) * 360 + rot) % 360;
    var r = (ang * Math.PI) / 180;
    return {
      x: radius * Math.cos(r),
      y: radius * Math.sin(r),
      z: Math.round(100 + 50 * Math.cos(r)),
      o: Math.max(0.45, Math.min(1, 0.45 + 0.55 * ((1 + Math.sin(r)) / 2)))
    };
  }

  window.initOrbitalTimeline = function (host, data, opts) {
    if (!host || host.dataset.orbInit) return;
    host.dataset.orbInit = "1";
    opts = opts || {};

    host.classList.add("orb-stage");
    host.setAttribute("role", "group");
    host.setAttribute("aria-label", "Lộ trình học tập dạng quỹ đạo");

    var field = document.createElement("div");
    field.className = "orb-field";
    field.innerHTML =
      '<div class="orb-ring" style="width:340px;height:340px"></div>' +
      '<div class="orb-center"><div class="orb-ping" style="width:80px;height:80px"></div>' +
      '<div class="orb-ping" style="width:104px;height:104px;animation-delay:.6s"></div>' +
      '<div class="orb-center-core"></div></div>';
    host.appendChild(field);

    var hint = document.createElement("div");
    hint.className = "orb-hint";
    hint.textContent = REDUCE
      ? "Chế độ giảm chuyển động — bấm một nút để xem chi tiết giai đoạn"
      : "Bấm vào một nút để xem chi tiết giai đoạn";
    host.appendChild(hint);

    var refs = {}, rotation = 0, auto = !REDUCE, raf = null, last = 0;

    function find(id) { for (var i = 0; i < data.length; i++) if (data[i].id === id) return data[i]; return null; }
    function relatedOf(id) { var it = find(id); return it ? (it.relatedIds || []) : []; }

    function radius() {
      var base = Math.min(host.clientWidth, host.clientHeight) / 2 - 80;
      return Math.max(110, Math.min(210, base));
    }

    function layout() {
      var rad = radius();
      for (var i = 0; i < data.length; i++) {
        var it = data[i], el = refs[it.id], p = calc(i, data.length, rotation, rad);
        var exp = el.getAttribute("aria-expanded") === "true";
        el.style.transform = "translate(-50%,-50%) translate(" + p.x.toFixed(1) + "px," + p.y.toFixed(1) + "px)";
        el.style.zIndex = exp ? 400 : p.z;
        el.style.opacity = exp ? 1 : p.o;
      }
    }

    function frame(now) {
      if (!last) last = now;
      if (auto) rotation = (rotation + (now - last) * 0.006) % 360;  // ~0.3°/50ms như bản gốc
      last = now;
      layout();
      raf = requestAnimationFrame(frame);
    }
    function startLoop() { if (raf == null) { last = 0; raf = requestAnimationFrame(frame); } }
    function stopLoop() { if (raf != null) { cancelAnimationFrame(raf); raf = null; } }

    // Đưa node đang mở lên ĐỈNH (angle 270°) để thẻ luôn nằm dưới và không bị cắt.
    function centerOn(id) {
      var idx = -1;
      for (var i = 0; i < data.length; i++) if (data[i].id === id) { idx = i; break; }
      if (idx < 0) return;
      rotation = (270 - (idx / data.length) * 360) % 360;
    }

    function closeAll() {
      data.forEach(function (it) {
        var el = refs[it.id];
        el.setAttribute("aria-expanded", "false");
        el.classList.remove("is-related");
        var c = el.querySelector(".orb-card"); if (c) c.remove();
      });
      auto = !REDUCE;
      if (auto) startLoop(); else layout();
    }

    function open(id) {
      var it = find(id); if (!it) return;
      data.forEach(function (o) {
        if (o.id !== id) {
          var el = refs[o.id];
          el.setAttribute("aria-expanded", "false");
          var c = el.querySelector(".orb-card"); if (c) c.remove();
        }
      });
      var node = refs[id];
      node.setAttribute("aria-expanded", "true");
      auto = false; stopLoop();

      var rel = relatedOf(id);
      data.forEach(function (o) { refs[o.id].classList.toggle("is-related", rel.indexOf(o.id) >= 0); });

      node.appendChild(buildCard(it));
      centerOn(id);
      layout();
    }

    function toggle(id) {
      if (refs[id].getAttribute("aria-expanded") === "true") closeAll();
      else open(id);
    }

    function buildCard(it) {
      var lv = LV[it.level] != null ? LV[it.level] : 1;
      var rel = (it.relatedIds || []).map(function (rid) {
        var r = find(rid); if (!r) return "";
        return '<button class="orb-chip" data-go="' + rid + '">' + esc(r.title) +
          ' <svg viewBox="0 0 24 24" width="9" height="9" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>';
      }).join("");

      var card = document.createElement("div");
      card.className = "orb-card";
      card.setAttribute("role", "dialog");
      card.setAttribute("aria-label", it.title);
      card.innerHTML =
        '<div class="orb-card-stem"></div>' +
        '<div class="orb-card-top">' +
          '<span class="orb-badge lv' + lv + '">' + esc((it.level || "").toUpperCase()) + '</span>' +
          '<span class="orb-date">' + esc(it.date || "") + '</span>' +
        '</div>' +
        '<h4>' + esc(it.title) + '</h4>' +
        '<p>' + esc(it.content || "") + '</p>' +
        '<div class="orb-meter"><div class="orb-meter-row"><span>Mức nền tảng</span><span>' + (it.energy || 0) + '%</span></div>' +
          '<div class="orb-meter-track"><div class="orb-meter-fill" style="width:' + (it.energy || 0) + '%"></div></div></div>' +
        (rel ? '<div class="orb-rel"><p class="orb-rel-h">Giai đoạn liên quan</p><div class="orb-rel-btns">' + rel + '</div></div>' : '') +
        (opts.onAsk ? '<button class="orb-cta" data-ask="1">Hỏi chatbot về giai đoạn này →</button>' : '');

      card.addEventListener("click", function (e) { e.stopPropagation(); });
      Array.prototype.forEach.call(card.querySelectorAll("[data-go]"), function (b) {
        b.addEventListener("click", function (e) { e.stopPropagation(); toggle(parseInt(b.getAttribute("data-go"), 10)); });
      });
      var ask = card.querySelector("[data-ask]");
      if (ask) ask.addEventListener("click", function (e) { e.stopPropagation(); opts.onAsk(it); });
      return card;
    }

    // Dựng node
    data.forEach(function (it) {
      var node = document.createElement("button");
      node.type = "button";
      node.className = "orb-node";
      node.setAttribute("aria-expanded", "false");
      node.setAttribute("aria-label", it.title + (it.level ? " — " + it.level : ""));
      var glow = (it.energy || 0) * 0.5 + 44;
      node.innerHTML =
        '<span class="orb-glow" style="width:' + glow + 'px;height:' + glow + 'px"></span>' +
        '<span class="orb-dot">' + svg(it.icon) + '</span>' +
        '<span class="orb-label">' + esc(it.title) + '</span>';
      node.addEventListener("click", function (e) { e.stopPropagation(); toggle(it.id); });
      node.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(it.id); }
        else if (e.key === "Escape") { closeAll(); node.focus(); }
      });
      refs[it.id] = node;
      field.appendChild(node);
    });

    host.addEventListener("click", function (e) { if (e.target === host || e.target === field) closeAll(); });
    window.addEventListener("resize", layout);

    layout();
    if (auto) startLoop();
  };
})();
