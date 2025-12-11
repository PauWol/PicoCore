from core import start

from core.comms.mesh.main import Mesh

def cbl(host, msg):
    print(f"{host}: {msg}")

mesh = Mesh()
mesh.hello()
mesh.callback(cbl)
mesh.receive(None)


start()