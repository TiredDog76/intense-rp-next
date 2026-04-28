(function () {
  const remote = window.IRPRemote;
  const state = remote.state;
  const elements = remote.elements;

  function show(name) {
    elements.views.forEach((view, key) => {
      view.classList.toggle("is-active", key === name);
    });
    state.currentView = name;

    if (name === "logs") {
      remote.logs.start();
    } else {
      remote.logs.stop();
    }

    remote.dropdowns.closeForView(name);

    if (name === "model-switch") {
      remote.switchers.renderModelSwitchProviderSelect();
      remote.switchers.renderModelSwitchOptions();
      remote.switchers.updateModelSwitchConfirmState();
    }
    if (name === "loadout-switch") {
      remote.switchers.renderLoadoutSwitchProviderSelect();
      remote.switchers.renderLoadoutSwitchOptions();
      remote.switchers.updateLoadoutSwitchConfirmState();
    }
    if (name !== "disconnected") {
      elements.reconnectStatus.classList.add("hidden");
    }
  }

  remote.views = {
    show: show,
  };
})();
