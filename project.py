#-*-coding:utf-8 -*-

import pygame
import RPi.GPIO as GPIO
import re
import kbhit as KB
import time
import os
import drivers
from threading import Thread

from firebase_admin import storage
import firebase_admin
from firebase_admin import messaging
from firebase_admin import credentials
from firebase_admin import firestore
from uuid import uuid4

import spidev

# pin number
lck = 12
dr = 20
uvc = 19
btn = 21

# GPIO 초기화
GPIO.setwarnings(False)

GPIO.setmode(GPIO.BCM)
GPIO.setup(lck,GPIO.OUT)
GPIO.setup(dr,GPIO.IN)
GPIO.setup(uvc,GPIO.OUT)
GPIO.setup(btn,GPIO.IN)

display=drivers.Lcd()
display.lcd_backlight(0)

# 파이어베이스 초기화
PROJECT_ID="big-box-2e5bb"
cred = credentials.Certificate("big-box-key.json")


firebase_admin.initialize_app(cred,{'storageBucket': f"{PROJECT_ID}.appspot.com"})
db = firestore.client()
bucket = storage.bucket()
box_name='box001'
barcode_ref = db.collection(box_name)


# 진동 감지 센서 초기화
spi=spidev.SpiDev()
spi.open(0,0)
spi.max_speed_hz=1000000

#sound
pygame.init()


# 진동감지센서 입력(아날로그 값 입력)
def read_spi_adc(adcChannel):
	adcValue=0
	buff=spi.xfer2([1,(8+adcChannel)<<4,0])
	adcValue=((buff[1]&3)<<8)+buff[2]
	return adcValue

# 스레드 1번에서 입력 받은 바코드 확인 과정
def coderight(code):
    global sound
    
    docs = barcode_ref.stream()
    m=0

    for doc in docs: 
        #print(doc.id, doc.to_dict())
    
        
        a=doc.to_dict()
       # print(a.items())
        
        if 'code' in a:
            if (a['code']==""):
                continue
            
            
            if (a['code']==code):
                
                print(doc.id)
                
                if (a['valid']==True):
                   # doc.update({u'valid' : False})
                    db.collection(box_name).document(doc.id).update({
                        u'valid':False
                        
                    })
                    
            
                        
                        
                    uploadLog("문이 열립니다.",doc.id,code)
                    sendCloudMessage("택배 도착", "%s 택배가 도착 했습니다 " %doc.id)
                    return True
                
                else:
                    
                    m=1
                    print("이미 입력된 바코드 입니다.")
                    break
                    
            else:
                
                print("abc")
    
    if (m==1):
        sound=4
        
    else:
        sound=2
    return False
    


door = 0 # 0 : 닫힙,  1 : 열림
lock = 0 # 0 : 잠김 , 1 : 해제


# 택배함의 로그 기록 업로드
def uploadLog(msg, info,code):
	global barcode_ref
	currentTime = time.localtime()
	timeStampString = '%04d%02d%02d%02d%02d%02d' % (currentTime.tm_year, currentTime.tm_mon, currentTime.tm_mday, currentTime.tm_hour, currentTime.tm_min, currentTime.tm_sec)
	barcode_ref.document(u'Log').update( {f'{timeStampString}': {
	u'Code': f'{code}',
	u'Date': f'{timeStampString}',
	u'Event': f'{msg}',
	u'Info': f'{info}'}})


# 어플리케이션 알림 전송 
def sendCloudMessage(title, msg):
	global barcode_ref, box_name
	registration_token = barcode_ref.document("UserAccount").get({u'Token'}).to_dict()['Token']
	message = messaging.Message(
		data={"title" : f'{title}', "message" : f'{msg}', "box": f'{box_name}'},
  		token=registration_token)
	response = messaging.send(message)
	print('successfully sent message:' , response)

# 블루투스 소리 설정 (스레드 4번)
def Sound():
    global sound
    
    while True:
        if sound>0: 
                        
            pygame.mixer.init()
            pygame.mixer.music.set_volume(1)
            
            if(sound==1):
                pygame.mixer.music.load("sound/open.mp3")
                
            elif(sound==2):
                pygame.mixer.music.load("sound/invalid.mp3")
                
            elif(sound==3):
                pygame.mixer.music.load("sound/close.mp3")
                
            elif(sound==4):
                pygame.mixer.music.load("sound/false.mp3")
                
            elif(sound==5):
                pygame.mixer.music.load("sound/notclosed.mp3")
            
            time.sleep(0.5)
            pygame.mixer.music.play()
            
            sound=0
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        else:
            time.sleep(0.1)
    
# 카메라 사진 캡쳐, 업로드 (스레드 2번)
def capture():
    global cam
    
    while True:

        if(cam>0):
            cam=cam-1
            now=time.localtime()
            filename = '%02d%02d%02d' % ((now.tm_year%100),now.tm_mon,now.tm_mday)
            filename = filename + '_'
            filename = filename + '%02d%02d%02d.jpg' % (now.tm_hour,now.tm_min,now.tm_sec) 


            capt="libcamera-still -t 10000 --width 1920 --height 1080 -n -o ./picture/" + filename
            print(capt)


            os.system(capt)
            fileUpload(filename)
            
            capt="rm ./picture/" + filename
            print(capt)
            os.system(capt)

            
        else:
            
            time.sleep(5)

