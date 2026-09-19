/* Theme toggle + the chart hover layer. No dependencies. */

(function theme() {
  var btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('dwts-theme', next);
  });
})();

(function charts() {
  document.querySelectorAll('.chart-wrap[data-chart]').forEach(function (wrap) {
    var spec;
    try {
      spec = JSON.parse(wrap.dataset.chart);
    } catch (e) {
      return;
    }
    var svg = wrap.querySelector('svg');
    var cross = wrap.querySelector('.crosshair');
    var tip = wrap.querySelector('.tooltip');
    if (!svg || !tip || !spec.labels.length) return;

    var g = spec.geometry;
    var n = spec.labels.length;

    function xAt(i) {
      return n === 1 ? g.left + g.width / 2 : g.left + (g.width * i) / (n - 1);
    }

    function show(event) {
      var rect = svg.getBoundingClientRect();
      var scale = rect.width / g.vbWidth;
      var vx = (event.clientX - rect.left) / scale;
      var i = n === 1 ? 0 : Math.round(((vx - g.left) / g.width) * (n - 1));
      i = Math.max(0, Math.min(n - 1, i));

      if (cross) {
        cross.setAttribute('x1', xAt(i));
        cross.setAttribute('x2', xAt(i));
        cross.style.opacity = 1;
      }

      var rows = spec.series
        .map(function (s, k) {
          return (
            '<div class="row"><span class="swatch" style="background:var(--series-' +
            (k + 1) +
            ')"></span>' +
            s.name +
            '<b>' +
            (s.values[i] === undefined ? '—' : s.values[i]) +
            '</b></div>'
          );
        })
        .join('');
      tip.innerHTML = '<h4>' + spec.labels[i] + '</h4>' + rows;
      tip.style.opacity = 1;

      var px = xAt(i) * scale;
      var flip = px > rect.width - tip.offsetWidth - 24;
      tip.style.left = (flip ? px - tip.offsetWidth - 14 : px + 14) + 'px';
      tip.style.top = Math.max(0, event.clientY - rect.top - tip.offsetHeight / 2) + 'px';
    }

    function hide() {
      tip.style.opacity = 0;
      if (cross) cross.style.opacity = 0;
    }

    svg.addEventListener('mousemove', show);
    svg.addEventListener('mouseleave', hide);
    svg.addEventListener('touchmove', function (e) {
      if (e.touches.length) show(e.touches[0]);
    }, { passive: true });
    svg.addEventListener('touchend', hide);
  });
})();
