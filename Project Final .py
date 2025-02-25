from fifo import Fifo
from piotimer import Piotimer
import network
import socket
from machine import Pin, PWM
from time import sleep
import time
from ssd1306 import SSD1306_I2C
import math
import urequests as requests
import ujson
import micropython
micropython.alloc_emergency_exception_buf(200)


WIDTH = 128 
HEIGHT = 64 
i2c = machine.I2C(1,sda=machine.Pin(14), scl=machine.Pin(15), freq=200000)
oled = SSD1306_I2C(WIDTH, HEIGHT, i2c)

push_sw = Pin(12, Pin.IN, Pin.PULL_UP)
enc_a = Pin(10, Pin.IN, Pin.PULL_UP)
enc_b = Pin(11, Pin.IN, Pin.PULL_UP)

adc = machine.ADC(26)



pushbot_state = 0
last_pushbot_state = 0
pushbot_val = 0

def pushbot_interrupt(pin):
    global pushbot_val
    global pushbot_state
    global last_pushbot_state

    a = enc_a.value()
    b = enc_b.value()

    if a != last_pushbot_state:
        if b != a:
            pushbot_state += 1
        else:
            pushbot_state -= 1

    pushbot_val += pushbot_state
    pushbot_state = 0
    last_pushbot_state = a

enc_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=pushbot_interrupt, hard=True)

#network_name = "kmd758_Ope2"
#network_pass = "aW43fKNE7Q7NxgC"

network_name = "iPhone"
network_pass = "12345678"


APIKEY = "pbZRUi49X48I56oL1Lq8y8NDjq6rPfzX3AQeNo3a"
CLIENT_ID = "3pjgjdmamlj759te85icf0lucv"
CLIENT_SECRET = "111fqsli1eo7mejcrlffbklvftcnfl4keoadrdv1o45vt9pndlef"



class Network:
    def __init__(self, network_name, network_pass):
        self.network_name = network_name
        self.network_pass = network_pass
        self.wlan = network.WLAN(network.STA_IF)
    
    def connect(self):
        self.wlan.active(True)
        self.wlan.connect(self.network_name, self.network_pass)
        while self.wlan.isconnected() == False:
            print('Waiting for connection...')
            oled.fill(0)
            oled.text('connection...',10 ,30, 1)
            oled.show()
            sleep(1)
        return self.wlan.ifconfig()


class Kubios:
    def __init__(self, client_id, client_secret, api_key):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_key = api_key
        self.login_url = "https://kubioscloud.auth.eu-west-1.amazoncognito.com/login"
        self.token_url = "https://kubioscloud.auth.eu-west-1.amazoncognito.com/oauth2/token"
        self.redirect_uri = "https://analysis.kubioscloud.com/v1/portal/login"
    
    def get_access_token(self):
        response = requests.post(
            url=self.token_url,
            data='grant_type=client_credentials&client_id={}'.format(self.client_id),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            auth=(self.client_id, self.client_secret)
        )
        response = response.json()  
        access_token = response["access_token"]
        return access_token
    
    def analyze(self, ppi_list):
        data_set = {
            "type": "RRI",
            "data": ppi_list,
            "analysis": {
                "type": "readiness"
            }
        }
        access_token = self.get_access_token()
        response = requests.post(
            url="https://analysis.kubioscloud.com/v2/analytics/analyze",
            headers={
                "Authorization": "Bearer {}".format(access_token),
                "X-Api-Key": self.api_key
            },
            json=data_set
        )
        response = response.json()
        return response["analysis"]




class Hrt_colculetor:
    def __init__(self, lst):
        self.lst = lst
        self.lst_len = len(lst)
        self.lst_sum = sum(lst)
        self.thrash_hold = ((max(self.lst) + min(self.lst))/ 2) + ((max(self.lst) - min(self.lst))/ 10)
        local_index = []
        for i in range(len(self.lst)-1):
            if self.lst[i] < self.thrash_hold and self.lst[i+1] >= self.thrash_hold:
                local_index.append(i+1)
        self.interval_index = 0   
        for i in range(len(local_index)-1):
            self.interval_index = local_index[i+1] - local_index[i] 


    def ppi(self):
        return (self.interval_index * 4)


    def hrt(self):
        if self.ppi() > 0:
             return 60000 / self.ppi()
        else:
            return 0
        
    def mean_ppi(self):
        return (self.lst_sum / self.lst_len)

    def mean_hr(self):
        return (60000 / self.mean_ppi())
        
    def sdnn(self):
        pow_list = []
        for x in self.lst:
             pow_list.append((math.pow((x - self.mean_ppi()), 2)))
        for x in pow_list:
            return (math.sqrt(sum(pow_list) / (self.lst_len - 1)))
        
    def rmsdd(self):
        pow_list = []
        for i in range(self.lst_len - 1):
            pow_list.append((math.pow((self.lst[i + 1] - self.lst[i]), 2)))
        for x in pow_list:
            return (math.sqrt(sum(pow_list) / (self.lst_len - 1)))
    

