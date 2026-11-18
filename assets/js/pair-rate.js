/*
 * ConvertCCY pair-page rate enhancement (SEO-A3).
 *
 * The page's static HTML already contains the answer: a reference-snapshot
 * rate, its inverse, a conversion table and the snapshot's as-of date, all
 * derived from /rates/snapshot.json at build time. This script only ENHANCES:
 *
 *   1. Try the live source (time-boxed). On success, replace the values and
 *      label them as a live reference value with the provider's date.
 *   2. If live fails, use /rates/snapshot.json only when it is NEWER than the
 *      snapshot baked into the HTML (the JSON can be refreshed independently).
 *   3. Otherwise leave the static values untouched. Never fall back to
 *      "Loading…" or "unavailable" over a valid static value.
 *
 * Precision policy mirrors generate.py (format_rate_value): a published rate
 * carries 2 decimals or 3 significant digits, whichever is finer; shown with
 * clamp(floor(-log10(relative uncertainty)), 3, 6) significant digits,
 * half-up rounding, plain decimal notation with thousands separators.
 */
(function () {
  'use strict';

  var root = document.getElementById('rate-root');
  if (!root) { return; }

  var FROM = root.getAttribute('data-from');
  var TO = root.getAttribute('data-to');
  var LIVE_ENDPOINT = 'https://api.exchangerate-api.com/v4/latest/';
  var LIVE_TIMEOUT_MS = 3500;
  var SIG_MIN = 3, SIG_MAX = 6;

  var state = {
    mode: root.getAttribute('data-mode') || 'unsupported',  // snapshot | live | unsupported
    rate: parseFloat(root.getAttribute('data-rate')),
    sig: parseInt(root.getAttribute('data-sig'), 10) || SIG_MIN,
    asOf: root.getAttribute('data-asof') || ''
  };
  if (!(state.rate > 0)) { state.rate = null; }

  function exponentOf(x) {
    // Exact decimal exponent (avoids Math.log10 rounding at powers of ten).
    return parseInt(Number(x).toExponential().split('e')[1], 10);
  }

  function legUncertainty(v, isBase) {
    if (isBase) { return 0; }
    var last = Math.min(-2, exponentOf(v) - 2);
    return 0.5 * Math.pow(10, last) / v;
  }

  function sigFor(u) {
    if (!(u > 0)) { return SIG_MAX; }
    return Math.max(SIG_MIN, Math.min(SIG_MAX, Math.floor(-Math.log10(u))));
  }

  function fmt(x, sig) {
    var r = Number(Number(x).toPrecision(sig));
    var fd = Math.max(0, sig - 1 - exponentOf(r));
    return r.toLocaleString('en-US', { minimumFractionDigits: fd, maximumFractionDigits: Math.min(fd, 20) });
  }

  function byId(id) { return document.getElementById(id); }
  function setText(id, text) { var el = byId(id); if (el) { el.textContent = text; } }

  function render(label, badgeText, badgeClass, sourceText) {
    var r = state.rate, s = state.sig;
    var main = '1 ' + FROM + ' = ' + fmt(r, s) + ' ' + TO;
    setText('live-rate', main);
    var sub = byId('rate-sub');
    if (sub) {
      sub.textContent = '1 ' + TO + ' = ';
      var span = document.createElement('span');
      span.id = 'inverse-rate';
      span.textContent = fmt(1 / r, s);
      sub.appendChild(span);
      sub.appendChild(document.createTextNode(' ' + FROM));
    }
    var badge = byId('rate-badge');
    if (badge) { badge.textContent = badgeText; badge.className = 'rate-badge' + (badgeClass ? ' ' + badgeClass : ''); }
    setText('rate-source', sourceText);
    setText('table-source', label);
    var tbody = byId('conv-table');
    if (tbody) {
      var rows = tbody.querySelectorAll('tr[data-amount]');
      if (rows.length) {
        for (var i = 0; i < rows.length; i++) {
          var a = parseFloat(rows[i].getAttribute('data-amount'));
          var cell = rows[i].cells[1];
          if (cell && a > 0) { cell.textContent = fmt(a * r, s) + ' ' + TO; }
        }
      } else {
        // Unsupported page upgraded by a live value: build rows from the
        // project-wide static amounts.
        var amounts = [1, 5, 10, 20, 50, 100, 500, 1000, 10000];
        tbody.textContent = '';
        amounts.forEach(function (a) {
          var tr = document.createElement('tr');
          tr.setAttribute('data-amount', String(a));
          var td1 = document.createElement('td'); td1.textContent = a.toLocaleString('en-US') + ' ' + FROM;
          var td2 = document.createElement('td'); td2.textContent = fmt(a * r, s) + ' ' + TO;
          tr.appendChild(td1); tr.appendChild(td2); tbody.appendChild(tr);
        });
      }
    }
    setText('rate-info', label);
    convertFrom();
  }

  function convertFrom() {
    var fi = byId('from-input'), ti = byId('to-input');
    if (!fi || !ti || !state.rate) { return; }
    var a = parseFloat(fi.value) || 0;
    var b = a * state.rate;
    ti.value = b > 0 ? fmt(b, state.sig).replace(/,/g, '') : '0';
    setText('main-result', (a || 0).toLocaleString('en-US') + ' ' + FROM + ' = ' + (b > 0 ? fmt(b, state.sig) : '0') + ' ' + TO);
  }

  function convertTo() {
    var fi = byId('from-input'), ti = byId('to-input');
    if (!fi || !ti || !state.rate) { return; }
    var b = parseFloat(ti.value) || 0;
    var a = b / state.rate;
    fi.value = a > 0 ? fmt(a, state.sig).replace(/,/g, '') : '0';
    setText('main-result', (b || 0).toLocaleString('en-US') + ' ' + TO + ' = ' + (a > 0 ? fmt(a, state.sig) : '0') + ' ' + FROM);
  }

  window.setAmt = function (n) {
    var fi = byId('from-input');
    if (fi) { fi.value = n; convertFrom(); }
  };
  window.swapPair = function () {
    window.location.href = '/pages/' + TO.toLowerCase() + '-to-' + FROM.toLowerCase() + '.html';
  };

  var fiEl = byId('from-input'), tiEl = byId('to-input');
  if (fiEl) { fiEl.addEventListener('input', convertFrom); }
  if (tiEl) { tiEl.addEventListener('input', convertTo); }

  function fetchJson(url, opts) {
    return fetch(url, opts).then(function (res) {
      if (!res.ok) { throw new Error('http ' + res.status); }
      return res.json();
    });
  }

  function tryLive() {
    var ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, LIVE_TIMEOUT_MS) : null;
    return fetchJson(LIVE_ENDPOINT + encodeURIComponent(FROM), ctrl ? { signal: ctrl.signal } : {})
      .then(function (data) {
        var r = data && data.rates && data.rates[TO];
        if (typeof r !== 'number' || !isFinite(r) || r <= 0) { throw new Error('live rate missing'); }
        var date = typeof data.date === 'string' ? data.date : '';
        state.rate = r;
        state.sig = sigFor(legUncertainty(r, false));
        state.mode = 'live';
        var dated = date ? ' (provider date ' + date + ')' : '';
        render('Live reference value' + dated,
               'LIVE' + (date ? ' · ' + date : ''), '',
               'Live reference value from exchangerate-api.com' + dated +
               '. Indicative only — not a dealing rate; providers apply their own spread and fees.');
      })
      .finally(function () { if (timer) { clearTimeout(timer); } });
  }

  function tryNewerSnapshot() {
    return fetchJson('/rates/snapshot.json', { cache: 'no-cache' }).then(function (s) {
      var asOf = s && s.as_of;
      var rf = s && s.rates && s.rates[FROM], rt = s && s.rates && s.rates[TO];
      if (!asOf || !(rf > 0) || !(rt > 0)) { return; }
      if (state.asOf && asOf <= state.asOf) { return; }  // baked value is as new or newer
      state.rate = rt / rf;
      state.sig = sigFor(legUncertainty(rf, FROM === s.base) + legUncertainty(rt, TO === s.base));
      state.mode = 'snapshot';
      state.asOf = asOf;
      render('Reference snapshot as of ' + asOf,
             'SNAPSHOT · ' + asOf, 'snap',
             'Reference snapshot as of ' + asOf + ' · source: ' + (s.source || 'exchangerate-api.com') +
             ' (USD-based reference rates, cross-calculated by ConvertCCY). Indicative only — not a live or dealing rate.');
    });
  }

  // Expose the pure helpers for tests; harmless in production.
  window.__convertccyRate = { fmt: fmt, sigFor: sigFor, legUncertainty: legUncertainty, state: state };

  tryLive().catch(function () {
    return tryNewerSnapshot().catch(function () { /* keep static values */ });
  });
})();
