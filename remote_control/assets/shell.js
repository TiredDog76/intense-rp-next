(function () {
  const remote = window.IRPRemote;
  const state = remote.state;
  const elements = remote.elements;

  function bindEvents() {
    elements.loginForm.addEventListener("submit", remote.api.handleLogin);
    elements.loginButton.addEventListener("click", remote.api.handleLogin);

    elements.viewLogsButton.addEventListener("click", function () {
      state.pendingView = "logs";
      remote.views.show("logs");
    });
    elements.stopButton.addEventListener("click", function () {
      remote.api.triggerAction("stop", {}, elements.homeStatus);
    });
    elements.stopToggle.addEventListener("click", remote.dropdowns.stop.toggle);
    elements.restartAction.addEventListener("click", function () {
      remote.api.triggerAction("restart", {}, elements.homeStatus);
    });
    elements.switchAccountAction.addEventListener("click", function () {
      remote.api.triggerAction("switch-account", {}, elements.homeStatus);
    });
    elements.hotswapAction.addEventListener("click", function () {
      remote.dropdowns.stop.close();
      remote.views.show("hotswap");
    });
    elements.modelSwitchButton.addEventListener("click", function () {
      remote.views.show("model-switch");
    });
    elements.loadoutSwitchButton.addEventListener("click", function () {
      remote.views.show("loadout-switch");
    });
    elements.hotswapBackButton.addEventListener("click", function () {
      remote.views.show("home");
    });
    elements.modelSwitchBackButton.addEventListener("click", function () {
      remote.views.show("home");
    });
    elements.modelProviderButton.addEventListener("click", remote.dropdowns.modelProvider.toggle);
    elements.modelSwitchConfirmButton.addEventListener(
      "click",
      remote.switchers.handleModelSwitchConfirm
    );
    elements.loadoutProviderButton.addEventListener(
      "click",
      remote.dropdowns.loadoutProvider.toggle
    );
    elements.loadoutSwitchBackButton.addEventListener("click", function () {
      remote.views.show("home");
    });
    elements.loadoutSwitchConfirmButton.addEventListener(
      "click",
      remote.switchers.handleLoadoutSwitchConfirm
    );
    elements.logsFooterButton.addEventListener("click", function () {
      if (state.logConnected) {
        remote.views.show("home");
      } else {
        remote.views.show("logs");
      }
    });
    elements.reconnectButton.addEventListener("click", remote.api.reconnect);
    remote.dropdowns.bindOutsideClicks();
  }

  bindEvents();
  remote.api.boot().catch(function () {
    remote.views.show("login");
  });
})();
