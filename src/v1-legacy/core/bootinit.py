
def init():
    from core import logger, config
    from core.constants.constants import LOG_LEVELS
    from core.config import get_config
    from core.utils.utils import sync_rtc
    from core.services.servicemanager import service_manager
    from core.services import health
    from core.services import led

    # Initialize the config
    config.config_instance = config.Config("config.toml")

    # Sync the RTC
    sync_rtc(get_config().get("system.rtc_sync_stamp"))

    # Initialize the global logger
    logger.logger_instance = logger.Log(
        LOG_LEVELS[get_config().get("system.logger.level")],
        get_config().get("system.logger.bufferSize"),
        get_config().get("system.logger.max"),
        get_config().get("system.logger.log_to_file"),
        get_config().get("system.logger.log_to_console")
    )

    # Register System services
    # ------------------------------------

    # Priority: 3
    service_manager.register("HEALTH", 3, health.SystemHealth, get_config().get("system.health.check_interval"), get_config().get("system.health.hardware_cooling"))

    # Priority: 2


    # Priority: 1
    if get_config().get("system.health.onboard_status_led"):
        service_manager.register("LED", 1, led.LED)

    # Start the Services
    service_manager.startAll()