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
    activeModelProvider: "",
    draftModels: {},
    activeLoadoutProvider: "",
    draftLoadouts: {},
    logController: null,
    logConnected: false,
    logLastId: 0,
    remoteStateLoad: null,
  };

  const elements = {
    views: new Map(
      Array.from(document.querySelectorAll("[data-view]")).map((view) => [
        view.getAttribute("data-view"),
        view,
      ])
    ),
    loginForm: document.getElementById("login-form"),
    loginPassword: document.getElementById("login-password"),
    loginButton: document.getElementById("login-button"),
    loginStatus: document.getElementById("login-status"),
    homeStatus: document.getElementById("home-status"),
    hotswapStatus: document.getElementById("hotswap-status"),
    modelSwitchStatus: document.getElementById("model-switch-status"),
    stopToggle: document.getElementById("stop-menu-toggle"),
    stopDropdown: document.getElementById("stop-dropdown"),
    restartAction: document.getElementById("restart-action"),
    switchAccountAction: document.getElementById("switch-account-action"),
    hotswapAction: document.getElementById("hotswap-action"),
    viewLogsButton: document.getElementById("view-logs-button"),
    modelSwitchRow: document.getElementById("model-switch-row"),
    modelSwitchButton: document.getElementById("model-switch-button"),
    modelSwitchCurrentModel: document.getElementById("model-switch-current-model"),
    loadoutSwitchRow: document.getElementById("loadout-switch-row"),
    loadoutSwitchButton: document.getElementById("loadout-switch-button"),
    loadoutSwitchCurrentLoadout: document.getElementById("loadout-switch-current-loadout"),
    hotswapGrid: document.getElementById("hotswap-grid"),
    hotswapBackButton: document.getElementById("hotswap-back-button"),
    modelSwitchList: document.getElementById("model-switch-list"),
    modelSwitchBackButton: document.getElementById("model-switch-back-button"),
    modelProviderBlock: document.getElementById("model-provider-block"),
    modelProviderDropdown: document.getElementById("model-provider-dropdown"),
    modelProviderButton: document.getElementById("model-provider-button"),
    modelProviderButtonIcon: document.getElementById("model-provider-button-icon"),
    modelProviderButtonLabel: document.getElementById("model-provider-button-label"),
    modelProviderMenu: document.getElementById("model-provider-menu"),
    modelSwitchFooter: document.getElementById("model-switch-footer"),
    modelSwitchConfirmButton: document.getElementById("model-switch-confirm-button"),
    loadoutProviderBlock: document.getElementById("loadout-provider-block"),
    loadoutProviderDropdown: document.getElementById("loadout-provider-dropdown"),
    loadoutProviderButton: document.getElementById("loadout-provider-button"),
    loadoutProviderButtonIcon: document.getElementById("loadout-provider-button-icon"),
    loadoutProviderButtonLabel: document.getElementById("loadout-provider-button-label"),
    loadoutProviderMenu: document.getElementById("loadout-provider-menu"),
    loadoutSwitchList: document.getElementById("loadout-switch-list"),
    loadoutSwitchFooter: document.getElementById("loadout-switch-footer"),
    loadoutSwitchBackButton: document.getElementById("loadout-switch-back-button"),
    loadoutSwitchConfirmButton: document.getElementById("loadout-switch-confirm-button"),
    loadoutSwitchStatus: document.getElementById("loadout-switch-status"),
    consoleOutput: document.getElementById("console-output"),
    logsStatus: document.getElementById("logs-status"),
    logsFooterButton: document.getElementById("logs-footer-button"),
    reconnectButton: document.getElementById("reconnect-button"),
    reconnectStatus: document.getElementById("reconnect-status"),
    stopButton: document.getElementById("stop-button"),
  };

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

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
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

  window.IRPRemote = {
    config: {
      remoteConfig: remoteConfig,
      initialState: initialState,
      assets: assets,
      basePath: basePath,
      sessionKey: sessionKey,
    },
    state: state,
    elements: elements,
    apiUrl: apiUrl,
    setToken: setToken,
    authHeaders: authHeaders,
    setStatus: setStatus,
    escapeHtml: escapeHtml,
    requestJson: requestJson,
  };
})();
