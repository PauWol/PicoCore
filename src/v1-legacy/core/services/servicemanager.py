from core.utils.error import PicoOSError, ErrorCodes
from core.constants.constants import SERVICE_STOP, SERVICE_START, SERVICE_RESTART
from core.logger import get_logger

class ServiceManager:
    def __init__(self):
        """Initialize the service manager."""
        self.services = {}
        self.service_definitions = {}

    def register(self, service_name:str,service_priority:int, service_class,*args):
        """Register a new service."""
        self.service_definitions[service_name] = (service_class, args, service_priority)
        self.services[service_name] = service_class(*args)

    def start(self, service_name):
        """Start a specific service by name."""
        service = self.services.get(service_name)
        if service and hasattr(service, 'start'):
            try:
                service.start()
                get_logger().debug(SERVICE_START,f"{service_name}","servicemanager.py:22")
            except PicoOSError as e:
                ErrorCodes.handle(e)
            except Exception as e:
                get_logger().warn(SERVICE_START,str(e),"servicemanager.py:26")

    def startAll(self):
        """Start all registered services."""
        for service_name, service in self.services.items():
            self.start(service_name)

    def stop(self, service_name):
        """Stop a specific service by name."""
        service = self.services.get(service_name)
        if service and hasattr(service, 'stop'):
            try:
                service.stop()
                get_logger().debug(SERVICE_STOP, f"{service_name}","servicemanager.py:39")
            except PicoOSError as e:
                ErrorCodes.handle(e)
            except Exception as e:
                get_logger().warn(SERVICE_STOP, str(e),"servicemanager.py:43")

    def stop_exclude(self, service_names:list[str]):
        """Stop all registered services except the ones in the list."""
        for service_name, service in self.services.items():
            if service_name not in service_names:
                self.stop(service_name)

    def stopAll(self):
        """Stop all registered services."""
        for service_name, service in self.services.items():
            self.stop(service_name)

    def restart(self, service_name):
        """Restart a specific service by name."""
        self.stop(service_name)
        self.start(service_name)

    def restartAll(self):
        """Restart all registered services."""
        self.stopAll()
        self.startAll()
        get_logger().info(SERVICE_RESTART,"All services restarted","servicemanager.py:65")

    def reset(self):
        """Reset all services by reinitializing them."""
        self.stopAll()
        try:
            self.services.clear()
            for service_name, (service_class, args, _) in self.service_definitions.items():
                self.services[service_name] = service_class(*args)

            self.startAll()  # Start services after reinitialization

        except PicoOSError as e:
            ErrorCodes.handle(e)
        except Exception as e:
            get_logger().warn(SERVICE_RESTART, str(e),"servicemanager.py:80")

    def reset_exclude(self, service_names: list[str]):
        self.stop_exclude(service_names)
        try:
            temp_services = {name: self.services[name] for name in service_names if name in self.services}
            self.services.clear()

            for service_name, (service_class, args, _) in self.service_definitions.items():
                if service_name not in service_names:
                    self.services[service_name] = service_class(*args)

            self.services.update(temp_services)  # Restore excluded services
            self.startAll()
        except PicoOSError as e:
            ErrorCodes.handle(e)
        except Exception as e:
            get_logger().warn(SERVICE_RESTART, str(e),"servicemanager.py:97")

    def get_priority(self, service_name):
        return self.service_definitions[service_name][2]

    def _stop_unnecessary_services(self, priority:int):
        """Stop all services with a lower priority than the given one."""
        for service_name, service in self.services.items():
            if self.get_priority(service_name) < priority:
                self.stop(service_name)

    def mode(self,mode="normal"):
        """Set the mode of the service manager.

        Args:
            mode (str): The mode to set. Can be "low", "medium", or "normal".
        """
        if mode == "low":
            self._stop_unnecessary_services(3)
        elif mode == "medium":
            self._stop_unnecessary_services(2)
        elif mode == "normal":
            self.startAll()

    def get(self, service_name):
        """Get a specific service by name."""
        return self.services.get(service_name)

service_manager = ServiceManager()
