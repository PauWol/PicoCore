from core.bootinit import init
from core.services.servicemanager import service_manager
from core.services import led

# Initialize the systems core components
init()



service_manager.register("LED",1,led.LED,2,"custom",3,60)

service_manager.startAll()