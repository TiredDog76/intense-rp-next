(function () {
  const remote = window.IRPRemote;
  const state = remote.state;
  const elements = remote.elements;

  async function validateSession() {
    if (!state.needsAuth) {
      return { reachable: true, authenticated: true };
    }
    if (!state.token) {
      return { reachable: true, authenticated: false };
    }

    try {
      const payload = await remote.requestJson(remote.apiUrl("/api/session"), {
        method: "GET",
        headers: remote.authHeaders(false),
        cache: "no-store",
      });
      if (payload && payload.token) {
        remote.setToken(payload.token);
      }
      return { reachable: true, authenticated: true };
    } catch (error) {
      if (error && error.status === 401) {
        remote.setToken("");
        return { reachable: true, authenticated: false };
      }
      return { reachable: false, authenticated: false, error: error };
    }
  }

  async function loadRemoteState() {
    state.remoteState = await remote.requestJson(remote.apiUrl("/api/state"), {
      method: "GET",
      headers: remote.authHeaders(false),
      cache: "no-store",
    });
    remote.switchers.refreshAll();
  }

  function loadRemoteStateInBackground() {
    if (state.remoteStateLoad) {
      return state.remoteStateLoad;
    }

    state.remoteStateLoad = loadRemoteState()
      .catch(function () {
        // The logs view should stay useful even if state refresh is briefly blocked.
      })
      .finally(function () {
        state.remoteStateLoad = null;
      });
    return state.remoteStateLoad;
  }

  async function completeAuthenticatedLoad(viewName) {
    let targetView = viewName || "home";
    if (targetView === "logs") {
      remote.views.show("logs");
      loadRemoteStateInBackground();
      return;
    }

    await loadRemoteState();
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
    remote.views.show(targetView);
  }

  async function boot() {
    if (!state.needsAuth) {
      await completeAuthenticatedLoad(state.pendingView === "login" ? "home" : state.pendingView);
      return;
    }

    const sessionState = await validateSession();
    if (!sessionState.reachable || !sessionState.authenticated) {
      remote.views.show("login");
      elements.loginPassword.focus();
      return;
    }

    await completeAuthenticatedLoad(state.pendingView === "login" ? "home" : state.pendingView);
  }

  async function handleLogin(event) {
    event.preventDefault();
    const password = elements.loginPassword.value || "";
    remote.setStatus(elements.loginStatus, "", false);
    elements.loginButton.disabled = true;

    try {
      const payload = await remote.requestJson(remote.apiUrl("/api/login"), {
        method: "POST",
        headers: remote.authHeaders(true),
        body: JSON.stringify({ password: password }),
        cache: "no-store",
      });
      remote.setToken(payload && payload.token ? payload.token : "");
      elements.loginPassword.value = "";
      await completeAuthenticatedLoad(state.pendingView === "login" ? "home" : state.pendingView);
    } catch (error) {
      remote.setToken("");
      remote.setStatus(
        elements.loginStatus,
        error && error.message ? error.message : "Login failed.",
        true
      );
    } finally {
      elements.loginButton.disabled = false;
    }
  }

  async function triggerAction(actionName, payload, statusElement, options) {
    const actionOptions = options || {};
    const shouldDisconnect = actionOptions.disconnect !== false;
    const successView = actionOptions.successView || "";
    remote.dropdowns.stop.close();
    remote.setStatus(statusElement, "", false);
    try {
      const response = await remote.requestJson(
        remote.apiUrl("/api/action/" + encodeURIComponent(actionName)),
        {
          method: "POST",
          headers: remote.authHeaders(true),
          body: JSON.stringify(payload || {}),
          cache: "no-store",
        }
      );
      if (response && response.remote_state) {
        state.remoteState = response.remote_state;
        remote.switchers.refreshAll();
      }
      const responseDisconnect =
        response && typeof response.disconnect === "boolean"
          ? response.disconnect
          : shouldDisconnect;
      if (responseDisconnect) {
        state.pendingView = "home";
        remote.views.show("disconnected");
      } else if (successView) {
        remote.views.show(successView);
      }
      return true;
    } catch (error) {
      remote.setStatus(
        statusElement,
        error && error.message ? error.message : "Action failed.",
        true
      );
      return false;
    }
  }

  async function reconnect() {
    elements.reconnectStatus.classList.add("hidden");
    remote.setStatus(
      elements.reconnectStatus,
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
          remote.views.show("login");
          return;
        }
      }
      await completeAuthenticatedLoad("home");
    } catch (_error) {
      elements.reconnectStatus.classList.remove("hidden");
    }
  }

  remote.api = {
    validateSession: validateSession,
    loadRemoteState: loadRemoteState,
    loadRemoteStateInBackground: loadRemoteStateInBackground,
    completeAuthenticatedLoad: completeAuthenticatedLoad,
    boot: boot,
    handleLogin: handleLogin,
    triggerAction: triggerAction,
    reconnect: reconnect,
  };
})();
