(() => {
  const header = document.getElementById("header");
  const menu = document.getElementById("hamburger");
  const links = document.getElementById("navLinks");
  if (!header || !menu || !links) return;
  menu.addEventListener("click", () => {
    const open = links.classList.toggle("open");
    menu.setAttribute("aria-expanded", String(open));
  });
  links.addEventListener("click", event => {
    if (event.target.closest("a")) {
      links.classList.remove("open");
      menu.setAttribute("aria-expanded", "false");
    }
  });
  addEventListener("scroll", () => header.classList.toggle("scrolled", scrollY > 10), {passive:true});
})();
