(function () {
  "use strict";

  var REDUCE = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var CALM = document.body.matches(".page-blog, .page-friends, .page-messages");

  var RT = (function () {
    var uid = parseInt(document.body.getAttribute("data-user-id") || "", 10);
    if (!uid || !window.EventSource) return { uid: 0, on: function () {} };
    var es = new EventSource("/api/realtime");
    window.addEventListener("pagehide", function () { try { es.close(); } catch (_) {} });
    return {
      uid: uid,
      on: function (ev, cb) {
        es.addEventListener(ev, function (e) {
          var d = {}; try { d = JSON.parse(e.data); } catch (_) {}
          cb(d);
        });
      },
    };
  })();
  var PAGE = (document.body.className.match(/page-([a-z]+)/) || [])[1] || "";

  function bumpNav(name) {
    var b = document.querySelector('.nav-links a[data-nav="' + name + '"] .nav-badge');
    if (!b) return;
    var n = (parseInt(b.textContent, 10) || 0) + 1;
    b.textContent = n > 9 ? "9+" : String(n);
    b.hidden = false;
  }

  var _newPosts = 0, _pill = null;
  function showNewPostsPill() {
    _newPosts++;
    if (!_pill) {
      _pill = document.createElement("button");
      _pill.type = "button"; _pill.className = "newposts-pill";
      _pill.addEventListener("click", function () { location.reload(); });
      document.body.appendChild(_pill);
    }
    _pill.textContent = "↑ " + _newPosts + " bài viết mới — bấm để xem";
  }

  RT.on("dm", function (d) {
    var log = document.getElementById("dm-log");
    var open = log ? log.getAttribute("data-user") : null;
    if (open && String(d.from) === String(open)) return;
    toast("💬 Tin nhắn mới từ " + (d.fromName || "bạn bè"), "ok");
    if (PAGE !== "messages") bumpNav("messages");
  });
  RT.on("friend_request", function (d) {
    toast("👋 " + (d.name || "Ai đó") + " gửi lời mời kết bạn", "ok");
    bumpNav("friends");
    if (PAGE === "friends") setTimeout(function () { location.reload(); }, 1400);
  });
  RT.on("friend_accept", function (d) {
    toast("🤝 " + (d.name || "Bạn bè") + " đã chấp nhận lời mời kết bạn", "ok");
    if (PAGE === "friends") setTimeout(function () { location.reload(); }, 1400);
  });
  RT.on("post_comment", function (d) {
    var post = document.querySelector('.post[data-post="' + d.postId + '"]');
    if (!post) return;
    var box = post.querySelector(".comments");
    if (box) {
      var div = document.createElement("div"); div.className = "cmt";
      div.innerHTML = "<b>" + esc(d.author) + "</b> " + esc(d.content);
      box.appendChild(div);
    }
    var cc = post.querySelector(".cmt-count");
    if (cc) cc.textContent = (parseInt(cc.textContent, 10) || 0) + 1;
  });
  RT.on("post_like", function (d) {
    var post = document.querySelector('.post[data-post="' + d.postId + '"]');
    if (!post) return;
    var c = post.querySelector(".like-count"); if (c) c.textContent = d.count;
  });
  RT.on("post_new", function () { if (PAGE === "blog") showNewPostsPill(); });

  (function () {
    function setDot(uid, online) {
      document.querySelectorAll('.pdot[data-uid="' + uid + '"]').forEach(function (el) {
        el.classList.toggle("on", !!online);
      });
    }
    function fmtSeen(iso) {
      if (!iso) return "ngoại tuyến";
      var s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
      if (s < 60) return "vừa truy cập";
      if (s < 3600) return "hoạt động " + Math.floor(s / 60) + " phút trước";
      if (s < 86400) return "hoạt động " + Math.floor(s / 3600) + " giờ trước";
      return "hoạt động " + Math.floor(s / 86400) + " ngày trước";
    }
    var hdr = document.getElementById("hdr-presence");
    function renderHdr(online, last) {
      if (!hdr) return;
      hdr.classList.toggle("on", !!online);
      hdr.textContent = online ? "● Đang hoạt động" : "● " + fmtSeen(last);
    }
    if (hdr) renderHdr(hdr.getAttribute("data-online") === "1", hdr.getAttribute("data-last"));

    RT.on("presence_snapshot", function (d) {
      (d.online || []).forEach(function (uid) { setDot(uid, true); });
      if (hdr && (d.online || []).map(String).indexOf(String(hdr.getAttribute("data-uid"))) >= 0) renderHdr(true);
    });
    RT.on("presence", function (d) {
      setDot(d.user, d.online);
      if (hdr && String(hdr.getAttribute("data-uid")) === String(d.user)) renderHdr(d.online, d.last_seen);
    });
  })();

  (function () {
    if (REDUCE || CALM || !("IntersectionObserver" in window)) return;
    var SEL = ".card, .cat-card, .cta, .post, .stat, .cw-feat, .section-title";
    var els = Array.prototype.slice.call(document.querySelectorAll(SEL));
    if (!els.length) return;
    els.forEach(function (el) { el.classList.add("reveal"); });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          var el = e.target, sibs = el.parentElement ? el.parentElement.children : [];
          var idx = Array.prototype.indexOf.call(sibs, el);
          el.style.transitionDelay = Math.min((idx % 8) * 45, 320) + "ms";
          el.classList.add("in");
          io.unobserve(el);
          setTimeout(function () { el.classList.remove("reveal"); el.style.transitionDelay = ""; }, 1100);
        }
      });
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.06 });
    els.forEach(function (el) { io.observe(el); });
  })();

  (function () {
    var nav = document.querySelector(".nav");
    if (!nav) return;
    var on = function () { nav.classList.toggle("scrolled", window.scrollY > 8); };
    on();
    window.addEventListener("scroll", on, { passive: true });
  })();

  function toast(msg, kind) {
    var wrap = document.getElementById("toast-wrap");
    if (!wrap) { wrap = document.createElement("div"); wrap.id = "toast-wrap"; document.body.appendChild(wrap); }
    var t = document.createElement("div");
    t.className = "toast " + (kind || "");
    t.textContent = msg;
    wrap.appendChild(t);
    setTimeout(function () { t.style.opacity = "0"; t.style.transform = "translateY(8px)"; setTimeout(function () { t.remove(); }, 250); }, 2600);
  }

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrf=([a-f0-9]+)/);
    return m ? m[1] : "";
  }
  function cfetch(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign({}, opts.headers, { "X-CSRF-Token": csrfToken() });
    return fetch(url, opts);
  }

  function askIntro(onSend) {
    var ov = document.createElement("div");
    ov.className = "modal-ov";
    ov.innerHTML =
      '<div class="modal" role="dialog" aria-modal="true">' +
      '<h3 class="modal-title">🤝 Gửi lời mời kết bạn</h3>' +
      '<p class="muted small">Viết vài dòng giới thiệu để họ biết lý do và dễ chấp nhận hơn.</p>' +
      '<textarea class="modal-input" rows="3" maxlength="300" placeholder="Ví dụ: Mình cùng học Web ở trường, kết bạn trao đổi nhé!"></textarea>' +
      '<div class="modal-actions">' +
      '<button type="button" class="btn-pill ghost modal-cancel">Hủy</button>' +
      '<button type="button" class="btn-pill primary modal-ok">Gửi lời mời</button>' +
      "</div></div>";
    document.body.appendChild(ov);
    var ta = ov.querySelector(".modal-input");
    setTimeout(function () { ta.focus(); }, 30);
    function close() { ov.remove(); }
    ov.addEventListener("click", function (e) { if (e.target === ov) close(); });
    ov.querySelector(".modal-cancel").addEventListener("click", close);
    ov.querySelector(".modal-ok").addEventListener("click", function () {
      var v = ta.value.trim(); close(); onSend(v);
    });
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
    });
  }

  function postJSON(url, body) {
    return cfetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); });
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function typeInto(el, plain, html, onDone) {
    if (REDUCE || !plain) {
      el.classList.remove("typing"); el.innerHTML = html;
      window.scrollTo(0, document.body.scrollHeight); if (onDone) onDone(); return;
    }
    el.classList.add("typing");
    var i = 0, n = plain.length, step = Math.max(1, Math.round(n / 180));
    (function tick() {
      i += step;
      el.textContent = plain.slice(0, i);
      if (i % (step * 8) < step) window.scrollTo(0, document.body.scrollHeight);
      if (i < n) { setTimeout(tick, 14); }
      else { el.classList.remove("typing"); el.innerHTML = html; window.scrollTo(0, document.body.scrollHeight); if (onDone) onDone(); }
    })();
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest(".card-del");
    if (!btn) return;
    e.preventDefault(); e.stopPropagation();
    if (!confirm("Xóa mục này khỏi danh sách đã lưu của bạn?")) return;
    var id = parseInt(btn.getAttribute("data-remove"), 10);
    var card = btn.closest(".card");
    postJSON("/api/unsave", { course_id: id }).then(function (res) {
      if (res.ok) {
        if (card) { card.style.transition = "opacity .2s, transform .2s"; card.style.opacity = "0"; card.style.transform = "scale(.97)"; setTimeout(function () { card.remove(); }, 210); }
        toast("Đã xóa khỏi danh sách", "ok");
      } else toast(res.j.error || "Lỗi", "err");
    }).catch(function () { toast("Lỗi mạng", "err"); });
  });

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest(".card-save");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    if (btn.dataset.busy) return;
    btn.dataset.busy = "1";
    var id = parseInt(btn.getAttribute("data-save"), 10);
    var isSaved = btn.classList.contains("is-saved");
    var url = isSaved ? "/api/unsave" : "/api/save";
    var body = isSaved ? { course_id: id } : { course_id: id, status: "saved", progress: 0 };
    postJSON(url, body).then(function (res) {
      delete btn.dataset.busy;
      if (res.ok) {
        if (isSaved) { btn.classList.remove("is-saved"); btn.textContent = "+ Lưu"; toast("Đã bỏ lưu", "ok"); }
        else { btn.classList.add("is-saved"); btn.textContent = "✓ Đã lưu"; toast("✓ Đã lưu khóa học", "ok"); }
      } else {
        toast(res.j.error || "Cần đăng nhập để lưu", "err");
      }
    }).catch(function () { delete btn.dataset.busy; toast("Lỗi mạng", "err"); });
  });

  var box = document.querySelector(".enroll-box");
  if (box) {
    var courseId = parseInt(box.getAttribute("data-course"), 10);
    var progVal = document.getElementById("enroll-prog-val");
    var statusSel = document.getElementById("enroll-status");
    function curProgress() { return parseInt(progVal && progVal.textContent, 10) || 0; }

    function saveEnroll(status, progress, okMsg) {
      return postJSON("/api/save", { course_id: courseId, status: status, progress: progress }).then(function (res) {
        if (res.ok) toast(okMsg || "✓ Đã cập nhật", "ok"); else toast(res.j.error || "Lỗi", "err");
        return res;
      }).catch(function () { toast("Lỗi mạng", "err"); });
    }

    var saveBtn = document.getElementById("enroll-save");
    if (saveBtn) saveBtn.addEventListener("click", function () {
      saveEnroll(statusSel.value, curProgress(), "✓ Đã lưu khóa học");
    });

    var completeBtn = document.getElementById("enroll-complete");
    if (completeBtn) completeBtn.addEventListener("click", function () {
      updateProgressBar(100, "completed");
      saveEnroll("completed", 100, "🎉 Chúc mừng đã hoàn thành khóa học!");
    });

    var removeBtn = document.getElementById("enroll-remove");
    if (removeBtn) removeBtn.addEventListener("click", function () {
      postJSON("/api/unsave", { course_id: courseId }).then(function () {
        toast("Đã bỏ lưu", "ok"); setTimeout(function () { window.location.reload(); }, 600);
      });
    });
  }

  var attForm = document.getElementById("attach-form");
  if (attForm) {
    var cId = attForm.getAttribute("data-course");
    var attMsg = document.getElementById("attach-msg");
    attForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var f = document.getElementById("attach-file").files[0];
      if (!f) return;
      attMsg.textContent = "Đang tải lên...";
      var fd = new FormData(); fd.append("file", f);
      cfetch("/api/courses/" + cId + "/attachments", { method: "POST", body: fd })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          attMsg.textContent = "";
          if (!res.ok) { toast(res.j.error || "Tải lên thất bại", "err"); return; }
          if (res.j.pending) { attForm.reset(); toast("🙌 Đã gửi đóng góp — chờ quản trị viên duyệt", "ok"); return; }
          var a = res.j.attachment, ul = document.getElementById("attach-list");
          var empty = document.getElementById("attach-empty"); if (empty) empty.style.display = "none";
          var li = document.createElement("li"); li.setAttribute("data-att", a.id);
          li.innerHTML = '<span class="att-ic">📄</span><a class="att-name" href="/api/download/' + a.id + '">' + esc(a.filename) + '</a>' +
            '<span class="muted att-size">' + Math.max(1, Math.round((a.size || 0) / 1024)) + ' KB</span>' +
            '<button class="att-del" type="button" data-att="' + a.id + '" title="Xóa">×</button>';
          ul.insertBefore(li, ul.firstChild);
          attForm.reset(); toast("✓ Đã tải lên tài liệu", "ok");
        }).catch(function () { attMsg.textContent = ""; toast("Lỗi mạng", "err"); });
    });
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".att-del");
    if (!b) return;
    if (!confirm("Xóa tài liệu này?")) return;
    cfetch("/api/attachments/" + b.getAttribute("data-att"), { method: "DELETE" }).then(function (r) {
      if (r.ok) { var li = b.closest("li"); if (li) li.remove(); toast("Đã xóa tài liệu", "ok"); }
      else toast("Không xóa được", "err");
    }).catch(function () { toast("Lỗi mạng", "err"); });
  });

  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".att-view");
    if (!b) return;
    var id = b.getAttribute("data-att");
    var mime = (b.getAttribute("data-mime") || "").toLowerCase();
    var name = b.getAttribute("data-name") || "Tài liệu";
    var v = document.getElementById("att-viewer");
    if (!v) return;
    v.hidden = false;
    v.innerHTML = '<div class="att-viewer-head"><b>' + esc(name) + '</b><button type="button" class="att-close">Đóng ✕</button></div><div class="att-viewer-body">Đang tải...</div>';
    var body = v.querySelector(".att-viewer-body");
    v.querySelector(".att-close").addEventListener("click", function () { v.hidden = true; v.innerHTML = ""; });
    if (mime.indexOf("pdf") >= 0) {
      body.innerHTML = '<iframe class="att-frame" src="/api/attachment/' + id + '/inline"></iframe>';
    } else if (mime.indexOf("image") >= 0) {
      body.innerHTML = '<img class="att-img" src="/api/attachment/' + id + '/inline" alt="">';
    } else {
      fetch("/api/attachment/" + id + "/text").then(function (r) { return r.json(); }).then(function (j) {
        body.innerHTML = '<pre class="att-text">' + esc(j.text || "") + "</pre>";
      }).catch(function () { body.textContent = "Không tải được nội dung."; });
    }
    v.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  var form = document.getElementById("chatform");
  if (form) {
    var input = document.getElementById("chatinput");
    var log = document.getElementById("chatlog");
    var conversationId = log.dataset.conv ? parseInt(log.dataset.conv, 10) : null;
    var history = [];
    log.querySelectorAll(".msg").forEach(function (m) {
      var role = m.classList.contains("user") ? "user" : "assistant";
      var b = m.querySelector(".bubble");
      history.push({ role: role, content: (b ? b.textContent : "").trim() });
    });

    document.querySelectorAll(".prompt-chip").forEach(function (b) {
      b.addEventListener("click", function () { input.value = b.textContent; send(); });
    });

    function bubble(role, html) {
      var wrap = document.createElement("div");
      wrap.className = "msg " + role;
      wrap.innerHTML = '<div class="avatar">' + (role === "user" ? "🧑" : "🤖") + '</div><div class="bubble">' + html + "</div>";
      log.appendChild(wrap);
      window.scrollTo(0, document.body.scrollHeight);
      return wrap;
    }
    function recsBlock(recs) {
      if (!recs || !recs.length) return;
      var cards = recs.slice(0, 4).map(function (it) {
        return '<div class="card">' +
          '<h3 class="card-title"><a href="/courses/' + it.item_id + '">' + esc(it.title) + "</a></h3>" +
          '<p class="muted">' + esc(it.type) + " · " + esc(it.category) + "</p>" +
          '<button type="button" class="card-share" data-share-course="' + it.item_id + '" title="Chia sẻ vào tin nhắn">✉️ Chia sẻ</button>' +
          "</div>";
      }).join("");
      var d = document.createElement("details");
      d.className = "recs";
      d.innerHTML = "<summary>📚 " + recs.length + " tài nguyên liên quan</summary><div class='grid'>" + cards + "</div>";
      log.appendChild(d);
    }
    function refsBlock(refs) {
      if (!refs || !refs.length) return;
      var links = refs.map(function (r) {
        return '<a href="' + r.url + '" target="_blank" rel="noopener">🔗 ' + esc(r.label) + "</a>";
      }).join("");
      var d = document.createElement("div");
      d.className = "refs-box";
      d.innerHTML = '<span class="refs-h">Tham khảo thêm trên Google:</span>' + links;
      log.appendChild(d);
      window.scrollTo(0, document.body.scrollHeight);
    }
    function addConvToSidebar(id, title) {
      var list = document.querySelector(".conv-list"); if (!list) return;
      var empty = list.querySelector(".conv-empty"); if (empty) empty.remove();
      list.querySelectorAll(".conv-item.active").forEach(function (x) { x.classList.remove("active"); });
      var div = document.createElement("div");
      div.className = "conv-item active"; div.setAttribute("data-conv", id);
      div.innerHTML = '<a class="conv-title" href="/chat?c=' + id + '">' + esc(title) + '</a>' +
        '<button class="conv-del" type="button" data-conv="' + id + '" title="Xóa">×</button>';
      list.insertBefore(div, list.firstChild);
    }

    function send() {
      var text = input.value.trim();
      if (!text) return;
      input.value = "";
      var wel = log.querySelector(".chat-welcome");
      if (wel) wel.remove();
      bubble("user", esc(text));
      history.push({ role: "user", content: text });
      var thinking = bubble("assistant", "");
      var tbub = thinking.querySelector(".bubble");
      tbub.classList.add("typing");
      var payload = { message: text, history: history.slice(0, -1), conversation_id: conversationId || undefined };

      function finish(j) {
        tbub.classList.remove("typing");
        tbub.innerHTML = j.response_html || esc(j.response || "");
        window.scrollTo(0, document.body.scrollHeight);
        recsBlock(j.recommendations); refsBlock(j.references);
        history.push({ role: "assistant", content: j.response || "" });
        if (j.conversation_id && !conversationId) {
          conversationId = j.conversation_id;
          log.dataset.conv = conversationId;
          addConvToSidebar(conversationId, text.slice(0, 60));
          if (window.history && window.history.replaceState) window.history.replaceState(null, "", "/chat?c=" + conversationId);
        }
      }
      function fallback() {
        postJSON("/api/chat", payload).then(function (res) {
          if (!res.ok) { tbub.classList.remove("typing"); tbub.textContent = res.j.error || "Có lỗi xảy ra."; return; }
          var html = res.j.response_html || esc(res.j.response || "");
          var tmp = document.createElement("div"); tmp.innerHTML = html;
          typeInto(tbub, (tmp.textContent || "").trim(), html, function () { recsBlock(res.j.recommendations); refsBlock(res.j.references); });
          history.push({ role: "assistant", content: res.j.response || "" });
          if (res.j.conversation_id && !conversationId) {
            conversationId = res.j.conversation_id;
            log.dataset.conv = conversationId;
            addConvToSidebar(conversationId, text.slice(0, 60));
            if (window.history && window.history.replaceState) window.history.replaceState(null, "", "/chat?c=" + conversationId);
          }
        }).catch(function () { tbub.classList.remove("typing"); tbub.textContent = "Lỗi mạng khi gọi trợ lý."; });
      }

      if (!window.ReadableStream || !window.TextDecoder) return fallback();
      cfetch("/api/chat/stream", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
        .then(function (r) {
          if (!r.ok || !r.body) throw new Error("stream unavailable");
          var reader = r.body.getReader(), dec = new TextDecoder(), buf = "", acc = "", started = false;
          function pump() {
            return reader.read().then(function (s) {
              if (s.done) { tbub.classList.remove("typing"); return; }
              buf += dec.decode(s.value, { stream: true });
              var idx;
              while ((idx = buf.indexOf("\n\n")) >= 0) {
                var line = buf.slice(0, idx).trim(); buf = buf.slice(idx + 2);
                if (line.indexOf("data: ") !== 0) continue;
                var d; try { d = JSON.parse(line.slice(6)); } catch (_) { continue; }
                if (d.type === "text") {
                  acc += d.text || "";
                  tbub.classList.remove("typing");
                  tbub.textContent = acc;
                  if (!started || acc.length % 200 < 30) window.scrollTo(0, document.body.scrollHeight);
                  started = true;
                } else if (d.type === "final") { finish(d); }
              }
              return pump();
            });
          }
          return pump();
        })
        .catch(function () { if (tbub.classList.contains("typing")) fallback(); else tbub.classList.remove("typing"); });
    }

    form.addEventListener("submit", function (e) { e.preventDefault(); send(); });
  }

  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".conv-del");
    if (!b) return;
    e.preventDefault();
    if (!confirm("Xóa cuộc trò chuyện này?")) return;
    var id = b.getAttribute("data-conv");
    cfetch("/api/conversations/" + id, { method: "DELETE" }).then(function (r) {
      if (!r.ok) { toast("Không xóa được", "err"); return; }
      var item = b.closest(".conv-item");
      var wasActive = item && item.classList.contains("active");
      if (item) item.remove();
      toast("Đã xóa cuộc trò chuyện", "ok");
      if (wasActive) window.location.href = "/chat";
    }).catch(function () { toast("Lỗi mạng", "err"); });
  });

  function genPwd() {
    var L = "abcdefghijkmnpqrstuvwxyz", U = "ABCDEFGHJKLMNPQRSTUVWXYZ", D = "23456789", S = "!@#$%^&*-_=+?";
    var all = L + U + D + S, pick = function (s) { return s[Math.floor(Math.random() * s.length)]; };
    var a = [pick(L), pick(U), pick(S), pick(D)];
    while (a.length < 10) a.push(pick(all));
    for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; }
    return a.join("");
  }
  var pwField = document.getElementById("reg-password") || document.getElementById("acc-password");
  var genBtn = document.getElementById("genpass");
  if (genBtn && pwField) genBtn.addEventListener("click", function () {
    pwField.type = "text"; pwField.value = genPwd(); pwField.focus();
    toast("Đã tạo mật khẩu mạnh — hãy lưu lại!", "ok");
  });
  var eyeBtn = document.getElementById("togglepw");
  if (eyeBtn && pwField) eyeBtn.addEventListener("click", function () {
    pwField.type = pwField.type === "password" ? "text" : "password";
  });

  var postForm = document.getElementById("post-form");
  if (postForm) {
    var imgInput = document.getElementById("post-image");
    var vidInput = document.getElementById("post-video");
    var docInput = document.getElementById("post-doc");
    var filesLbl = document.getElementById("post-files");
    function showFiles() {
      var n = [];
      if (imgInput.files[0]) n.push("🖼️ " + imgInput.files[0].name);
      if (vidInput && vidInput.files[0]) n.push("🎬 " + vidInput.files[0].name);
      if (docInput.files[0]) n.push("📎 " + docInput.files[0].name);
      filesLbl.textContent = n.join("  ");
    }
    [imgInput, vidInput, docInput].forEach(function (i) { if (i) i.addEventListener("change", showFiles); });

    postForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var content = document.getElementById("post-content").value.trim();
      var hasFile = imgInput.files[0] || (vidInput && vidInput.files[0]) || docInput.files[0];
      if (!content && !hasFile) { toast("Nhập nội dung hoặc đính kèm", "err"); return; }
      var fd = new FormData();
      fd.append("content", content);
      if (imgInput.files[0]) fd.append("image", imgInput.files[0]);
      if (vidInput && vidInput.files[0]) fd.append("video", vidInput.files[0]);
      if (docInput.files[0]) fd.append("doc", docInput.files[0]);
      var btn = postForm.querySelector("button[type=submit]");
      if (btn) { btn.disabled = true; btn.textContent = "Đang đăng..."; }
      cfetch("/api/posts", { method: "POST", body: fd })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok) { toast(res.j.error || "Đăng thất bại", "err"); if (btn) { btn.disabled = false; btn.textContent = "Đăng bài"; } return; }
          toast("✓ Đã đăng bài", "ok"); window.location.reload();
        }).catch(function () { toast("Lỗi mạng", "err"); if (btn) { btn.disabled = false; btn.textContent = "Đăng bài"; } });
    });
  }

  function reflectComplete(pct, status) {
    var b = document.getElementById("enroll-complete"); if (!b) return;
    var done = pct >= 100 || status === "completed";
    b.textContent = done ? "✓ Đã hoàn thành khóa học" : "✓ Đánh dấu hoàn thành";
    b.classList.toggle("is-done", done);
    b.disabled = done;
  }
  function updateProgressBar(pct, status) {
    var bar = document.getElementById("enroll-bar"); if (bar) bar.style.width = pct + "%";
    var val = document.getElementById("enroll-prog-val"); if (val) val.textContent = pct;
    if (status) { var sel = document.getElementById("enroll-status"); if (sel) sel.value = status; }
    reflectComplete(pct, status);
  }

  document.addEventListener("click", function (e) {
    var t = e.target;
    var like = t.closest && t.closest(".like-btn");
    if (like) {
      postJSON("/api/posts/" + like.getAttribute("data-post") + "/like", {}).then(function (res) {
        if (!res.ok) return;
        like.classList.toggle("liked", res.j.liked);
        like.querySelector(".like-count").textContent = res.j.count;
      });
      return;
    }
    var share = t.closest && t.closest(".share-btn");
    if (share && !share.hasAttribute("data-share-post")) {
      if (!confirm("Chia sẻ bài này về trang cá nhân của bạn?")) return;
      postJSON("/api/posts/" + share.getAttribute("data-post") + "/share", {}).then(function (res) {
        toast(res.ok ? "✓ Đã chia sẻ về trang của bạn" : (res.j.error || "Lỗi"), res.ok ? "ok" : "err");
      });
      return;
    }
    var del = t.closest && t.closest(".post-del");
    if (del) {
      if (!confirm("Xóa bài viết này?")) return;
      cfetch("/api/posts/" + del.getAttribute("data-post"), { method: "DELETE" }).then(function (r) {
        if (r.ok) { var a = del.closest(".post"); if (a) a.remove(); toast("Đã xóa bài", "ok"); }
        else toast("Không xóa được", "err");
      });
      return;
    }
    var fa = t.closest && t.closest(".friend-act");
    if (fa) {
      var act = fa.getAttribute("data-act"), uid = fa.getAttribute("data-user");
      function sendFriend(body) {
        var url = act === "request" ? "/api/friends/request" : act === "accept" ? "/api/friends/accept" : "/api/friends/remove";
        postJSON(url, body).then(function (res) {
          if (!res.ok) { toast(res.j.error || "Lỗi", "err"); return; }
          toast(act === "request" ? "✓ Đã gửi lời mời kết bạn" : "✓ Đã cập nhật", "ok");
          window.location.reload();
        });
      }
      if (act === "request") {
        askIntro(function (intro) { sendFriend({ to: uid, intro: intro }); });
      } else {
        sendFriend(act === "accept" ? { from: uid } : { user: uid });
      }
      return;
    }
    var ld = t.closest && t.closest(".lesson-done");
    if (ld) {
      var done = ld.getAttribute("data-done") === "true";
      postJSON("/api/lessons/" + ld.getAttribute("data-lesson") + "/complete", { undo: done }).then(function (res) {
        if (!res.ok) { toast(res.j.error || "Lỗi", "err"); return; }
        ld.setAttribute("data-done", String(res.j.done));
        ld.textContent = res.j.done ? "✓ Đã xem xong" : "Đánh dấu đã xem xong";
        var card = ld.closest(".lesson"); if (card) card.classList.toggle("done", res.j.done);
        updateProgressBar(res.j.progress, res.j.status);
        toast(res.j.done ? "🎉 Đã xem xong bài học · tiến độ " + res.j.progress + "%" : "Đã bỏ đánh dấu", "ok");
      });
      return;
    }
    var lDel = t.closest && t.closest(".lesson-del");
    if (lDel) {
      if (!confirm("Xóa bài học này?")) return;
      cfetch("/api/lessons/" + lDel.getAttribute("data-lesson"), { method: "DELETE" })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok) { toast(res.j.error || "Lỗi", "err"); return; }
          var c = lDel.closest(".lesson"); if (c) c.remove();
          updateProgressBar(res.j.progress, res.j.status); toast("Đã xóa bài học", "ok");
        });
      return;
    }
  });

  document.addEventListener("submit", function (e) {
    var cf = e.target.closest && e.target.closest(".cmt-form");
    if (cf) {
      e.preventDefault();
      var input = cf.querySelector("input"), text = input.value.trim(); if (!text) return;
      postJSON("/api/posts/" + cf.getAttribute("data-post") + "/comments", { content: text }).then(function (res) {
        if (!res.ok) { toast(res.j.error || "Lỗi", "err"); return; }
        var post = cf.closest(".post"), box = post.querySelector(".comments");
        var div = document.createElement("div"); div.className = "cmt";
        div.innerHTML = "<b>" + esc(res.j.comment.author) + "</b> " + esc(res.j.comment.content);
        box.appendChild(div);
        var cc = post.querySelector(".cmt-count"); cc.textContent = (parseInt(cc.textContent, 10) || 0) + 1;
        input.value = "";
      });
      return;
    }
    var lf = e.target.closest && e.target.closest("#lesson-form");
    if (lf) {
      e.preventDefault();
      var lurl = document.getElementById("lesson-url").value.trim();
      var ltitle = document.getElementById("lesson-title").value.trim();
      if (!lurl) return;
      postJSON("/api/courses/" + lf.getAttribute("data-course") + "/lessons", { url: lurl, title: ltitle }).then(function (res) {
        if (!res.ok) { toast(res.j.error || "Link YouTube không hợp lệ", "err"); return; }
        if (res.j.pending) {
          document.getElementById("lesson-url").value = ""; document.getElementById("lesson-title").value = "";
          toast("🙌 Đã gửi đóng góp — chờ quản trị viên duyệt", "ok"); return;
        }
        toast("✓ Đã thêm bài học", "ok"); window.location.reload();
      });
      return;
    }
  });

  (function () {
    var btn = document.getElementById("msg-menu-btn");
    var pop = document.getElementById("msg-menu-pop");
    if (!btn || !pop) return;
    function setOpen(open) { pop.hidden = !open; btn.setAttribute("aria-expanded", String(open)); }
    btn.addEventListener("click", function (e) { e.stopPropagation(); setOpen(pop.hidden); });
    document.addEventListener("click", function (e) { if (!pop.contains(e.target) && e.target !== btn) setOpen(false); });
  })();

  (function () {
    var form = document.getElementById("dm-form");
    var log = document.getElementById("dm-log");
    if (!form || !log) return;
    var other = form.getAttribute("data-user");
    var seenEl = document.getElementById("dm-seen");
    var typingEl = document.getElementById("dm-typing");
    var lastId = 0;
    log.querySelectorAll(".dm").forEach(function (el) {
      var id = parseInt(el.getAttribute("data-id"), 10) || 0; if (id > lastId) lastId = id;
    });
    log.scrollTop = log.scrollHeight;

    function fmtMsgTime(iso) {
      var d = new Date(iso); if (isNaN(d.getTime())) return "";
      var now = new Date();
      var hm = d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
      if (d.toDateString() === now.toDateString()) return hm;
      var opts = d.getFullYear() === now.getFullYear()
        ? { day: "2-digit", month: "2-digit" }
        : { day: "2-digit", month: "2-digit", year: "numeric" };
      return d.toLocaleDateString("vi-VN", opts) + " " + hm;
    }
    log.querySelectorAll(".dm-time[datetime]").forEach(function (el) {
      el.textContent = fmtMsgTime(el.getAttribute("datetime"));
    });

    function clearSeen() { if (seenEl) seenEl.textContent = ""; }
    function showSeen() { if (seenEl) seenEl.textContent = "✓ Đã xem"; }

    function markRead() { cfetch("/api/messages/" + other + "/read", { method: "POST" }).catch(function () {}); }

    function buildDm(m, mine) {
      if (log.querySelector('.dm[data-id="' + m.id + '"]')) return;
      var d = document.createElement("div");
      d.className = "dm " + (mine ? "me" : "them"); d.setAttribute("data-id", m.id);
      var html = "";
      if (m.has_image) html += '<a href="/api/messages/media/' + m.id + '/image" target="_blank" rel="noopener"><img class="dm-media-img" src="/api/messages/media/' + m.id + '/image" alt="ảnh"></a>';
      if (m.has_video) html += '<video class="dm-media-video" src="/api/messages/media/' + m.id + '/video" controls preload="metadata"></video>';
      if (m.has_doc) html += '<a class="dm-doc" href="/api/messages/media/' + m.id + '/doc">📄 ' + esc(m.doc_original || "Tài liệu") + "</a>";
      if (m.post) {
        html += '<a class="dm-share post" href="/blog/' + m.post.id + '"><div class="dm-share-h">↪ Bài viết của <b>' + esc(m.post.author) + "</b></div>" +
          (m.post.content ? '<div class="dm-share-body">' + esc(m.post.content) + "</div>" : "") +
          ((m.post.has_image || m.post.has_video || m.post.has_doc) ? '<div class="dm-share-tag">📎 có đính kèm</div>' : "") + "</a>";
      }
      if (m.course) {
        html += '<a class="dm-share course" href="/courses/' + m.course.item_id + '"><div class="dm-share-h">📚 Khóa học / Tài liệu</div>' +
          '<div class="dm-share-title">' + esc(m.course.title) + "</div>" +
          '<div class="dm-share-tag">' + esc(m.course.type) + " · " + esc(m.course.category) + "</div></a>";
      }
      if (m.content) html += '<span class="dm-text">' + esc(m.content) + "</span>";
      d.innerHTML = '<div class="dm-bubble">' + html + "</div>" +
        '<time class="dm-time" datetime="' + esc(m.created_at) + '">' + esc(fmtMsgTime(m.created_at)) + "</time>";
      log.appendChild(d); log.scrollTop = log.scrollHeight;
      if (mine) clearSeen();
    }
    function poll() {
      fetch("/api/messages/" + other + "?after=" + lastId).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
        if (!j || !j.messages) return;
        j.messages.forEach(function (m) { lastId = Math.max(lastId, m.id); buildDm(m, m.sender_id === j.me); });
        if (j.messages.some(function (m) { return m.sender_id !== j.me; })) markRead();
      }).catch(function () {});
    }

    var imgI = document.getElementById("dm-image"), vidI = document.getElementById("dm-video"), docI = document.getElementById("dm-doc");
    var filesBox = document.getElementById("dm-files");
    function refreshFiles() {
      var items = [];
      if (imgI.files[0]) items.push(["🖼️", imgI.files[0].name, imgI]);
      if (vidI.files[0]) items.push(["🎬", vidI.files[0].name, vidI]);
      if (docI.files[0]) items.push(["📎", docI.files[0].name, docI]);
      filesBox.innerHTML = "";
      items.forEach(function (it) {
        var chip = document.createElement("span"); chip.className = "dm-file-chip";
        chip.innerHTML = it[0] + " " + esc(it[1]) + ' <button type="button" title="Bỏ">✕</button>';
        chip.querySelector("button").addEventListener("click", function () { it[2].value = ""; refreshFiles(); });
        filesBox.appendChild(chip);
      });
    }
    [imgI, vidI, docI].forEach(function (i) { if (i) i.addEventListener("change", refreshFiles); });

    var input = document.getElementById("dm-input");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = input.value.trim();
      var hasFile = imgI.files[0] || vidI.files[0] || docI.files[0];
      if (!text && !hasFile) return;
      var fd = new FormData();
      fd.append("to", other); fd.append("content", text);
      if (imgI.files[0]) fd.append("image", imgI.files[0]);
      if (vidI.files[0]) fd.append("video", vidI.files[0]);
      if (docI.files[0]) fd.append("doc", docI.files[0]);
      var btn = form.querySelector("button[type=submit]");
      if (btn) btn.disabled = true;
      cfetch("/api/messages", { method: "POST", body: fd })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (btn) btn.disabled = false;
          if (!res.ok) { toast(res.j.error || "Không gửi được", "err"); return; }
          input.value = ""; imgI.value = ""; vidI.value = ""; docI.value = ""; refreshFiles();
          if (res.j.message) { lastId = Math.max(lastId, res.j.message.id); buildDm(res.j.message, true); }
        }).catch(function () { if (btn) btn.disabled = false; toast("Lỗi mạng", "err"); });
    });

    RT.on("dm", function (d) {
      if (String(d.from) !== String(other) || !d.message) return;
      lastId = Math.max(lastId, d.message.id);
      buildDm(d.message, false);
      hideTyping();
      markRead();
    });

    RT.on("dm_read", function (d) { if (String(d.by) === String(other)) showSeen(); });

    var typingTimer = null;
    function hideTyping() { if (typingEl) { typingEl.hidden = true; } clearTimeout(typingTimer); }
    RT.on("typing", function (d) {
      if (String(d.from) !== String(other) || !typingEl) return;
      typingEl.hidden = false; log.scrollTop = log.scrollHeight;
      clearTimeout(typingTimer);
      typingTimer = setTimeout(function () { typingEl.hidden = true; }, 4000);
    });
    var lastTyping = 0;
    if (input) input.addEventListener("input", function () {
      var now = Date.now();
      if (now - lastTyping > 2500) {
        lastTyping = now;
        cfetch("/api/messages/" + other + "/typing", { method: "POST" }).catch(function () {});
      }
    });

    markRead();              
    setInterval(poll, 25000);
  })();

  function shareToFriend(payload, label) {
    fetch("/api/friends/list").then(function (r) { return r.ok ? r.json() : { friends: [] }; }).then(function (j) {
      var friends = (j && j.friends) || [];
      var ov = document.createElement("div");
      ov.className = "modal-ov";
      var list = friends.length
        ? friends.map(function (f) { return '<button type="button" class="friend-pick" data-id="' + f.id + '">👤 ' + esc(f.name) + "</button>"; }).join("")
        : '<p class="muted small" style="padding:8px 0">Bạn chưa có bạn bè nào. Hãy kết bạn trước để chia sẻ.</p>';
      ov.innerHTML =
        '<div class="modal" role="dialog" aria-modal="true">' +
        '<h3 class="modal-title">✉️ Chia sẻ vào tin nhắn</h3>' +
        '<p class="muted small">' + esc(label || "Chọn người bạn muốn gửi tới:") + "</p>" +
        '<div class="friend-pick-list">' + list + "</div>" +
        '<div class="modal-actions"><button type="button" class="btn-pill ghost modal-cancel">Đóng</button></div>' +
        "</div>";
      document.body.appendChild(ov);
      function close() { ov.remove(); }
      ov.addEventListener("click", function (e) { if (e.target === ov) close(); });
      ov.querySelector(".modal-cancel").addEventListener("click", close);
      ov.querySelectorAll(".friend-pick").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var body = Object.assign({ to: btn.getAttribute("data-id") }, payload);
          postJSON("/api/messages", body).then(function (res) {
            close();
            toast(res.ok ? "✓ Đã gửi vào tin nhắn" : (res.j.error || "Lỗi"), res.ok ? "ok" : "err");
          });
        });
      });
    }).catch(function () { toast("Lỗi mạng", "err"); });
  }

  document.addEventListener("click", function (e) {
    var cs = e.target.closest && e.target.closest("[data-share-course]");
    if (cs) { e.preventDefault(); shareToFriend({ shared_course_id: cs.getAttribute("data-share-course") }, "Gửi khóa học này tới:"); return; }
    var ps = e.target.closest && e.target.closest("[data-share-post]");
    if (ps) { e.preventDefault(); shareToFriend({ shared_post_id: ps.getAttribute("data-share-post") }, "Gửi bài viết này tới:"); return; }
  });
})();
