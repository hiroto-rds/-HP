/* =========================================================
   Rデザインスタジオ 営業支援 — main.js
   ========================================================= */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var config = window.RDS_CONFIG || {};

  /* ---------- Header: scrolled state ---------- */
  var header = document.querySelector(".site-header");
  var hero = document.querySelector(".hero");
  var mobileCta = document.querySelector(".mobile-cta");
  var contact = document.getElementById("contact");

  function onScroll() {
    var y = window.scrollY || window.pageYOffset;
    header.classList.toggle("is-scrolled", y > 24);

    if (mobileCta && hero && contact) {
      var pastHero = y > hero.offsetHeight - 80;
      var contactTop = contact.getBoundingClientRect().top;
      var atContact = contactTop < window.innerHeight * 0.85;
      mobileCta.classList.toggle("is-shown", pastHero && !atContact);
    }
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------- Mobile navigation ---------- */
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("global-nav");

  function setNav(open) {
    toggle.setAttribute("aria-expanded", String(open));
    toggle.querySelector(".visually-hidden").textContent = open ? "メニューを閉じる" : "メニューを開く";
    nav.classList.toggle("is-open", open);
    document.body.classList.toggle("nav-open", open);
  }
  toggle.addEventListener("click", function () {
    setNav(toggle.getAttribute("aria-expanded") !== "true");
  });
  nav.addEventListener("click", function (e) {
    if (e.target.closest("a")) setNav(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && nav.classList.contains("is-open")) {
      setNav(false);
      toggle.focus();
    }
  });
  window.addEventListener("resize", function () {
    if (window.innerWidth > 900 && nav.classList.contains("is-open")) setNav(false);
  });

  /* ---------- Scroll spy for nav ---------- */
  var navLinks = Array.prototype.slice.call(nav.querySelectorAll("ul a"));
  if ("IntersectionObserver" in window) {
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var id = "#" + entry.target.id;
        navLinks.forEach(function (a) {
          a.classList.toggle("is-current", a.getAttribute("href") === id);
        });
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    navLinks.forEach(function (a) {
      var href = a.getAttribute("href");
      if (href.charAt(0) !== "#") return; // 下層ページ（index.html#...）では監視しない
      var target = document.querySelector(href);
      if (target) spy.observe(target);
    });
  }

  /* ---------- Count-up numbers ---------- */
  function formatNum(n, comma) {
    return comma ? n.toLocaleString("ja-JP") : String(n);
  }
  function countUp(el) {
    var end = parseInt(el.getAttribute("data-count"), 10);
    var comma = el.getAttribute("data-format") === "comma";
    if (isNaN(end) || reduceMotion) {
      el.textContent = formatNum(end, comma);
      return;
    }
    var duration = end > 100 ? 1800 : 1100;
    var start = null;
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min((ts - start) / duration, 1);
      var eased = 1 - Math.pow(1 - p, 4);
      el.textContent = formatNum(Math.round(end * eased), comma);
      if (p < 1) requestAnimationFrame(step);
    }
    el.textContent = formatNum(0, comma);
    requestAnimationFrame(step);
  }

  /* ---------- Reveal on scroll ---------- */
  var reveals = Array.prototype.slice.call(document.querySelectorAll(".reveal"));

  function show(el) {
    el.classList.add("is-visible");
    Array.prototype.forEach.call(el.querySelectorAll("[data-count]"), countUp);
  }

  if ("IntersectionObserver" in window && !reduceMotion) {
    // 同じ親の中で順番に少しずつ遅らせて表示
    reveals.forEach(function (el) {
      var siblings = Array.prototype.filter.call(el.parentElement.children, function (c) {
        return c.classList.contains("reveal");
      });
      var idx = siblings.indexOf(el);
      if (idx > 0) el.style.transitionDelay = Math.min(idx * 90, 450) + "ms";
    });

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          show(entry.target);
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(show);
  }

  /* ---------- FAQ: only one open at a time ---------- */
  var faqItems = document.querySelectorAll(".faq-item");
  Array.prototype.forEach.call(faqItems, function (item) {
    item.addEventListener("toggle", function () {
      if (!item.open) return;
      Array.prototype.forEach.call(faqItems, function (other) {
        if (other !== item) other.open = false;
      });
    });
  });

  /* ---------- Footer year ---------- */
  var year = document.getElementById("year");
  if (year) year.textContent = new Date().getFullYear();

  /* =========================================================
     Contact form
     ========================================================= */
  var form = document.getElementById("contact-form");
  if (!form) return;

  var statusBox = form.querySelector(".form-status");
  var submitLabel = form.querySelector(".btn-label");
  var message = form.querySelector("#f-message");
  var charCount = form.querySelector(".char-count");

  message.addEventListener("input", function () {
    charCount.textContent = message.value.length;
  });

  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  function fieldOf(el) { return el.closest(".field"); }

  function setError(field, msg) {
    var box = field.querySelector(".field-error");
    field.classList.toggle("has-error", !!msg);
    if (box) box.textContent = msg || "";
    var controls = field.querySelectorAll("input, textarea");
    Array.prototype.forEach.call(controls, function (c) {
      if (c.type === "checkbox" && c.name === "topics") return;
      if (msg) c.setAttribute("aria-invalid", "true");
      else c.removeAttribute("aria-invalid");
    });
  }

  var validators = {
    company: function (v) { return v ? "" : "会社名・屋号を入力してください。"; },
    name: function (v) { return v ? "" : "お名前を入力してください。"; },
    email: function (v) {
      if (!v) return "メールアドレスを入力してください。";
      return EMAIL_RE.test(v) ? "" : "メールアドレスの形式をご確認ください。";
    },
    tel: function (v) {
      if (!v) return "";
      return /^[0-9０-９+\-−ー() ]{8,20}$/.test(v) ? "" : "電話番号の形式をご確認ください。";
    },
    business: function (v) { return v ? "" : "事業内容・商材を入力してください。"; },
    message: function (v) {
      if (!v) return "現在の課題・ご相談内容を入力してください。";
      return v.length > 3000 ? "3000文字以内で入力してください。" : "";
    }
  };

  function validateInput(input) {
    var fn = validators[input.name];
    if (!fn) return true;
    var msg = fn(input.value.trim());
    setError(fieldOf(input), msg);
    return !msg;
  }

  function validateTopics() {
    var checked = form.querySelectorAll('input[name="topics"]:checked').length > 0;
    var field = form.querySelector('input[name="topics"]').closest(".field");
    setError(field, checked ? "" : "ご相談内容を1つ以上選択してください。");
    return checked;
  }

  function validateConsent() {
    var c = form.querySelector('input[name="consent"]');
    setError(fieldOf(c), c.checked ? "" : "内容をご確認のうえ、チェックを入れてください。");
    return c.checked;
  }

  // 入力後（blur）に検証し、エラー表示中は入力ごとに再検証
  Object.keys(validators).forEach(function (name) {
    var input = form.elements[name];
    if (!input) return;
    input.addEventListener("blur", function () { if (input.value.trim()) validateInput(input); });
    input.addEventListener("input", function () {
      if (fieldOf(input).classList.contains("has-error")) validateInput(input);
    });
  });
  Array.prototype.forEach.call(form.querySelectorAll('input[name="topics"]'), function (c) {
    c.addEventListener("change", validateTopics);
  });
  form.querySelector('input[name="consent"]').addEventListener("change", validateConsent);

  function validateAll() {
    var ok = true;
    Object.keys(validators).forEach(function (name) {
      var input = form.elements[name];
      if (input && !validateInput(input)) ok = false;
    });
    if (!validateTopics()) ok = false;
    if (!validateConsent()) ok = false;
    return ok;
  }

  function showStatus(type, title, body) {
    statusBox.className = "form-status is-" + type;
    statusBox.innerHTML = "";
    var strong = document.createElement("strong");
    strong.textContent = title;
    statusBox.appendChild(strong);
    if (body) statusBox.appendChild(document.createTextNode(body));
    statusBox.focus({ preventScroll: true });
    statusBox.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
  }

  function buildPayload() {
    var data = new FormData(form);
    var topics = data.getAll("topics");
    data.delete("topics");
    data.set("topics", topics.join("、"));
    data.set("_subject", "【営業支援サイト】" + (data.get("company") || "") + " 様よりご相談");
    data.set("_replyto", data.get("email") || "");
    return data;
  }

  function setSending(sending) {
    form.classList.toggle("is-sending", sending);
    submitLabel.textContent = sending ? "送信しています…" : "この内容で相談する";
    form.querySelector('button[type="submit"]').disabled = sending;
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    if (!validateAll()) {
      var first = form.querySelector(".has-error input, .has-error textarea");
      if (first) first.focus();
      return;
    }

    // ボット対策：非表示項目に入力があれば送信しない（成功に見せる）
    if (form.elements._gotcha && form.elements._gotcha.value) {
      form.reset();
      showStatus("success", "送信が完了しました。", "");
      return;
    }

    var endpoint = (config.formEndpoint || "").trim();
    if (!endpoint) {
      showStatus(
        "info",
        "（デモ表示）フォームの送信先が未設定です。",
        "入力内容のチェックは正常に完了しましたが、実際には送信されていません。assets/js/config.js の formEndpoint を設定すると送信できるようになります。"
      );
      return;
    }

    setSending(true);

    fetch(endpoint, {
      method: "POST",
      body: buildPayload(),
      headers: { Accept: "application/json" }
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (json) {
          if (!res.ok || json.ok === false) {
            var msg = (json && (json.message || (json.errors && json.errors[0] && json.errors[0].message))) || "";
            throw new Error(msg || "HTTP " + res.status);
          }
          return json;
        });
      })
      .then(function () {
        form.reset();
        charCount.textContent = "0";
        showStatus(
          "success",
          "お問い合わせを受け付けました。",
          "内容を確認のうえ、ご入力いただいたメールアドレスへご連絡します。"
        );
      })
      .catch(function (err) {
        var mail = (config.fallbackEmail || "").trim();
        showStatus(
          "error",
          "送信できませんでした。",
          "時間をおいて再度お試しください。" +
            (mail ? "解決しない場合は " + mail + " までメールでご連絡ください。" : "") +
            (err && err.message && err.message.indexOf("HTTP") !== 0 ? "（" + err.message + "）" : "")
        );
      })
      .then(function () { setSending(false); });
  });
})();
