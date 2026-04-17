(function () {
  const remoteConfig = window.__REMOTE_CONFIG__ || {};
  const initialState = remoteConfig.initialState || {};
  const assets = remoteConfig.assets || {};
  const basePath = remoteConfig.basePath || "";
  const sessionKey = "irp-next-remote-token";

  const state = {
    needsAuth: Boolean(initialState.needs_auth),
    token: sessionStorage.getItem(sessionKey) || "",
    currentView: "",
    pendingView: initialState.initial_view || "home",
    remoteState: initialState.remote_state || null,
    activeLoadoutProvider: "",
    draftLoadouts: {},
    logController: null,
    logConnected: false,
  };

  const views = new Map(
    Array.from(document.querySelectorAll("[data-view]")).map((view) => [
      view.getAttribute("data-view"),
      view,
    ])
  );

  const loginForm = document.getElementById("login-form");
  const loginPassword = document.getElementById("login-password");
  const loginButton = document.getElementById("login-button");
  const loginStatus = document.getElementById("login-status");
  const homeStatus = document.getElementById("home-status");
  const hotswapStatus = document.getElementById("hotswap-status");
  const modelSwitchStatus = document.getElementById("model-switch-status");
  const stopToggle = document.getElementById("stop-menu-toggle");
  const stopDropdown = document.getElementById("stop-dropdown");
  const restartAction = document.getElementById("restart-action");
  const switchAccountAction = document.getElementById("switch-account-action");
  const hotswapAction = document.getElementById("hotswap-action");
  const viewLogsButton = document.getElementById("view-logs-button");
  const modelSwitchRow = document.getElementById("model-switch-row");
  const modelSwitchButton = document.getElementById("model-switch-button");
  const modelSwitchCurrentModel = document.getElementById("model-switch-current-model");
  const loadoutSwitchRow = document.getElementById("loadout-switch-row");
  const loadoutSwitchButton = document.getElementById("loadout-switch-button");
  const loadoutSwitchCurrentLoadout = document.getElementById("loadout-switch-current-loadout");
  const hotswapGrid = document.getElementById("hotswap-grid");
  const hotswapBackButton = document.getElementById("hotswap-back-button");
  const modelSwitchList = document.getElementById("model-switch-list");
  const modelSwitchBackButton = document.getElementById("model-switch-back-button");
  const loadoutProviderBlock = document.getElementById("loadout-provider-block");
  const loadoutProviderDropdown = document.getElementById("loadout-provider-dropdown");
  const loadoutProviderButton = document.getElementById("loadout-provider-button");
  const loadoutProviderButtonIcon = document.getElementById("loadout-provider-button-icon");
  const loadoutProviderButtonLabel = document.getElementById("loadout-provider-button-label");
  const loadoutProviderMenu = document.getElementById("loadout-provider-menu");
  const loadoutSwitchList = document.getElementById("loadout-switch-list");
  const loadoutSwitchFooter = document.getElementById("loadout-switch-footer");
  const loadoutSwitchBackButton = document.getElementById("loadout-switch-back-button");
  const loadoutSwitchConfirmButton = document.getElementById("loadout-switch-confirm-button");
  const loadoutSwitchStatus = document.getElementById("loadout-switch-status");
  const consoleOutput = document.getElementById("console-output");
  const consolePlaceholder = document.getElementById("console-placeholder");
  const logsStatus = document.getElementById("logs-status");
  const logsFooterButton = document.getElementById("logs-footer-button");
  const reconnectButton = document.getElementById("reconnect-button");
  const reconnectStatus = document.getElementById("reconnect-status");
  const stopButton = document.getElementById("stop-button");

  function apiUrl(path) {
    return basePath + path;
  }

  function setToken(token) {
    state.token = token || "";
    if (state.token) {
      sessionStorage.setItem(sessionKey, state.token);
    } else {
      sessionStorage.removeItem(sessionKey);
    }
  }

  function authHeaders(includeJson) {
    const headers = {};
    if (includeJson) {
      headers["Content-Type"] = "application/json";
    }
    if (state.token) {
      headers["Authorization"] = "Bearer " + state.token;
    }
    return headers;
  }

  function setStatus(element, text, isError) {
    if (!element) {
      return;
    }
    element.textContent = text || "";
    element.classList.toggle("status-text--error", Boolean(isError) && Boolean(text));
  }

  function closeStopMenu() {
    if (!stopDropdown) {
      return;
    }
    stopDropdown.classList.remove("is-open");
    stopDropdown.setAttribute("aria-hidden", "true");
  }

  function openStopMenu() {
    if (!stopDropdown) {
      return;
    }
    stopDropdown.classList.add("is-open");
    stopDropdown.setAttribute("aria-hidden", "false");
  }

  function closeLoadoutProviderDropdown() {
    if (!loadoutProviderDropdown || !loadoutProviderButton || !loadoutProviderMenu) {
      return;
    }
    loadoutProviderDropdown.classList.remove("is-open");
    loadoutProviderButton.setAttribute("aria-expanded", "false");
    loadoutProviderMenu.setAttribute("aria-hidden", "true");
  }

  function openLoadoutProviderDropdown() {
    if (!loadoutProviderDropdown || !loadoutProviderButton || !loadoutProviderMenu) {
      return;
    }
    loadoutProviderDropdown.classList.add("is-open");
    loadoutProviderButton.setAttribute("aria-expanded", "true");
    loadoutProviderMenu.setAttribute("aria-hidden", "false");
  }

  function toggleLoadoutProviderDropdown() {
    if (loadoutProviderDropdown.classList.contains("is-open")) {
      closeLoadoutProviderDropdown();
    } else {
      openLoadoutProviderDropdown();
    }
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function showView(name) {
    views.forEach((view, key) => {
      view.classList.toggle("is-active", key === name);
    });
    state.currentView = name;
    if (name === "logs") {
      startLogs();
    } else {
      stopLogs();
    }
    if (name !== "loadout-switch") {
      closeLoadoutProviderDropdown();
    }
    if (name === "loadout-switch") {
      renderLoadoutSwitchProviderSelect();
      renderLoadoutSwitchOptions();
      updateLoadoutSwitchConfirmState();
    }
    if (name !== "disconnected") {
      reconnectStatus.classList.add("hidden");
    }
  }

  function updateHomeControls() {
    const remoteState = state.remoteState || {};
    const busy = Boolean(remoteState.busy);
    const canSwitchAccount = Boolean(remoteState.can_switch_account);
    const modelSwitch = remoteState.model_switch || {};
    const loadoutSwitch = remoteState.loadout_switch || {};
    stopButton.disabled = busy;
    stopToggle.disabled = busy;
    restartAction.disabled = busy;
    switchAccountAction.disabled = busy || !canSwitchAccount;
    hotswapAction.disabled = busy;
    modelSwitchButton.disabled = busy || !Boolean(modelSwitch.supported);
    loadoutSwitchButton.disabled = busy || !Boolean(loadoutSwitch.supported);
  }

  function renderHotswapTargets() {
    hotswapGrid.innerHTML = "";
    const targets = (state.remoteState && state.remoteState.hotswap_targets) || [];
    targets.forEach((target) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "web-button web-button--accent";
      button.innerHTML =
        '<span class="web-button__icon" aria-hidden="true"><img src="' +
        escapeHtml(target.icon_url) +
        '" alt=""></span><span class="web-button__label">' +
        escapeHtml(target.name) +
        "</span>";
      button.addEventListener("click", function () {
        triggerAction("hotswap", { provider: target.name }, hotswapStatus);
      });
      hotswapGrid.appendChild(button);
    });
  }

  function renderModelSwitchHomeState() {
    const remoteState = state.remoteState || {};
    const modelSwitch = remoteState.model_switch || {};
    const supported = Boolean(modelSwitch.supported);
    const currentModel = String(modelSwitch.current_model || "").trim();

    modelSwitchRow.classList.toggle("hidden", !supported);
    if (!supported) {
      modelSwitchCurrentModel.textContent = "";
      modelSwitchCurrentModel.classList.add("hidden");
      return;
    }

    modelSwitchCurrentModel.textContent =
      "Current Model: " + (currentModel || "Unknown");
    modelSwitchCurrentModel.classList.remove("hidden");
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

    loadoutSwitchRow.classList.toggle("hidden", !supported);
    if (!supported) {
      loadoutSwitchCurrentLoadout.textContent = "";
      loadoutSwitchCurrentLoadout.classList.add("hidden");
      return;
    }

    loadoutSwitchCurrentLoadout.textContent =
      "Current Loadout: " + (currentLoadout || "Unknown");
    loadoutSwitchCurrentLoadout.classList.remove("hidden");
  }

  function renderLoadoutSwitchProviderSelect() {
    const loadoutSwitch = getLoadoutSwitchState();
    const providers = getLoadoutProviders();
    const showProviderSelect = Boolean(loadoutSwitch.parallel) && providers.length > 1;
    const activeProvider = findLoadoutProvider(state.activeLoadoutProvider);

    loadoutProviderBlock.classList.toggle("hidden", !showProviderSelect);
    loadoutSwitchFooter.classList.toggle("is-single", !showProviderSelect);
    loadoutSwitchConfirmButton.classList.toggle("hidden", !showProviderSelect);
    if (!showProviderSelect) {
      closeLoadoutProviderDropdown();
      return;
    }

    if (activeProvider) {
      loadoutProviderButtonLabel.textContent = activeProvider.name;
      loadoutProviderButtonIcon.src = activeProvider.icon_url || "";
      loadoutProviderButtonIcon.classList.toggle("hidden", !activeProvider.icon_url);
    }

    loadoutProviderMenu.innerHTML = "";
    providers.forEach((provider) => {
      const option = document.createElement("button");
      const selected = activeProvider && provider.name === activeProvider.name;
      option.type = "button";
      option.className = "custom-select__option" + (selected ? " is-selected" : "");
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", selected ? "true" : "false");
      option.innerHTML =
        '<span class="custom-select__icon" aria-hidden="true"><img src="' +
        escapeHtml(provider.icon_url || "") +
        '" alt=""></span><span class="custom-select__label">' +
        escapeHtml(provider.name) +
        "</span>";
      option.addEventListener("click", function () {
        state.activeLoadoutProvider = provider.name;
        closeLoadoutProviderDropdown();
        renderLoadoutSwitchProviderSelect();
        renderLoadoutSwitchOptions();
        updateLoadoutSwitchConfirmState();
      });
      loadoutProviderMenu.appendChild(option);
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
    loadoutSwitchConfirmButton.disabled =
      !confirmVisible || !loadoutDraftHasChanges();
  }

  function renderLoadoutSwitchOptions() {
    loadoutSwitchList.innerHTML = "";
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

      const stateIcon = parallel && selected
        ? '<span class="loadout-option__check" aria-hidden="true"><img src="' +
          escapeHtml(assets.icons.check) +
          '" alt=""></span>'
        : '<span class="loadout-option__check" aria-hidden="true"></span>';
      const meta = selected
        ? '<span class="loadout-option__meta">' +
          escapeHtml(optionName === currentName ? "Current" : "Selected") +
          "</span>"
        : "";

      button.innerHTML =
        stateIcon +
        '<span class="loadout-option__text"><span class="loadout-option__title">' +
        escapeHtml(optionName) +
        "</span>" +
        meta +
        "</span>";
      button.addEventListener("click", function () {
        handleLoadoutSwitchSelection(activeProvider.name, optionName);
      });
      loadoutSwitchList.appendChild(button);
    });
  }

  function renderModelSwitchOptions() {
    modelSwitchList.innerHTML = "";
    const modelSwitch = (state.remoteState && state.remoteState.model_switch) || {};
    const options = modelSwitch.options || [];
    options.forEach((option) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "web-button web-button--secondary model-switch-list__button";
      button.innerHTML =
        '<span class="web-button__label">' +
        escapeHtml(option.name) +
        "</span>";
      button.addEventListener("click", function () {
        handleModelSwitchSelection(button, option.name);
      });
      modelSwitchList.appendChild(button);
    });
  }

  async function requestJson(url, options) {
    const response = await fetch(url, options || {});
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }

    if (!response.ok) {
      const message = payload && payload.detail ? payload.detail : "Request failed";
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  async function validateSession() {
    if (!state.needsAuth) {
      return { reachable: true, authenticated: true };
    }
    if (!state.token) {
      return { reachable: true, authenticated: false };
    }

    try {
      const payload = await requestJson(apiUrl("/api/session"), {
        method: "GET",
        headers: authHeaders(false),
        cache: "no-store",
      });
      if (payload && payload.token) {
        setToken(payload.token);
      }
      return { reachable: true, authenticated: true };
    } catch (error) {
      if (error && error.status === 401) {
        setToken("");
        return { reachable: true, authenticated: false };
      }
      return { reachable: false, authenticated: false, error: error };
    }
  }

  async function loadRemoteState() {
    state.remoteState = await requestJson(apiUrl("/api/state"), {
      method: "GET",
      headers: authHeaders(false),
      cache: "no-store",
    });
    syncLoadoutDrafts();
    updateHomeControls();
    renderHotswapTargets();
    renderModelSwitchHomeState();
    renderModelSwitchOptions();
    renderLoadoutSwitchHomeState();
    renderLoadoutSwitchProviderSelect();
    renderLoadoutSwitchOptions();
    updateLoadoutSwitchConfirmState();
  }

  async function completeAuthenticatedLoad(viewName) {
    await loadRemoteState();
    let targetView = viewName || "home";
    const remoteState = state.remoteState || {};
    const modelSwitch = remoteState.model_switch || {};
    const loadoutSwitch = remoteState.loadout_switch || {};
    if (
      targetView === "model-switch" &&
      !Boolean(modelSwitch.supported) &&
      Boolean(loadoutSwitch.supported)
    ) {
      targetView = "loadout-switch";
    }
    showView(targetView);
  }

  async function boot() {
    if (!state.needsAuth) {
      await completeAuthenticatedLoad(state.pendingView === "login" ? "home" : state.pendingView);
      return;
    }

    const sessionState = await validateSession();
    if (!sessionState.reachable || !sessionState.authenticated) {
      showView("login");
      loginPassword.focus();
      return;
    }

    await completeAuthenticatedLoad(state.pendingView === "login" ? "home" : state.pendingView);
  }

  async function handleLogin(event) {
    event.preventDefault();
    const password = loginPassword.value || "";
    setStatus(loginStatus, "", false);
    loginButton.disabled = true;

    try {
      const payload = await requestJson(apiUrl("/api/login"), {
        method: "POST",
        headers: authHeaders(true),
        body: JSON.stringify({ password: password }),
        cache: "no-store",
      });
      setToken(payload && payload.token ? payload.token : "");
      loginPassword.value = "";
      await completeAuthenticatedLoad(state.pendingView === "login" ? "home" : state.pendingView);
    } catch (error) {
      setToken("");
      setStatus(loginStatus, error && error.message ? error.message : "Login failed.", true);
    } finally {
      loginButton.disabled = false;
    }
  }

  async function triggerAction(actionName, payload, statusElement, options) {
    const actionOptions = options || {};
    const shouldDisconnect = actionOptions.disconnect !== false;
    const successView = actionOptions.successView || "";
    closeStopMenu();
    setStatus(statusElement, "", false);
    try {
      const response = await requestJson(apiUrl("/api/action/" + encodeURIComponent(actionName)), {
        method: "POST",
        headers: authHeaders(true),
        body: JSON.stringify(payload || {}),
        cache: "no-store",
      });
      if (response && response.remote_state) {
        state.remoteState = response.remote_state;
        syncLoadoutDrafts();
        updateHomeControls();
        renderHotswapTargets();
        renderModelSwitchHomeState();
        renderModelSwitchOptions();
        renderLoadoutSwitchHomeState();
        renderLoadoutSwitchProviderSelect();
        renderLoadoutSwitchOptions();
        updateLoadoutSwitchConfirmState();
      }
      const responseDisconnect =
        response && typeof response.disconnect === "boolean"
          ? response.disconnect
          : shouldDisconnect;
      if (responseDisconnect) {
        state.pendingView = "home";
        showView("disconnected");
      } else if (successView) {
        showView(successView);
      }
      return true;
    } catch (error) {
      setStatus(
        statusElement,
        error && error.message ? error.message : "Action failed.",
        true
      );
      return false;
    }
  }

  function setModelSwitchBusyState(busy) {
    const buttons = Array.from(modelSwitchList.querySelectorAll("button"));
    buttons.forEach((button) => {
      button.disabled = busy;
    });
    modelSwitchBackButton.disabled = busy;
  }

  async function handleModelSwitchSelection(button, modelName) {
    const originalHtml = button.innerHTML;
    setModelSwitchBusyState(true);
    button.innerHTML = '<span class="web-button__label">Loading...</span>';

    const ok = await triggerAction(
      "switch-model",
      { model: modelName },
      modelSwitchStatus,
      { disconnect: false, successView: "home" }
    );

    if (!ok) {
      button.innerHTML = originalHtml;
      setModelSwitchBusyState(false);
    }
  }

  function setLoadoutSwitchBusyState(busy) {
    const buttons = Array.from(loadoutSwitchList.querySelectorAll("button"));
    buttons.forEach((button) => {
      button.disabled = busy;
    });
    loadoutProviderButton.disabled = busy;
    loadoutSwitchBackButton.disabled = busy;
    loadoutSwitchConfirmButton.disabled =
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
    await triggerAction(
      "switch-loadout",
      { provider: provider.name, loadout: loadoutName },
      loadoutSwitchStatus,
      { successView: "home" }
    );
    setLoadoutSwitchBusyState(false);
  }

  async function handleLoadoutSwitchConfirm() {
    if (!loadoutDraftHasChanges()) {
      return;
    }

    setLoadoutSwitchBusyState(true);
    await triggerAction(
      "switch-loadout",
      { loadouts: state.draftLoadouts },
      loadoutSwitchStatus,
      { successView: "home" }
    );
    setLoadoutSwitchBusyState(false);
  }

  function clearConsolePlaceholder() {
    if (consolePlaceholder) {
      consolePlaceholder.remove();
    }
  }

  function appendLog(entry) {
    clearConsolePlaceholder();
    const line = document.createElement("div");
    line.className = "log-line log-line--" + escapeHtml(entry.level || "INFO");
    line.textContent = entry.message || "";
    consoleOutput.appendChild(line);
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
  }

  function setLogsConnected(connected, message) {
    state.logConnected = Boolean(connected);
    if (state.logConnected) {
      logsFooterButton.innerHTML = '<span class="web-button__label">Back</span>';
      setStatus(logsStatus, "", false);
    } else {
      logsFooterButton.innerHTML =
        '<span class="web-button__icon" aria-hidden="true"><img src="' +
        escapeHtml(assets.icons.chevron_right) +
        '" alt=""></span><span class="web-button__label">Reconnect</span>';
      setStatus(logsStatus, message || "Connection to logs was lost.", true);
    }
  }

  function stopLogs() {
    if (state.logController) {
      state.logController.abort();
      state.logController = null;
    }
    state.logConnected = false;
  }

  async function startLogs() {
    stopLogs();
    setLogsConnected(true, "");

    const controller = new AbortController();
    state.logController = controller;

    try {
      const response = await fetch(apiUrl("/api/logs/stream"), {
        method: "GET",
        headers: authHeaders(false),
        cache: "no-store",
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error("Unable to connect to the logs stream.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const result = await reader.read();
        if (result.done) {
          throw new Error("The logs stream closed.");
        }

        buffer += decoder.decode(result.value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";

        blocks.forEach((block) => {
          if (!block || block.startsWith(":")) {
            return;
          }
          const lines = block.split("\n");
          let eventName = "message";
          let dataText = "";
          lines.forEach((line) => {
            if (line.startsWith("event:")) {
              eventName = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              dataText += line.slice(5).trim();
            }
          });
          if (eventName !== "log" || !dataText) {
            return;
          }
          try {
            const entry = JSON.parse(dataText);
            appendLog(entry);
          } catch (_error) {
            // Ignore malformed log events
          }
        });
      }
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      setLogsConnected(false, error && error.message ? error.message : "Connection to logs was lost.");
    } finally {
      if (state.logController === controller) {
        state.logController = null;
      }
    }
  }

  async function reconnect() {
    reconnectStatus.classList.add("hidden");
    setStatus(
      reconnectStatus,
      "Failed to reconnect. Start the server up, check the connection, and try again.",
      true
    );
    try {
      if (state.needsAuth) {
        const sessionState = await validateSession();
        if (!sessionState.reachable) {
          throw sessionState.error || new Error("Unable to reach the server.");
        }
        if (!sessionState.authenticated) {
          state.pendingView = "home";
          showView("login");
          return;
        }
      }
      await completeAuthenticatedLoad("home");
    } catch (_error) {
      reconnectStatus.classList.remove("hidden");
    }
  }

  loginForm.addEventListener("submit", handleLogin);
  loginButton.addEventListener("click", handleLogin);
  viewLogsButton.addEventListener("click", function () {
    state.pendingView = "logs";
    showView("logs");
  });
  stopButton.addEventListener("click", function () {
    triggerAction("stop", {}, homeStatus);
  });
  stopToggle.addEventListener("click", function () {
    if (stopDropdown.classList.contains("is-open")) {
      closeStopMenu();
    } else {
      openStopMenu();
    }
  });
  restartAction.addEventListener("click", function () {
    triggerAction("restart", {}, homeStatus);
  });
  switchAccountAction.addEventListener("click", function () {
    triggerAction("switch-account", {}, homeStatus);
  });
  hotswapAction.addEventListener("click", function () {
    closeStopMenu();
    showView("hotswap");
  });
  modelSwitchButton.addEventListener("click", function () {
    showView("model-switch");
  });
  loadoutSwitchButton.addEventListener("click", function () {
    showView("loadout-switch");
  });
  hotswapBackButton.addEventListener("click", function () {
    showView("home");
  });
  modelSwitchBackButton.addEventListener("click", function () {
    showView("home");
  });
  loadoutProviderButton.addEventListener("click", toggleLoadoutProviderDropdown);
  loadoutSwitchBackButton.addEventListener("click", function () {
    showView("home");
  });
  loadoutSwitchConfirmButton.addEventListener("click", handleLoadoutSwitchConfirm);
  logsFooterButton.addEventListener("click", function () {
    if (state.logConnected) {
      showView("home");
    } else {
      showView("logs");
    }
  });
  reconnectButton.addEventListener("click", reconnect);

  document.addEventListener("click", function (event) {
    if (!stopDropdown || !stopToggle) {
      return;
    }
    const target = event.target;
    if (!target) {
      return;
    }
    if (stopDropdown.contains(target) || stopToggle.contains(target)) {
      return;
    }
    closeStopMenu();
  });

  document.addEventListener("click", function (event) {
    if (!loadoutProviderDropdown || !loadoutProviderButton) {
      return;
    }
    const target = event.target;
    if (!target) {
      return;
    }
    if (loadoutProviderDropdown.contains(target)) {
      return;
    }
    closeLoadoutProviderDropdown();
  });

  boot().catch(function () {
    showView("login");
  });
})();