# 사진 업로드
def fileUpload(file):
 
    blob = bucket.blob('picture/'+file)
    new_token = uuid4()
    metadata = {"firebaseStorageDownloadTokens":new_token}
    blob.meta = metadata
    blob.upload_from_filename(filename='./picture/'+file, content_type='image/jpeg')


# LCD 값 출력 (스레드 3번)
# main 함수로 부터 lcd_time, lcd 출력 내용을 받아서 사용

def printlcd():
    global lcd_time,lcd_prev
    global lcdword1,lcdword2
    
    
    while True:
         while (lcd_time!=0):
            
            display.lcd_backlight(1)
            display.lcd_display_string(lcdword1,1)
            display.lcd_display_string(lcdword2,2)
                
            if (now>lcd_time+lcd_prev):
                lcd_time=0
                display.lcd_clear()
                lcdword1='               '
                lcdword2='               '
                display.lcd_backlight(0)
                
                
         else:
             time.sleep(0.1)
             
            # display.lcd_clear()
             display.lcd_backlight(0)
             
             
            


# 진동감지센서 (스레드 5번)
# 직전 값과 10초 동안 20 이상 차이나는 값을 10번 이상 발견 시 로그, 앱 알림
def vibe(): 
    adcChannel=0
    adcValue=read_spi_adc(adcChannel)
    vibenum=0
    prev=time.time()

    
    while True:
        
        newValue=read_spi_adc(adcChannel)
        vibegap=newValue-adcValue
      #  print(vibegap)
        
        if (abs(vibegap)>20):
            if(vibenum==0):
                prev=time.time()
                print("vibe start")
                
            vibenum+=1
            print("vibenum ", vibenum)
            
        if(vibenum>10):
            print("vibe jindong")
            uploadLog("진동 감지", "비정상적인 진동을 감지하였습니다","")
            sendCloudMessage("진동 감지", "비정상적인 진동을 감지하였습니다")
            vibenum=0
            
        new=time.time()
        timegap=new-prev
                    
        
        print("%d" %vibegap )
        
        if(vibenum>0 and timegap>10): 
            vibenum=0
            print("reset")
            
        adcValue=newValue
        print("%d" %adcValue)
        time.sleep(0.1)
    
    
# 바코드 스캔 (스레드 1번)
def barcode_scan(): 
    global code
    global barcodeinput
    kb = KB.KBHit()

    print('Hit any key, or ESC to exit')

    ifinput=0
    code1=''

    
    while True:
        now=time.time()
        if(door==0):
        
            if kb.kbhit():
                pref=time.time()     
                code1=code1+kb.getch()
                ifinput=1

                    
            if (ifinput == 1):
                if (now-pref>0.2):
                    print(code1)
                    
                    code=re.sub(r'[^0-9A-Za-z]','',code1)

                    code1=''         
                    ifinput=0
                    barcodeinput=1
       
                
                    

    kb.set_normal_term()







