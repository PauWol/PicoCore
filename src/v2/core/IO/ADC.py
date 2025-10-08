from machine import ADC as HWADC , Pin

class ADC:
    def __init__(self, pin:int, vref:float=3.3,resolution:int=12,):
        self.pin = HWADC(Pin(pin))


    def raw(self):
        pass

    def 