(function () {
  const remote = window.IRPRemote;
  const elements = remote.elements;

  function createDropdown(options) {
    const root = options.root;
    const button = options.button;
    const menu = options.menu || root;
    const updateExpanded = Boolean(options.updateExpanded);

    function close() {
      if (!root || !menu) {
        return;
      }
      root.classList.remove("is-open");
      if (updateExpanded && button) {
        button.setAttribute("aria-expanded", "false");
      }
      menu.setAttribute("aria-hidden", "true");
    }

    function open() {
      if (!root || !menu) {
        return;
      }
      root.classList.add("is-open");
      if (updateExpanded && button) {
        button.setAttribute("aria-expanded", "true");
      }
      menu.setAttribute("aria-hidden", "false");
    }

    function toggle() {
      if (!root) {
        return;
      }
      if (root.classList.contains("is-open")) {
        close();
      } else {
        open();
      }
    }

    function contains(target) {
      if (!target) {
        return false;
      }
      return Boolean(
        (root && root.contains(target)) ||
        (button && button.contains(target))
      );
    }

    return {
      close: close,
      open: open,
      toggle: toggle,
      contains: contains,
    };
  }

  const stop = createDropdown({
    root: elements.stopDropdown,
    button: elements.stopToggle,
  });
  const modelProvider = createDropdown({
    root: elements.modelProviderDropdown,
    button: elements.modelProviderButton,
    menu: elements.modelProviderMenu,
    updateExpanded: true,
  });
  const loadoutProvider = createDropdown({
    root: elements.loadoutProviderDropdown,
    button: elements.loadoutProviderButton,
    menu: elements.loadoutProviderMenu,
    updateExpanded: true,
  });

  function closeForView(viewName) {
    if (viewName !== "model-switch") {
      modelProvider.close();
    }
    if (viewName !== "loadout-switch") {
      loadoutProvider.close();
    }
  }

  function bindOutsideClicks() {
    document.addEventListener("click", function (event) {
      const target = event.target;
      if (!stop.contains(target)) {
        stop.close();
      }
      if (!modelProvider.contains(target)) {
        modelProvider.close();
      }
      if (!loadoutProvider.contains(target)) {
        loadoutProvider.close();
      }
    });
  }

  remote.dropdowns = {
    stop: stop,
    modelProvider: modelProvider,
    loadoutProvider: loadoutProvider,
    closeForView: closeForView,
    bindOutsideClicks: bindOutsideClicks,
  };
})();
