from core import start,task


@task("3s",False)
def test():
    print("test")


start()
