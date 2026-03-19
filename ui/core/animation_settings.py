from PySide6.QtWidgets import QApplication


APP_ANIMATIONS_DISABLED_PROPERTY = "animations_disabled"
CONFIG_ENABLE_ANIMATIONS_KEY = "enable_animations"


def animations_disabled(default: bool = True) -> bool:
    app = QApplication.instance()
    if app is None:
        return bool(default)

    try:
        value = app.property(APP_ANIMATIONS_DISABLED_PROPERTY)
    except Exception:
        value = None

    if value is None:
        return bool(default)

    return bool(value)


def set_animations_disabled(disabled: bool) -> None:
    app = QApplication.instance()
    if app is None:
        return

    app.setProperty(APP_ANIMATIONS_DISABLED_PROPERTY, bool(disabled))


def sync_animations_disabled_from_config(config_manager) -> bool:
    disabled = True

    try:
        disabled = not bool(
            config_manager.get_setting(
                "application_settings", CONFIG_ENABLE_ANIMATIONS_KEY
            )
        )
    except Exception:
        disabled = True

    set_animations_disabled(disabled)
    return disabled
