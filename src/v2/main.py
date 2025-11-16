from core import start,task , logging

@task("2s",False)
def test():
    print("2s")


@task("3s",False)
def testt():
    print("3s")
start()
