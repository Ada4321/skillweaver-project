// Progressive enhancement only — every section is reachable, every trajectory
// figure is present, and the BibTeX is selectable without any of this running.
(function () {
  /* ---------- Side navigation ---------- */
  const sidenav = document.querySelector('.sidenav');
  const hero = document.querySelector('.hero');

  if (sidenav) {
    // Each tracked section element -> its nav link, kept in document order.
    const links = new Map();
    sidenav.querySelectorAll('a[href^="#"]').forEach((a) => {
      const el = document.getElementById(a.getAttribute('href').slice(1));
      if (el) links.set(el, a);
    });

    if (links.size) {
      const list = sidenav.querySelector('ul');

      // Grow the spectrum progress fill down to the active node's centre.
      const setProgress = (link) => {
        if (!list) return;
        const center = link.offsetTop + link.offsetHeight / 2;
        list.style.setProperty('--nav-progress', `${Math.max(0, center - 17)}px`);
      };

      // Highlight the section nearest the viewport's vertical middle.
      const spy = new IntersectionObserver((entries) => {
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          const active = links.get(e.target);
          if (!active) return;
          links.forEach((a) => a.classList.toggle('is-active', a === active));
          setProgress(active);
        });
      }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });

      links.forEach((_, section) => spy.observe(section));

      // Reveal the nav only after the hero leaves the viewport.
      if (hero) {
        new IntersectionObserver((entries) => {
          sidenav.classList.toggle('is-visible', !entries[0].isIntersecting);
        }, { threshold: 0.12 }).observe(hero);
      } else {
        sidenav.classList.add('is-visible');
      }
    }
  }

  /* ---------- Section reveal ----------
     One-way on purpose: re-running the animation every time a section scrolls
     back into view turns a settling effect into a flicker. The threshold stays
     low because the tallest section runs past three screens and would never
     reach a high one. */
  if ('IntersectionObserver' in window) {
    const reveal = new IntersectionObserver((entries, obs) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        e.target.classList.add('is-in');
        obs.unobserve(e.target);
      });
    }, { rootMargin: '0px 0px -16% 0px', threshold: 0.04 });
    document.querySelectorAll('.section').forEach((s) => reveal.observe(s));
  }

  /* ---------- Trajectory tabs ----------
     The panels ship visible so the figures are all there with JS off; the
     first thing this does is collapse them down to the selected one. */
  document.querySelectorAll('[data-tabs]').forEach((group) => {
    const tabs = [...group.querySelectorAll('[role="tab"]')];
    const panels = tabs.map((t) => document.getElementById(t.getAttribute('aria-controls')));

    const select = (i) => {
      tabs.forEach((t, j) => {
        t.setAttribute('aria-selected', String(j === i));
        t.tabIndex = j === i ? 0 : -1;
        if (panels[j]) panels[j].hidden = j !== i;
      });
    };

    tabs.forEach((t, i) => {
      t.addEventListener('click', () => select(i));
      // Left/right arrows move between tabs, per the tablist pattern.
      t.addEventListener('keydown', (e) => {
        const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
        if (!d) return;
        e.preventDefault();
        const next = (i + d + tabs.length) % tabs.length;
        select(next);
        tabs[next].focus();
      });
    });

    select(tabs.findIndex((t) => t.getAttribute('aria-selected') === 'true') || 0);
  });

  /* ---------- Copy BibTeX ---------- */
  document.querySelectorAll('[data-copy]').forEach((btn) => {
    const src = document.getElementById(btn.getAttribute('data-copy'));
    if (!src || !navigator.clipboard) return;
    btn.hidden = false;
    btn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(src.textContent.trim());
        const was = btn.textContent;
        btn.textContent = 'Copied';
        btn.classList.add('is-done');
        setTimeout(() => {
          btn.textContent = was;
          btn.classList.remove('is-done');
        }, 1600);
      } catch (_) {
        /* Clipboard blocked (insecure origin, denied permission) — the BibTeX
           is right there to select by hand, so there is nothing to report. */
      }
    });
  });
})();
