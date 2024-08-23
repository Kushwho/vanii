import requests
import json
import hashlib
import time
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Global variables
BASE_URL = "https://api.speechsuper.com/"
APP_KEY = os.getenv("APP_KEY")  # Replace with your actual app key
SECRET_KEY = os.getenv("SECRET_KEY") # Replace with your actual secret key

def upload_file(file):    
    file_path = f"temp_{file.filename}"
    file.save(file_path)
    logging.info(f"File saved temporarily as: {file_path}")
    try:
        result = process_audio(file_path)
        logging.info("Audio processing completed successfully")
    except Exception as e:
        logging.error(f"Error processing audio: {str(e)}")
        return {'error': 'Error processing audio'}, 500
    finally:
        # Clean up the temporary file
        os.remove(file_path)
        logging.info(f"Temporary file {file_path} removed")
    
    return result

def process_audio(file_path):
    timestamp = str(int(time.time()))

    core_type = "speak.eval.pro"  # Change the coreType according to your needs.
    audio_type = "mp3"  # Change the audio type corresponding to the audio file.
    audio_sample_rate = 16000
    user_id = "guest"

    url = BASE_URL + core_type
    connect_str = (APP_KEY + timestamp + SECRET_KEY).encode("utf-8")
    connect_sig = hashlib.sha1(connect_str).hexdigest()
    start_str = (APP_KEY + timestamp + user_id + SECRET_KEY).encode("utf-8")
    start_sig = hashlib.sha1(start_str).hexdigest()

    params = {
        "connect": {
            "cmd": "connect",
            "param": {
                "sdk": {
                    "version": 16777472,
                    "source": 9,
                    "protocol": 2
                },
                "app": {
                    "applicationId": APP_KEY,
                    "sig": connect_sig,
                    "timestamp": timestamp
                }
            }
        },
        "start": {
            "cmd": "start",
            "param": {
                "app": {
                    "userId": user_id,
                    "applicationId": APP_KEY,
                    "timestamp": timestamp,
                    "sig": start_sig
                },
                "audio": {
                    "audioType": audio_type,
                    "channel": 1,
                    "sampleBytes": 2,
                    "sampleRate": audio_sample_rate
                },
                "request": {
                    "coreType": core_type,
                    "phoneme_output": 1,
                    "model":"non_native",
                    "tokenId": "tokenId"
                }
            }
        }
    }

    datas = json.dumps(params)
    data = {'text': datas}
    headers = {"Request-Index": "0"}
    files = {"audio": open(file_path, 'rb')}

    res = requests.post(url, data=data, headers=headers, files=files, timeout=60)

    if res.status_code != 200:
        print(f"Error: Received status code {res.status_code}")
        return None
    
    responseData = res.json()
    SpeechStatistics = ExtractingRequiredParameters(responseData)
    return SpeechStatistics

def ExtractingRequiredParameters(SpeechData):
    response_json = SpeechData
    # Extract the required parameters
    overall = response_json["result"]["overall"]
    pronunciation = response_json["result"]["pronunciation"]
    grammar = response_json["result"]["grammar"]
    fluency = response_json["result"]["fluency"]
    lexical_resource = response_json["result"]["vocabulary"]

    # Function to extract phonics data for a word
    def extract_phonics(word):
        phonics_data = {}
        for phonic in word["phonics"]:
            phonics_data[phonic["spell"]] = {
                "phoneme": phonic["phoneme"],
                "score": phonic["overall"]
            }
        return phonics_data

    # Extract word-level phonics for all sentences
    word_phonics = {}
    for sentence in response_json["result"]["sentences"]:
        for word in sentence["details"]:
            word_key = f"{word['word']}"
            word_phonics[word_key] = extract_phonics(word)

    combined_speech_stats = {
        "overall": overall,
        "pronunciation": pronunciation,
        "fluency": fluency,
        "grammar": grammar,
        "vocabulary": lexical_resource,
        "Phoneme Pronunciation": word_phonics
    }

    # Convert to JSON string if needed
    combined_speech_stats_json = json.dumps(combined_speech_stats, indent=4)
    
    return combined_speech_stats_json
        

