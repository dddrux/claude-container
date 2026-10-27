/* Skin do DeepSeek no tema do Claude.
 * Injetado pelo main.py (__PALETTE__ vira um JSON com as cores do tema atual).
 *
 * 1) CSS estático: fundo, seleção, cursor, scrollbars, fontes (texto em serifa, como no Claude).
 * 2) Remapeador de cores: as classes do DeepSeek são ofuscadas, então lê as cores calculadas de
 *    cada elemento e troca o azul da marca pelo laranja do Claude e os cinzas frios por tons
 *    quentes. O mapeamento dos cinzas é CONTÍNUO (cores parecidas continuam parecidas), os
 *    gradientes também são convertidos, e os elementos novos são pintados antes do primeiro
 *    frame (sem piscar). O estado :hover é lido na hora em que o mouse passa. */
(function () {
  if (window.__ccSkin) return;
  window.__ccSkin = true;
  var P = __PALETTE__;
  var DARK = !!P.dark;

  function sheet(text) {
    try {
      var sh = new CSSStyleSheet();
      if (text) sh.replaceSync(text);
      document.adoptedStyleSheets = document.adoptedStyleSheets.concat([sh]);
      return sh;
    } catch (e) { return null; }
  }

  /* ------------------------------------------------ CSS estático */
  sheet([
    ':root{color-scheme:' + (DARK ? 'dark' : 'light') + ';}',
    'html,body{background:' + P.bg + ';}',  // só fallback: o fundo real do site é remapeado, igual ao do cabeçalho
    // esconde até a primeira passada de cores terminar (evita o "flash" azul/cinza)
    'html:not([data-cc-ready]) body{visibility:hidden !important;}',
    'html[data-cc-probe] *{transition:none !important;}',
    '::selection{background:' + P.accent + ' !important;color:#fff !important;}',
    '*{caret-color:' + P.accent + ';}',
    'input::placeholder,textarea::placeholder{color:' + P.plus + ' !important;opacity:1;}',
    'body{font-family:-apple-system,"Inter","Segoe UI",system-ui,sans-serif !important;-webkit-font-smoothing:antialiased;}',
    '.ds-markdown p,.ds-markdown li,.ds-markdown blockquote{font-family:Georgia,"Iowan Old Style","Palatino Linotype","Times New Roman",serif;}',
    '.ds-markdown pre,.ds-markdown code,pre,code{font-family:ui-monospace,"JetBrains Mono","Fira Code","SF Mono",Consolas,monospace !important;}',
    'a{text-decoration-color:' + P.accent + ';}'
  ].join('\n'));

  /* ------------------------------------------------ cores */
  var dyn = sheet('');
  var ATTR = { bg: 'data-ccb', fg: 'data-ccf', bd: 'data-ccd', fl: 'data-ccl', sk: 'data-ccs', bi: 'data-cci',
               b0: 'data-ccb0', b1: 'data-ccb1', b2: 'data-ccb2', b3: 'data-ccb3' };
  var PROP = { bg: 'background-color', fg: 'color', bd: 'border-color', fl: 'fill', sk: 'stroke', bi: 'background-image',
               b0: 'border-top-color', b1: 'border-right-color', b2: 'border-bottom-color', b3: 'border-left-color' };
  var table = [], tindex = {}, done = {};

  function idx(v) {
    if (!(v in tindex)) { tindex[v] = table.length; table.push(v); }
    return tindex[v];
  }
  function ensureRule(kind, i, hov) {
    var key = kind + (hov ? 'h' : '') + i;
    if (done[key] || !dyn) return;
    done[key] = 1;
    var a = ATTR[kind] + (hov ? 'h' : '');
    try {
      dyn.insertRule('[' + a + '="' + i + '"]' + (hov ? ':hover' : ':not(:hover):not(:active)') +
        '{' + PROP[kind] + ':' + table[i] + ' !important}', dyn.cssRules.length);
    } catch (e) {}
  }
  function put(el, kind, val, hov) {
    if (val == null) return;
    var i = idx(val);
    ensureRule(kind, i, hov);
    el.setAttribute(ATTR[kind] + (hov ? 'h' : ''), i);
  }

  function parse(c) {
    var m = /rgba?\(([^)]+)\)/.exec(c || '');
    if (!m) return null;
    var a = m[1].split(/[ ,\/]+/).filter(Boolean).map(parseFloat);
    if (a.length < 3 || a.some(isNaN)) return null;
    return { r: a[0], g: a[1], b: a[2], a: a.length > 3 ? a[3] : 1 };
  }
  function toHsl(c) {
    var r = c.r / 255, g = c.g / 255, b = c.b / 255;
    var mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn, h = 0, s = 0;
    if (d) {
      s = d / (1 - Math.abs(2 * l - 1));
      if (mx === r) h = ((g - b) / d) % 6; else if (mx === g) h = (b - r) / d + 2; else h = (r - g) / d + 4;
      h *= 60; if (h < 0) h += 360;
    }
    return { h: h, s: s, l: l };
  }
  function fromHsl(h, s, l, a) {
    var C = (1 - Math.abs(2 * l - 1)) * s, X = C * (1 - Math.abs((h / 60) % 2 - 1)), m = l - C / 2, r, g, b;
    if (h < 60) { r = C; g = X; b = 0; } else if (h < 120) { r = X; g = C; b = 0; } else if (h < 180) { r = 0; g = C; b = X; }
    else if (h < 240) { r = 0; g = X; b = C; } else if (h < 300) { r = X; g = 0; b = C; } else { r = C; g = 0; b = X; }
    var R = Math.round((r + m) * 255), G = Math.round((g + m) * 255), B = Math.round((b + m) * 255);
    return a >= 1 ? 'rgb(' + R + ',' + G + ',' + B + ')' : 'rgba(' + R + ',' + G + ',' + B + ',' + a + ')';
  }
  function hexRgba(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return a >= 1 ? hex : 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function clamp(v) { return Math.max(0, Math.min(1, v)); }

  var WH = 48;  // matiz quente (Claude: bege/areia)

  /* Mapeia uma cor calculada para a cor do Claude. anyAlpha: usado em gradientes (mantém alpha). */
  function mapColor(kind, c, hov, anyAlpha) {
    if (!c || (c.a === 0 && !anyAlpha)) return null;
    var x = toHsl(c);
    // azul da marca -> laranja do Claude
    if (x.s > 0.3 && x.h >= 200 && x.h <= 265 && x.l > 0.12 && x.l < 0.88) {
      return hexRgba(hov && c.a >= 1 ? P.accent_hover : P.accent, c.a);
    }
    if (x.s >= 0.3) return null;
    // fundos translúcidos (cabeçalho com blur, caixa de mensagem) também precisam ser convertidos,
    // senão ficam na cor original por cima do fundo já convertido
    if (c.a < 1 && !anyAlpha && kind !== 'bg') return null;
    var l = x.l;
    if (kind === 'bg' || kind === 'bi') {
      if (DARK) {
        if (l > 0.93) return (anyAlpha || c.a < 1) ? null : P.text;
        if (l < 0.55) return fromHsl(WH, 0.05, clamp(l + 0.07), c.a);
      } else if (l > 0.88 && (c.a >= 1 || anyAlpha)) return fromHsl(WH, 0.22, clamp(l * 0.985), c.a);
    } else if (kind === 'fg' || kind === 'fl' || kind === 'sk') {
      if (DARK) {
        if (l > 0.45) return l > 0.97 ? P.text : fromHsl(WH, 0.05, l, c.a);
      } else if (l < 0.55) return fromHsl(WH, 0.04, Math.max(l, 0.075), c.a);
    } else if (kind === 'bd') {
      if (DARK && l < 0.40) return fromHsl(WH, 0.05, clamp(l + 0.05), c.a);
      if (!DARK && l > 0.70) return fromHsl(WH, 0.12, l * 0.985, c.a);
    }
    return null;
  }

  function mapGradient(img, hov) {
    if (!img || img.indexOf('gradient(') < 0) return null;
    var changed = false;
    var out = img.replace(/rgba?\([^)]*\)/g, function (tok) {
      var m = mapColor('bg', parse(tok), hov, true);
      if (m) { changed = true; return m; }
      return tok;
    });
    return changed ? out : null;
  }

  var SKIP = { SCRIPT: 1, STYLE: 1, LINK: 1, META: 1, HEAD: 1, TITLE: 1, NOSCRIPT: 1 };
  var SHAPES = { path: 1, circle: 1, rect: 1, line: 1, polyline: 1, polygon: 1, ellipse: 1, svg: 1, use: 1 };
  var SIDES = ['Top', 'Right', 'Bottom', 'Left'];

  /* lê as cores de um elemento (no estado atual) e grava os atributos; hov=true grava as regras :hover */
  function paint(el, hov) {
    var cs = getComputedStyle(el), par = el.parentElement, pcs = par ? getComputedStyle(par) : null;
    if (el instanceof SVGElement) {
      if (SHAPES[el.tagName.toLowerCase()]) {
        if (!pcs || cs.fill !== pcs.fill) put(el, 'fl', mapColor('fl', parse(cs.fill), hov), hov);
        if (!pcs || cs.stroke !== pcs.stroke) put(el, 'sk', mapColor('sk', parse(cs.stroke), hov), hov);
      }
      return;
    }
    put(el, 'bg', mapColor('bg', parse(cs.backgroundColor), hov), hov);
    if (!hov) put(el, 'bi', mapGradient(cs.backgroundImage, false), false);
    if (!pcs || cs.color !== pcs.color) put(el, 'fg', mapColor('fg', parse(cs.color), hov), hov);
    for (var q = 0; q < 4; q++) {
      if (parseFloat(cs['border' + SIDES[q] + 'Width']) > 0 && cs['border' + SIDES[q] + 'Style'] !== 'none') {
        // por lado: bordas transparentes (espaçadores) não podem virar barras visíveis
        put(el, 'b' + q, mapColor('bd', parse(cs['border' + SIDES[q] + 'Color']), hov), hov);
      }
    }
  }

  function proc(el, fresh) {
    if (el.nodeType !== 1 || !el.isConnected || SKIP[el.tagName]) return;
    if (fresh) {
      for (var k in ATTR) { el.removeAttribute(ATTR[k]); el.removeAttribute(ATTR[k] + 'h'); }
      el.removeAttribute('data-cc'); el.removeAttribute('data-cch');
    } else if (el.hasAttribute('data-cc')) return;
    if (!el.__ccL && el.matches(':hover,:active')) {
      // sob o mouse a cor lida é a de hover: pinta assim mesmo (melhor que mostrar a cor original
      // do site piscando) e refaz com a cor certa quando o mouse sair
      el.__ccL = 1;
      el.addEventListener('mouseleave', function () { el.__ccL = 0; fresh.add(el); kick(); }, { once: true });
    }
    paint(el, false);
    el.setAttribute('data-cc', '1');
  }

  /* hover: lê as cores "de hover" reais (sem transição) do alvo e dos ancestrais */
  document.addEventListener('mouseover', function (e) {
    var el = e.target, n = 0, todo = [];
    if (!document.documentElement) return;
    while (el && el.nodeType === 1 && n < 6) {
      if (!el.hasAttribute('data-cch') && !SKIP[el.tagName]) todo.push(el);
      el = el.parentElement; n++;
    }
    if (!todo.length) return;  // nada novo: não mexe no documento (evita recálculo/piscar)
    document.documentElement.setAttribute('data-cc-probe', '1');
    for (var i = 0; i < todo.length; i++) { paint(todo[i], true); todo[i].setAttribute('data-cch', '1'); }
    getComputedStyle(e.target).color;  // força o estilo final antes de religar as transições
    document.documentElement.removeAttribute('data-cc-probe');
  }, true);

  /* ------------------------------------------------ fila */
  var queue = new Set(), fresh = new Set(), work = [], sched = false, ready = false;

  function drain(budget) {
    queue.forEach(function (r) {
      work.push(r);
      var d = r.querySelectorAll ? r.querySelectorAll('*') : [];
      for (var i = d.length - 1; i >= 0; i--) work.push(d[i]);
    });
    queue.clear();
    fresh.forEach(function (e) { proc(e, true); });
    fresh.clear();
    var t = performance.now();
    while (work.length && performance.now() - t < budget) proc(work.pop(), false);
  }
  function setReady() {
    if (ready || !document.documentElement) return;
    ready = true;
    document.documentElement.setAttribute('data-cc-ready', '1');
  }
  function kick() {
    if (sched) return;
    sched = true;
    (window.requestIdleCallback || function (f) { setTimeout(f, 40); })(function () {
      sched = false;
      drain(12);
      if (work.length || queue.size || fresh.size) kick();
      else if (document.readyState !== 'loading') setReady();
    }, { timeout: 200 });
  }

  var mo = new MutationObserver(function (ms) {
    for (var i = 0; i < ms.length; i++) {
      var m = ms[i];
      if (m.type === 'childList') {
        for (var j = 0; j < m.addedNodes.length; j++)
          if (m.addedNodes[j].nodeType === 1) queue.add(m.addedNodes[j]);
      } else if (m.target.nodeType === 1) {
        if (m.target === document.documentElement || m.target === document.body) {
          var all = document.querySelectorAll('[data-cc]');  // troca de tema do próprio site
          for (var k = 0; k < all.length; k++) fresh.add(all[k]);
        } else fresh.add(m.target);
      }
    }
    drain(14);  // síncrono (antes do próximo frame) -> elementos novos já nascem na cor certa
    if (work.length || queue.size || fresh.size) kick();
  });
  mo.observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style'] });

  function start() {
    if (document.documentElement) { queue.add(document.documentElement); kick(); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
  window.addEventListener('load', function () { start(); setTimeout(setReady, 150); });
  setTimeout(setReady, 1800);  // segurança: nunca deixa a página escondida
})();
