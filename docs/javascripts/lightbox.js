/*
 * Lightbox: a screenshot or a Mermaid diagram opens large in a modal.
 *
 * Images are copied into the modal and sized by CSS. Material renders each
 * diagram into a closed shadow root, which cannot be read or cloned, so the
 * diagram source is kept from before Material mounts and Mermaid renders a
 * second copy for the modal, as wide as the viewport allows and at most twice
 * its natural size. The script runs after Material's bundle but before
 * DOMContentLoaded, which is when Material mounts, once per full page load:
 * it relies on navigation.instant staying off in mkdocs.yml.
 */
(function () {
  "use strict";

  var IMAGE = ".md-typeset img:not(.twemoji)";
  var sources = new WeakMap();
  var renders = 0;
  var overlay = null;
  var box = null;
  var opener = null;

  // Material replaces each pre.mermaid with a rendered div. The wrapper around
  // it survives, remembers the source and is the click target.
  document.querySelectorAll(".md-typeset pre.mermaid").forEach(function (pre) {
    var wrapper = document.createElement("div");
    wrapper.className = "lightbox-diagram";
    wrapper.tabIndex = 0;
    wrapper.setAttribute("role", "button");
    wrapper.setAttribute("aria-label", "Enlarge diagram");
    sources.set(wrapper, pre.textContent);
    pre.replaceWith(wrapper);
    wrapper.appendChild(pre);
  });

  document.querySelectorAll(IMAGE).forEach(function (img) {
    if (img.closest("a")) return;
    img.tabIndex = 0;
    img.setAttribute("role", "button");
  });

  function build() {
    overlay = document.createElement("div");
    overlay.className = "lightbox";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Enlarged view");
    overlay.hidden = true;
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) close();
    });

    var button = document.createElement("button");
    button.type = "button";
    button.className = "lightbox__close";
    button.setAttribute("aria-label", "Close");
    button.textContent = "×";
    button.addEventListener("click", close);

    box = document.createElement("div");
    box.className = "lightbox__box";

    overlay.append(button, box);
    document.body.appendChild(overlay);
  }

  function open(content, trigger) {
    if (!overlay) build();
    opener = trigger;
    box.replaceChildren(content);
    overlay.hidden = false;
    document.documentElement.classList.add("lightbox-open");
    overlay.querySelector(".lightbox__close").focus();
  }

  function close() {
    overlay.hidden = true;
    box.replaceChildren();
    document.documentElement.classList.remove("lightbox-open");
    if (opener && opener.isConnected) opener.focus();
    opener = null;
  }

  function openImage(img) {
    var copy = new Image();
    copy.src = img.currentSrc || img.src;
    copy.alt = img.alt;
    copy.className = "lightbox__image";
    open(copy, img);
  }

  function openDiagram(wrapper) {
    var source = sources.get(wrapper);
    if (!source || typeof mermaid === "undefined") return;
    renders += 1;
    mermaid.render("lightbox-" + renders, source).then(function (result) {
      var holder = document.createElement("div");
      holder.className = "lightbox__diagram";
      holder.innerHTML = result.svg;
      open(holder, wrapper);
      fit(holder.querySelector("svg"));
    });
  }

  // As wide as the box allows and at most twice the natural width. A tall
  // diagram scrolls inside the box instead of shrinking below page size.
  function fit(svg) {
    var natural = svg.viewBox.baseVal.width;
    var style = getComputedStyle(box);
    box.style.width = "100%";
    var available =
      box.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    box.style.width = "";
    svg.style.maxWidth = "none";
    svg.style.height = "auto";
    svg.style.width = Math.min(available, 2 * natural) + "px";
  }

  document.addEventListener("click", function (event) {
    if (event.defaultPrevented || event.button !== 0) return;
    var target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    var wrapper = target.closest(".lightbox-diagram");
    if (wrapper) {
      openDiagram(wrapper);
      return;
    }
    var img = target.closest(IMAGE);
    if (img && !img.closest("a")) openImage(img);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && overlay && !overlay.hidden) {
      close();
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") return;
    var el = document.activeElement;
    if (!el || !(el.classList.contains("lightbox-diagram") || el.matches(IMAGE))) return;
    event.preventDefault();
    el.click();
  });
})();