sample = Fifo(750)
def catch(x):
    sample.put(adc.read_u16())
    
timer=Piotimer(period=4,mode=Piotimer.PERIODIC,callback=catch)



count1 = 0
count2 = 0
push_state1 = False
push_state2 = False

sample_list = []
ppi_list = []


network = Network(network_name, network_pass)
network.connect()
    
kubios = Kubios(CLIENT_ID, CLIENT_SECRET,APIKEY)
stress_index = 0
pns_index = 0
sns_index = 0
mean_ppi = 0
mean_hr = 0
sdnn = 0
rmsdd = 0

while True:
    if count1 % 2 == 0:
        cont_number_sample = 20
        ppi_list.clear()
        oled.fill(0)
        oled.text("For start", 0,0,1)
        oled.text("Hold sensor", 0,10,1)
        oled.text("On your finger", 0,20,1)
        oled.text("Then press", 0,30,1)
        oled.text("Push buttom", 0,40,1)
        oled.text("Be calm", 0,50,1)
        oled.show()
        if not push_state1 and push_sw.value() == 0:
            push_state1 = not push_state1
            count1 += 1
        if push_sw.value() == 1:
            push_state1 = not push_state1
        if count1 % 2 == 1:
            while True:
                if not sample.empty():
                    value = sample.get()
                    if len(sample_list) <= sample.size:
                        sample_list.append(value)
                    else:
                        a = Hrt_colculetor(sample_list)
                        print("Heart rate is : " ,a.hrt())
                        #print("PPI is : " ,a.ppi())
                        sample_list.clear()
                
                        oled.fill(0)
                        oled.text("Heart rate is : " ,0,0,1)
                        oled.text(f"{a.hrt()} " ,0,15,1)
                        oled.text(f"{cont_number_sample} Pulse left " ,0,30,1)
                        oled.show()
                        if len(ppi_list) < 20:
                            if 400 <= a.ppi() <= 2000:
                                cont_number_sample -= 1
                                ppi_list.append(a.ppi())
                        else:
                            oled.fill(0)
                            oled.text('In progress...',10 ,30, 1)
                            oled.show()
                            time.sleep(2)
                            basic = Hrt_colculetor(ppi_list)
                            mean_ppi = round(basic.mean_ppi())
                            mean_hr = round(basic.mean_hr())
                            sdnn = round(basic.sdnn())
                            rmsdd = round(basic.rmsdd())
                            analysis = kubios.analyze(ppi_list)
                            stress_index = analysis['stress_index']
                            pns_index = analysis['pns_index']
                            sns_index = analysis['sns_index']
                            break
            while True:
                if not push_state2 and push_sw.value() == 0:
                    push_state2 = not push_state2
                    count2 += 1
                if push_sw.value() == 1:
                    push_state2 = not push_state2
                if count2 % 2 == 0:
                    m = 0 + pushbot_val * 20
                    if m > 40 or pushbot_val > 4:
                        pushbot_val -= 1
                        m = 40
                    elif m < 0 or pushbot_val < 0:
                        pushbot_val += 1
                        m = 0
                    oled.fill(0)
                    oled.text('Basic ',0,0)
                    oled.text('Kubios ',0,20)
                    oled.text('Try again ',0,40)
                    oled.text(f"<-",90,m)
                    oled.show()
                if count2 % 2 == 1 and m == 0:
                    #basic = Hrt_colculetor(ppi_list)
                    oled.fill(0)
                    oled.text(f'mean PPI:{mean_ppi} ms',0,0,1)
                    oled.text(f'Mean HR: {mean_hr} bpm',0,15,1)
                    oled.text(f'sdnn:{sdnn} ms',0,30,1)
                    oled.text(f'rmsdd:{rmsdd} ms',0,45,1)
                    oled.show()
                if count2 % 2 == 1 and m == 20:
                    #analysis = kubios.analyze(ppi_list)
                    #stress_index = analysis['stress_index']
                    #pns_index = analysis['pns_index']
                    #sns_index = analysis['sns_index']
                    oled.fill(0)
                    oled.text('stress index:',0,0,1)
                    oled.text(f'{stress_index}',0,10,1)
                    oled.text('pns index:',0,20,1)
                    oled.text(f'{pns_index}',0,30,1)
                    oled.text('sns index:',0,40,1)
                    oled.text(f'{sns_index}',0,50,1)
                    oled.show()
                    #print("stress index is :", stress_index)
                    #print("pns index is:", pns_index)
                    #print("sns index is:", sns_index)

                    
                    
                    
                if count2 % 2 == 1 and m == 40:
                    count1 += 1
                    count2 += 1
                    break
                    
                    
                
    

