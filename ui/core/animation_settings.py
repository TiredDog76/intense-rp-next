from PySide6.QtWidgets import QApplication


APP_DISABLE_ANIMATIONS_PROPERTY = "disable_animations"


def animations_disabled(default: bool = False) -> bool:
    app = QApplication.instance()
    if app is None:
        return bool(default)

    try:
        value = app.property(APP_DISABLE_ANIMATIONS_PROPERTY)
    except Exception:
        value = None

    if value is None:
        return bool(default)

    return bool(value)


def set_animations_disabled(disabled: bool) -> None:
    app = QApplication.instance()
    if app is None:
        return

    app.setProperty(APP_DISABLE_ANIMATIONS_PROPERTY, bool(disabled))


def sync_animations_disabled_from_config(config_manager) -> bool:
    disabled = False

    try:
        disabled = bool(
            config_manager.get_setting("application_settings", "disable_animations")
        )
    except Exception:
        disabled = False

    set_animations_disabled(disabled)
    return disabled
