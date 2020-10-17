import re

import pyaudio
import speech_recognition as sr

REWRITES = {}

def get_line():
    # obtain audio from the microphone
    r = sr.Recognizer()
    with sr.Microphone(1) as source:
        audio = r.listen(source)

    # recognize speech using Google Speech Recognition
    try:
        # for testing purposes, we're just using the default API key
        # to use another API key, use `r.recognize_google(audio, key="GOOGLE_SPEECH_RECOGNITION_API_KEY")`
        # instead of `r.recognize_google(audio)`
        return r.recognize_google(audio)
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print("Could not request results from Google Speech Recognition service; {0}".format(e))

def get_rewritten_line():
    line = get_line()
    if line is not None:
        line = re.sub("Six(-?[0-9]+)", "seek \\1", line)
        return " ".join([REWRITES.get(word, word) for word in line.split()])

if __name__ == '__main__':
    while True:
        line = get_line()
        if line is None:
            print("You said nothing")
        else:
            print(f"You said '{line}'")
