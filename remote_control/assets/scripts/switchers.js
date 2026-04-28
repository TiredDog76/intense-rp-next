(function () {
  const remote = window.IRPRemote;
  const state = remote.state;
  const elements = remote.elements;
  const assets = remote.config.assets || {};
  const icons = assets.icons || {};

  function updateHomeControls() {
    const remoteState = state.remoteState || {};
    const busy = Boolean(remoteState.busy);
    const canSwitchAccount = Boolean(remoteState.can_switch_account);
    const modelSwitch = remoteState.model_switch || {};
    const loadoutSwitch = remoteState.loadout_switch || {};
    elements.stopButton.disabled = busy;
    elements.stopToggle.disabled = busy;
    elements.restartAction.disabled = busy;
    elements.switchAccountAction.disabled = busy || !canSwitchAccount;
    elements.hotswapAction.disabled = busy;
    elements.modelSwitchButton.disabled = busy || !Boolean(modelSwitch.supported);
    elements.loadoutSwitchButton.disabled = busy || !Boolean(loadoutSwitch.supported);
  }

  function renderHotswapTargets() {
    elements.hotswapGrid.innerHTML = "";
    const targets = (state.remoteState && state.remoteState.hotswap_targets) || [];
    targets.forEach((target) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "web-button web-button--accent";
      button.innerHTML =
        '<span class="web-button__icon" aria-hidden="true"><img src="' +
        remote.escapeHtml(target.icon_url) +
        '" alt=""></span><span class="web-button__label">' +
        remote.escapeHtml(target.name) +
        "</span>";
      button.addEventListener("click", function () {
        remote.api.triggerAction("hotswap", { provider: target.name }, elements.hotswapStatus);
      });
      elements.hotswapGrid.appendChild(button);
    });
  }

  function getModelSwitchState() {
    return (state.remoteState && state.remoteState.model_switch) || {};
  }

  function getModelProviders() {
    const providers = getModelSwitchState().providers || [];
    return Array.isArray(providers) ? providers : [];
  }

  function findModelProvider(providerName) {
    const normalizedName = String(providerName || "").trim();
    return (
      getModelProviders().find((provider) => provider.name === normalizedName) ||
      getModelProviders()[0] ||
      null
    );
  }

  function syncModelDrafts() {
    const modelSwitch = getModelSwitchState();
    const providers = getModelProviders();
    const nextDrafts = {};

    providers.forEach((provider) => {
      const options = Array.isArray(provider.options) ? provider.options : [];
      const currentName =
        String(provider.current_model || "").trim() ||
        (options[0] ? String(options[0].name || "").trim() : "");
      const existingDraft = String(state.draftModels[provider.name] || "").trim();
      const draftStillExists = options.some((option) => option.name === existingDraft);
      nextDrafts[provider.name] = draftStillExists ? existingDraft : currentName;
    });

    state.draftModels = nextDrafts;

    const activeProvider = state.activeModelProvider
      ? findModelProvider(state.activeModelProvider)
      : null;
    const stateProvider = modelSwitch.current_provider
      ? findModelProvider(modelSwitch.current_provider)
      : null;
    state.activeModelProvider = (
      activeProvider ||
      stateProvider ||
      providers[0] ||
      {}
    ).name || "";
  }

  function renderModelSwitchHomeState() {
    const modelSwitch = getModelSwitchState();
    const supported = Boolean(modelSwitch.supported);
    const parallel = Boolean(modelSwitch.parallel);
    const provider = findModelProvider(modelSwitch.current_provider);
    const currentModel = provider
      ? String(provider.current_model || "").trim()
      : String(modelSwitch.current_model || "").trim();

    elements.modelSwitchRow.classList.toggle("hidden", !supported);
    if (!supported) {
      elements.modelSwitchCurrentModel.textContent = "";
      elements.modelSwitchCurrentModel.classList.add("hidden");
      return;
    }

    elements.modelSwitchCurrentModel.textContent = parallel && provider
      ? "Current Model: " + provider.name + " - " + (currentModel || "Unknown")
      : "Current Model: " + (currentModel || "Unknown");
    elements.modelSwitchCurrentModel.classList.remove("hidden");
  }

  function renderModelSwitchProviderSelect() {
    const modelSwitch = getModelSwitchState();
    const providers = getModelProviders();
    const showProviderSelect = Boolean(modelSwitch.parallel) && providers.length > 1;
    const activeProvider = findModelProvider(state.activeModelProvider);

    elements.modelProviderBlock.classList.toggle("hidden", !showProviderSelect);
    elements.modelSwitchFooter.classList.toggle("is-single", !showProviderSelect);
    elements.modelSwitchConfirmButton.classList.toggle("hidden", !showProviderSelect);
    if (!showProviderSelect) {
      remote.dropdowns.modelProvider.close();
      return;
    }

    if (activeProvider) {
      elements.modelProviderButtonLabel.textContent = activeProvider.name;
      elements.modelProviderButtonIcon.src = activeProvider.icon_url || "";
      elements.modelProviderButtonIcon.classList.toggle("hidden", !activeProvider.icon_url);
    }

    elements.modelProviderMenu.innerHTML = "";
    providers.forEach((provider) => {
      const option = document.createElement("button");
      const selected = activeProvider && provider.name === activeProvider.name;
      option.type = "button";
      option.className = "custom-select__option" + (selected ? " is-selected" : "");
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", selected ? "true" : "false");
      option.innerHTML =
        '<span class="custom-select__icon" aria-hidden="true"><img src="' +
        remote.escapeHtml(provider.icon_url || "") +
        '" alt=""></span><span class="custom-select__label">' +
        remote.escapeHtml(provider.name) +
        "</span>";
      option.addEventListener("click", function () {
        state.activeModelProvider = provider.name;
        remote.dropdowns.modelProvider.close();
        renderModelSwitchProviderSelect();
        renderModelSwitchOptions();
        updateModelSwitchConfirmState();
      });
      elements.modelProviderMenu.appendChild(option);
    });
  }

  function modelDraftHasChanges() {
    return getModelProviders().some((provider) => {
      const currentName = String(provider.current_model || "").trim();
      const draftName = String(state.draftModels[provider.name] || "").trim();
      return draftName && draftName !== currentName;
    });
  }

  function updateModelSwitchConfirmState() {
    const modelSwitch = getModelSwitchState();
    const confirmVisible = Boolean(modelSwitch.parallel);
    elements.modelSwitchConfirmButton.disabled =
      !confirmVisible || !modelDraftHasChanges();
  }

  function getLoadoutSwitchState() {
    return (state.remoteState && state.remoteState.loadout_switch) || {};
  }

  function getLoadoutProviders() {
    const providers = getLoadoutSwitchState().providers || [];
    return Array.isArray(providers) ? providers : [];
  }

  function findLoadoutProvider(providerName) {
    const normalizedName = String(providerName || "").trim();
    return (
      getLoadoutProviders().find((provider) => provider.name === normalizedName) ||
      getLoadoutProviders()[0] ||
      null
    );
  }

  function syncLoadoutDrafts() {
    const loadoutSwitch = getLoadoutSwitchState();
    const providers = getLoadoutProviders();
    const nextDrafts = {};

    providers.forEach((provider) => {
      const options = Array.isArray(provider.options) ? provider.options : [];
      const currentName =
        String(provider.current_loadout || "").trim() ||
        (options[0] ? String(options[0].name || "").trim() : "");
      const existingDraft = String(state.draftLoadouts[provider.name] || "").trim();
      const draftStillExists = options.some((option) => option.name === existingDraft);
      nextDrafts[provider.name] = draftStillExists ? existingDraft : currentName;
    });

    state.draftLoadouts = nextDrafts;

    const activeProvider = state.activeLoadoutProvider
      ? findLoadoutProvider(state.activeLoadoutProvider)
      : null;
    const stateProvider = loadoutSwitch.current_provider
      ? findLoadoutProvider(loadoutSwitch.current_provider)
      : null;
    state.activeLoadoutProvider = (
      activeProvider ||
      stateProvider ||
      providers[0] ||
      {}
    ).name || "";
  }

  function renderLoadoutSwitchHomeState() {
    const loadoutSwitch = getLoadoutSwitchState();
    const supported = Boolean(loadoutSwitch.supported);
    const provider = findLoadoutProvider(loadoutSwitch.current_provider);
    const currentLoadout = provider
      ? String(provider.current_loadout || "").trim()
      : "";

    elements.loadoutSwitchRow.classList.toggle("hidden", !supported);
    if (!supported) {
      elements.loadoutSwitchCurrentLoadout.textContent = "";
      elements.loadoutSwitchCurrentLoadout.classList.add("hidden");
      return;
    }

    elements.loadoutSwitchCurrentLoadout.textContent =
      "Current Loadout: " + (currentLoadout || "Unknown");
    elements.loadoutSwitchCurrentLoadout.classList.remove("hidden");
  }

  function renderLoadoutSwitchProviderSelect() {
    const loadoutSwitch = getLoadoutSwitchState();
    const providers = getLoadoutProviders();
    const showProviderSelect = Boolean(loadoutSwitch.parallel) && providers.length > 1;
    const activeProvider = findLoadoutProvider(state.activeLoadoutProvider);

    elements.loadoutProviderBlock.classList.toggle("hidden", !showProviderSelect);
    elements.loadoutSwitchFooter.classList.toggle("is-single", !showProviderSelect);
    elements.loadoutSwitchConfirmButton.classList.toggle("hidden", !showProviderSelect);
    if (!showProviderSelect) {
      remote.dropdowns.loadoutProvider.close();
      return;
    }

    if (activeProvider) {
      elements.loadoutProviderButtonLabel.textContent = activeProvider.name;
      elements.loadoutProviderButtonIcon.src = activeProvider.icon_url || "";
      elements.loadoutProviderButtonIcon.classList.toggle("hidden", !activeProvider.icon_url);
    }

    elements.loadoutProviderMenu.innerHTML = "";
    providers.forEach((provider) => {
      const option = document.createElement("button");
      const selected = activeProvider && provider.name === activeProvider.name;
      option.type = "button";
      option.className = "custom-select__option" + (selected ? " is-selected" : "");
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", selected ? "true" : "false");
      option.innerHTML =
        '<span class="custom-select__icon" aria-hidden="true"><img src="' +
        remote.escapeHtml(provider.icon_url || "") +
        '" alt=""></span><span class="custom-select__label">' +
        remote.escapeHtml(provider.name) +
        "</span>";
      option.addEventListener("click", function () {
        state.activeLoadoutProvider = provider.name;
        remote.dropdowns.loadoutProvider.close();
        renderLoadoutSwitchProviderSelect();
        renderLoadoutSwitchOptions();
        updateLoadoutSwitchConfirmState();
      });
      elements.loadoutProviderMenu.appendChild(option);
    });
  }

  function loadoutDraftHasChanges() {
    return getLoadoutProviders().some((provider) => {
      const currentName = String(provider.current_loadout || "").trim();
      const draftName = String(state.draftLoadouts[provider.name] || "").trim();
      return draftName && draftName !== currentName;
    });
  }

  function updateLoadoutSwitchConfirmState() {
    const loadoutSwitch = getLoadoutSwitchState();
    const confirmVisible = Boolean(loadoutSwitch.parallel);
    elements.loadoutSwitchConfirmButton.disabled =
      !confirmVisible || !loadoutDraftHasChanges();
  }

  function renderLoadoutSwitchOptions() {
    elements.loadoutSwitchList.innerHTML = "";
    const loadoutSwitch = getLoadoutSwitchState();
    const activeProvider = findLoadoutProvider(state.activeLoadoutProvider);
    if (!activeProvider) {
      return;
    }

    const parallel = Boolean(loadoutSwitch.parallel);
    const currentName = String(activeProvider.current_loadout || "").trim();
    const draftName =
      String(state.draftLoadouts[activeProvider.name] || "").trim() || currentName;
    const options = Array.isArray(activeProvider.options)
      ? activeProvider.options
      : [];

    options.forEach((option) => {
      const optionName = String(option.name || "").trim();
      if (!optionName) {
        return;
      }

      const selected = optionName === draftName;
      const button = document.createElement("button");
      button.type = "button";
      button.className =
        "web-button web-button--secondary loadout-switch-list__button" +
        (selected ? " is-selected" : "");

      const stateIcon = selected
        ? '<span class="loadout-option__check" aria-hidden="true"><img src="' +
          remote.escapeHtml(icons.check) +
          '" alt=""></span>'
        : '<span class="loadout-option__check" aria-hidden="true"></span>';
      const meta = selected
        ? '<span class="loadout-option__meta">' +
          remote.escapeHtml(optionName === currentName ? "Current" : "Selected") +
          "</span>"
        : "";

      button.innerHTML =
        stateIcon +
        '<span class="loadout-option__text"><span class="loadout-option__title">' +
        remote.escapeHtml(optionName) +
        "</span>" +
        meta +
        "</span>";
      button.addEventListener("click", function () {
        handleLoadoutSwitchSelection(activeProvider.name, optionName);
      });
      elements.loadoutSwitchList.appendChild(button);
    });
  }

  function renderModelSwitchOptions() {
    elements.modelSwitchList.innerHTML = "";
    const modelSwitch = getModelSwitchState();
    const activeProvider = findModelProvider(state.activeModelProvider);
    if (!activeProvider) {
      return;
    }

    const parallel = Boolean(modelSwitch.parallel);
    const currentName = String(activeProvider.current_model || "").trim();
    const draftName =
      String(state.draftModels[activeProvider.name] || "").trim() || currentName;
    const options = Array.isArray(activeProvider.options)
      ? activeProvider.options
      : [];

    options.forEach((option) => {
      const optionName = String(option.name || "").trim();
      if (!optionName) {
        return;
      }

      const selected = optionName === draftName;
      const button = document.createElement("button");
      button.type = "button";
      button.className =
        "web-button web-button--secondary model-switch-list__button" +
        (parallel ? " model-switch-list__button--stateful" : "") +
        (selected ? " is-selected" : "");

      if (parallel) {
        const stateIcon = selected
          ? '<span class="model-option__check" aria-hidden="true"><img src="' +
            remote.escapeHtml(icons.check) +
            '" alt=""></span>'
          : '<span class="model-option__check" aria-hidden="true"></span>';
        const meta = selected
          ? '<span class="model-option__meta">' +
            remote.escapeHtml(optionName === currentName ? "Current" : "Selected") +
            "</span>"
          : "";
        button.innerHTML =
          stateIcon +
          '<span class="model-option__text"><span class="model-option__title">' +
          remote.escapeHtml(optionName) +
          "</span>" +
          meta +
          "</span>";
      } else {
        button.innerHTML =
          '<span class="web-button__label">' +
          remote.escapeHtml(optionName) +
          "</span>";
      }

      button.addEventListener("click", function () {
        handleModelSwitchSelection(activeProvider.name, optionName, button);
      });
      elements.modelSwitchList.appendChild(button);
    });
  }

  function refreshAll() {
    syncModelDrafts();
    syncLoadoutDrafts();
    updateHomeControls();
    renderHotswapTargets();
    renderModelSwitchHomeState();
    renderModelSwitchProviderSelect();
    renderModelSwitchOptions();
    updateModelSwitchConfirmState();
    renderLoadoutSwitchHomeState();
    renderLoadoutSwitchProviderSelect();
    renderLoadoutSwitchOptions();
    updateLoadoutSwitchConfirmState();
  }

  function setModelSwitchBusyState(busy) {
    const buttons = Array.from(elements.modelSwitchList.querySelectorAll("button"));
    buttons.forEach((button) => {
      button.disabled = busy;
    });
    elements.modelProviderButton.disabled = busy;
    elements.modelSwitchBackButton.disabled = busy;
    elements.modelSwitchConfirmButton.disabled =
      busy || !Boolean(getModelSwitchState().parallel) || !modelDraftHasChanges();
  }

  async function handleModelSwitchSelection(providerName, modelName, button) {
    const modelSwitch = getModelSwitchState();
    const provider = findModelProvider(providerName);
    if (!provider) {
      return;
    }

    if (Boolean(modelSwitch.parallel)) {
      state.draftModels[provider.name] = modelName;
      renderModelSwitchOptions();
      updateModelSwitchConfirmState();
      return;
    }

    const originalHtml = button.innerHTML;
    setModelSwitchBusyState(true);
    button.innerHTML = '<span class="web-button__label">Loading...</span>';

    const ok = await remote.api.triggerAction(
      "switch-model",
      { provider: provider.name, model: modelName },
      elements.modelSwitchStatus,
      { disconnect: false, successView: "home" }
    );

    if (!ok) {
      button.innerHTML = originalHtml;
      setModelSwitchBusyState(false);
    }
  }

  async function handleModelSwitchConfirm() {
    if (!modelDraftHasChanges()) {
      return;
    }

    setModelSwitchBusyState(true);
    await remote.api.triggerAction(
      "switch-model",
      { models: state.draftModels },
      elements.modelSwitchStatus,
      { disconnect: false, successView: "home" }
    );
    setModelSwitchBusyState(false);
  }

  function setLoadoutSwitchBusyState(busy) {
    const buttons = Array.from(elements.loadoutSwitchList.querySelectorAll("button"));
    buttons.forEach((button) => {
      button.disabled = busy;
    });
    elements.loadoutProviderButton.disabled = busy;
    elements.loadoutSwitchBackButton.disabled = busy;
    elements.loadoutSwitchConfirmButton.disabled =
      busy || !Boolean(getLoadoutSwitchState().parallel) || !loadoutDraftHasChanges();
  }

  async function handleLoadoutSwitchSelection(providerName, loadoutName) {
    const loadoutSwitch = getLoadoutSwitchState();
    const provider = findLoadoutProvider(providerName);
    if (!provider) {
      return;
    }

    if (Boolean(loadoutSwitch.parallel)) {
      state.draftLoadouts[provider.name] = loadoutName;
      renderLoadoutSwitchOptions();
      updateLoadoutSwitchConfirmState();
      return;
    }

    setLoadoutSwitchBusyState(true);
    await remote.api.triggerAction(
      "switch-loadout",
      { provider: provider.name, loadout: loadoutName },
      elements.loadoutSwitchStatus,
      { successView: "home" }
    );
    setLoadoutSwitchBusyState(false);
  }

  async function handleLoadoutSwitchConfirm() {
    if (!loadoutDraftHasChanges()) {
      return;
    }

    setLoadoutSwitchBusyState(true);
    await remote.api.triggerAction(
      "switch-loadout",
      { loadouts: state.draftLoadouts },
      elements.loadoutSwitchStatus,
      { successView: "home" }
    );
    setLoadoutSwitchBusyState(false);
  }

  remote.switchers = {
    refreshAll: refreshAll,
    renderModelSwitchProviderSelect: renderModelSwitchProviderSelect,
    renderModelSwitchOptions: renderModelSwitchOptions,
    updateModelSwitchConfirmState: updateModelSwitchConfirmState,
    renderLoadoutSwitchProviderSelect: renderLoadoutSwitchProviderSelect,
    renderLoadoutSwitchOptions: renderLoadoutSwitchOptions,
    updateLoadoutSwitchConfirmState: updateLoadoutSwitchConfirmState,
    handleModelSwitchConfirm: handleModelSwitchConfirm,
    handleLoadoutSwitchConfirm: handleLoadoutSwitchConfirm,
  };
})();
