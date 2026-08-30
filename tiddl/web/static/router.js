// 手写迷你路由:/ 与 /player 共存于同一文档,切换只显隐视图容器。
// 音频元素在壳文档内,路由切换不卸载任何脚本上下文,播放天然连续。
(function () {
  const ROUTES = { "/": "downloads", "/player": "player" };
  const TITLES = { downloads: "Abducted Tidal Player", player: "Player - Abducted Tidal Player" };

  function currentRoute() { return ROUTES[location.pathname] || "downloads"; }

  function apply(route) {
    document.body.dataset.route = route;
    document.body.classList.toggle("player-body", route === "player");
    document.getElementById("view-downloads").hidden = route !== "downloads";
    document.getElementById("view-player").hidden = route !== "player";
    document.querySelectorAll("[data-route-link]").forEach(a => a.classList.toggle("active", a.dataset.routeLink === route));
    document.title = TITLES[route];
  }

  function navigate(path) {
    if (location.pathname === path) return apply(currentRoute());
    history.pushState({}, "", path);
    apply(currentRoute());
  }

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest("a[href]");
    if (!link) return;
    const href = link.getAttribute("href");
    if (href !== "/" && href !== "/player") return;
    event.preventDefault();
    navigate(href);
  });

  window.addEventListener("popstate", () => {
    const route = currentRoute();
    apply(route);
    if (route === "player" && window.ATPPlayer) window.ATPPlayer.enter();
  });

  apply(currentRoute());
  if (currentRoute() === "player" && window.ATPPlayer) window.ATPPlayer.enter();
})();