# 메인
if __name__ == "__main__":
    
    # 스레드와 연동하여 사용하는 값
    
    barcodeinput=0
    cam=0
    uvc_prev=0
    uvc_time=0
    wrongcode=0
    
    btnerror=0
    btnvalid=True
    
    lcd_prev=0
    lcd_time=0
    lcdword1='               '
    lcdword2='               '
    
    open_prev=time.time()
    
    appopen = False
    

    
    sound = 0
    ERbut = 0
    
    code=''
    
    # 스레드 등록
    proc  = Thread(target=barcode_scan,args=())
    proc2 = Thread(target=capture,args=())
    proc3 = Thread(target=printlcd,args=())
    proc4 = Thread(target=Sound,args=())
    proc5 = Thread(target=vibe,args=())
    
    # 스레드 시작
    proc.start()
    proc2.start()
    proc3.start()
    proc4.start()
    proc5.start()
    
    
    
    while True:
        
    
        try:
            
            now=time.time()
            
                                           
            # uv lamp
            if (uvc_time!=0):
                
                if (now>uvc_prev+3):
                    GPIO.output(uvc,GPIO.HIGH)
                
                if (now>uvc_time+uvc_prev+3):
                    
                    uvc_time = 0
                    GPIO.output(uvc,GPIO.LOW)
            

                     
            # 문이 잠겨있을 때
            if (door == 0):
              #  print("1")
              
                #button 입력                
                if (0==1):
                                                            
                    lcd_time=99999999
                    lcd_prev=time.time()
                    m=0
                    
                    while (GPIO.input(btn)==GPIO.LOW):
                        now=time.time()
                        
                    
                        m=int((now-lcd_prev)/1.8+1)
                        
                       # print(m)
                        
                    #    print(now-lcd_prev)
                        lcdword1='%d              ' %m
                        lcdword2='button         '
                        
                        
                    num=barcode_ref.document(u'App').get().to_dict()['button']                                          
                                               
                    
                    print(m)
                    lcdword1= '               '
                    
                    # 1회용 버튼 암호 맞으면 문 열림
                    if (m==num or m==num+1):
 
                        
                        GPIO.output(uvc,GPIO.LOW)
                        uvc_time=0
                        
                        lcdword1= "Button         "
                            
                        lcdword2= "open           "
                        
                        
                        
                        GPIO.output(lck,GPIO.HIGH)
                        door = 1
                        prev = time.time()+25
                        wrongcode=0
                        sound=1
                        
                        btnerror = 0
                        btnvalid = False
                        sendCloudMessage("버튼 개방", "버튼 암호로 문이 열렸습니다")
                        db.collection(box_name).document(u'App').update({
                        u'buttonvalid':False
                    })
                        
                    # 버튼 입력시, 앱 알림으로 사용자 호출 가능    
                    else:
                        btnerror+=1
                        lcdword2='App notice     '
                        sendCloudMessage("버튼 호출", "버튼 호출이 일어났습니다")
                        
                        if (btnerror>2): # 3회 이상 호출시 버튼 비활성화
                            lcdword2='cant use button' 
                            btnvalid = False
                   
                    lcd_prev=time.time()
                    lcd_time=2
                    
                    
                    
                # 문이 열리지 않았을 때, 열림
                if (GPIO.input(dr)):
                    door=1
                    sound=5
                    GPIO.output(lck,GPIO.HIGH)
                    GPIO.output(uvc,GPIO.LOW)
                    uvc_time=0
                    
                    prev=time.time()
                    uploadLog("비정상적인 열림", "문이 제대로 닫히지 않았거나 비정상적인 잠금  해제가 일어났습니다","")
                    #cam+=1
                    
                    continue
                
                # 20초 마다 원격 열림과 버튼이 허용되는지 확인
                if (now-open_prev>20):
                    appremote=barcode_ref.document(u'App').get().to_dict()
                    appopen=appremote['open']
                    btnvalid=appremote['buttonvalid']
                    open_prev = time.time()
                    print("app open check")
                
                
                if (barcodeinput==1 or appopen == True):
                    
                    barcodeinput=0
            
                    lcdword1=code                    
                    
                    print()
                    print("input =",code)
                    print()
                    
                    # 바코드가 맞거나, 원격 오픈의 경우 문 정상 열림
                    if(coderight(code) or appopen == True):
                        
                        GPIO.output(uvc,GPIO.LOW)
                        uvc_time=0
                        if(appopen==True):
                            lcdword1= "App remote     "
                            
                        appopen=False
                        lcdword2="open           "
                                                
                        GPIO.output(lck,GPIO.HIGH)
                        door = 1
                        prev = time.time() + 25
                        wrongcode=0
                        sound=1
                        
                        
                       
                    # 잘못된 바코드 ( 등록되지 않은 바코드, 이미 사용된 바코드) 
                    else:
                        wrongcode+=1
                        lcdword2="invalid barcode%d" %wrongcode
                        
                        if(wrongcode>=3): # 3회 이상 바코드 실수시 입력 일어남
                            uploadLog("유효하지 않은 바코드", "유효하지 않은 바코드가 3회 이상 인식되었습니다.",code)
                            sendCloudMessage("인증 3회 이상 실패", "유효하지 않은 바코드가 3회 이상 인식되었습니다.")
                        
                    lcd_prev=time.time()
                    lcd_time=3
                    
                        
                    code=''
                    
            
            # 문이 열려있을 때
            if (door == 1):
             

                if (GPIO.input(dr)):
                    prev=time.time()
                    GPIO.output(lck,GPIO.HIGH)
                    
                    
                else:
                    print(now-prev)

                               
                
                # 문이 닫히고 2초 뒤 잠김
                if (now-prev>2 ):
                    GPIO.output(lck,GPIO.LOW)
                    
                    lcdword1="               "
                    lcdword2="close          "

                    
                    
                    lcd_time=3
                    lcd_prev=time.time()
                    uploadLog("문이 닫힙니다","-","-")
                    
                   
                    door = 0
                    cam += 1
                    
                    # 저장된 UV 시간만큼 UV램프 사용 시간 설정 
                    x=barcode_ref.document(u'App').get() 
                    print(x.to_dict()) 
                    uvc_time=x.to_dict()['UV_TIME']
                    print("uv time = ",x.to_dict()['UV_TIME'])
                    uvc_prev=time.time()
                    sound=3
                    db.collection(box_name).document(u'App').update({
                        u'open':False
                    })
                    
        
            time.sleep(0.03)

        # ctrl + C
        except KeyboardInterrupt: 

            print("Cleaning up!")
            
            display.lcd_clear()
            display.lcd_backlight(0)
            GPIO.output(lck,GPIO.LOW)
            GPIO.output(uvc,GPIO.LOW)
            GPIO.cleanup()
            spi.close()
