/**
 * Robust toggle for "Ver materias" per career group.
 * Ensures proper collapse/expand and nicer button classes.
 */

function initSubjectToggle() {
  try {
    document.querySelectorAll('.grupo-carrera-perfil-fie').forEach(function (group) {
      var btn = group.querySelector('.eur-carrera-toggle, .collapse-toggle');
      var list = group.querySelector('.eur-carrera-content, .eur-carrera-collapse');

      if (!btn || !list) return;

      // Remove legacy inline handler to avoid double-toggling
      if (btn.hasAttribute('onclick')) {
        btn.removeAttribute('onclick');
      }

      // Improve button look if needed
      btn.classList.add('btn', 'btn-sm', 'btn-outline-secondary', 'rounded-pill');
      btn.classList.remove('btn-link');

      // Ensure hidden by default (no Bootstrap dependency)
      var isCollapsed = true;
      if (list.classList.contains('collapse')) {
        // If some themes inject collapse, respect it
        isCollapsed = !list.classList.contains('show');
      } else {
        // Always start hidden
        list.classList.add('d-none');
        isCollapsed = true;
      }

      // Apply collapsed marker to toggle
      if (isCollapsed) btn.classList.add('collapsed');

      // Ensure hidden by default when needed
      if (!list.classList.contains('collapse')) {
        if (isCollapsed) list.classList.add('d-none');
      }

      // Label helpers
      function setLabel(collapsed) {
        var showSpan = btn.querySelector('.when-collapsed');
        var hideSpan = btn.querySelector('.when-not-collapsed');
        var pager = group.querySelector('.eur-pager');
        if (collapsed) {
          if (showSpan) showSpan.style.display = '';
          if (hideSpan) hideSpan.style.display = 'none';
          btn.classList.add('collapsed');
          btn.setAttribute('aria-expanded', 'false');
          if (pager) pager.style.display = 'none';
        } else {
          if (showSpan) showSpan.style.display = 'none';
          if (hideSpan) hideSpan.style.display = '';
          btn.classList.remove('collapsed');
          btn.setAttribute('aria-expanded', 'true');
          if (pager) pager.style.display = '';
        }
      }
      setLabel(isCollapsed);

      // Click handler
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();

        var collapsed;
        if (list.classList.contains('collapse')) {
          // Bootstrap collapse integration
          // If Bootstrap JS is present, it will toggle classes; otherwise we toggle directly.
          if (typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
            var instance = bootstrap.Collapse.getOrCreateInstance(list, { toggle: true });
            // After BS toggles, check class to update labels a bit later
            setTimeout(function () {
              setLabel(!list.classList.contains('show'));
            }, 50);
            return;
          } else {
            list.classList.toggle('show');
            collapsed = !list.classList.contains('show');
          }
        } else {
          list.classList.toggle('d-none');
          collapsed = list.classList.contains('d-none');
        }

        setLabel(collapsed);
        group.classList.toggle('eur-carrera-expanded', !collapsed);
      });
    });
  } catch (e) {
    // silent
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSubjectToggle);
} else {
  initSubjectToggle();
}

// Pagination of career groups within the assignments section
// Shows 3 .grupo-carrera-perfil-fie per page inside each
// .asignaturas-agrupadas-perfil-fie container
function initAssignmentsPagination() {
  try {
    // Legacy overlay/toggle removed from template; no-op

    // For each assignments container, paginate its group blocks
    document.querySelectorAll('.asignaturas-agrupadas-perfil-fie').forEach(function (container) {
      var groups = Array.prototype.slice.call(container.querySelectorAll('.grupo-carrera-perfil-fie'));
      var pageSize = 3;
      var total = groups.length;
      var totalPages = Math.ceil(total / pageSize);
      if (totalPages <= 1) return; // nothing to paginate

      // Remove existing pager in section
      var next = container.nextElementSibling; if (next && next.classList && next.classList.contains('eur-pager')) { next.remove(); }

      // Build pager UI
      var pager = document.createElement('div');
      pager.className = 'eur-pager';

      var prevBtn = document.createElement('button');
      prevBtn.className = 'eur-page-btn eur-prev';
      prevBtn.textContent = String.fromCharCode(8249);
      pager.appendChild(prevBtn);

      var pageBtns = [];
      for (var p = 1; p <= totalPages; p++) {
        var b = document.createElement('button');
        b.className = 'eur-page-btn';
        b.textContent = String(p);
        b.dataset.page = String(p);
        pager.appendChild(b);
        pageBtns.push(b);
      }

      var nextBtn = document.createElement('button');
      nextBtn.className = 'eur-page-btn eur-next';
      nextBtn.textContent = String.fromCharCode(8250);
      pager.appendChild(nextBtn);

      // Insert pager after the container
      container.parentNode.insertBefore(pager, container.nextSibling);

      var currentPage = 1;
      function render() {
        var start = (currentPage - 1) * pageSize;
        var end = Math.min(start + pageSize, total);
        var lastVisibleIdx = -1;
        // hide all
        groups.forEach(function (grp) {
          grp.classList.add('hidden-item');
          grp.classList.remove('is-last-visible');
        });
        // show current page
        groups.forEach(function (grp, idx) {
          if (idx >= start && idx < end) {
            grp.classList.remove('hidden-item');
            lastVisibleIdx = idx;
          }
        });
        // mark last visible to remove bottom margin
        if (lastVisibleIdx >= 0) {
          groups[lastVisibleIdx].classList.add('is-last-visible');
        }
        pageBtns.forEach(function (b, idx) {
          if (idx + 1 === currentPage) b.classList.add('active'); else b.classList.remove('active');
        });
        prevBtn.disabled = currentPage === 1;
        nextBtn.disabled = currentPage === totalPages;
      }
      render();

      pager.addEventListener('click', function (ev) {
        var t = ev.target;
        if (!(t instanceof HTMLElement)) return;
        if (t.classList.contains('eur-prev')) {
          if (currentPage > 1) { currentPage--; render(); }
          return;
        }
        if (t.classList.contains('eur-next')) {
          if (currentPage < totalPages) { currentPage++; render(); }
          return;
        }
        if (t.classList.contains('eur-page-btn') && t.dataset.page) {
          var pp = parseInt(t.dataset.page, 10);
          if (!isNaN(pp)) { currentPage = pp; render(); }
          return;
        }
      });
    });
  } catch (e) {
    // silent
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAssignmentsPagination);
} else {
  initAssignmentsPagination();
}






