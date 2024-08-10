let isRecording = false;
let socket;
let microphone;
let audioQueue = [];
let isPlayingAudio = false;
let currentAudio = null;

const sessionId = "3"; 
const socket_port = 5001;
socket = io("http://" + window.location.hostname + ":" + socket_port.toString());

socket.on('connect', () => {
  socket.emit('session_start', { sessionId });
  socket.emit('join', {sessionId});
});

socket.on("transcription_update", (data) => {
  const { transcription, audioBinary, sessionId: responseSessionId } = data;
  console.log(responseSessionId)
  console.log("I am audio binary")
  console.log(audioBinary)
  if (responseSessionId === sessionId) {
    const captions = document.getElementById("captions");
    captions.innerHTML = transcription;
    enqueueAudio(audioBinary);
  }
});

async function getMicrophone() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    return new MediaRecorder(stream, { mimeType: "audio/webm" });
  } catch (error) {
    console.error("Error accessing microphone:", error);
    throw error;
  }
}

async function openMicrophone(microphone, socket) {
  return new Promise((resolve) => {
    microphone.onstart = () => {
      console.log("Client: Microphone opened");
      document.body.classList.add("recording");
      resolve();
    };
    microphone.ondataavailable = async (event) => {
      if (event.data.size > 0) {
        socket.emit("audio_stream", {data: event.data, sessionId});
      }
    };
    microphone.start(1000);
  });
}

async function startRecording() {
  socket.emit('join', {sessionId});
  isRecording = true;
  microphone = await getMicrophone();
  socket.on('deepgram_connection_opened' , async () => {
      console.log("Hello, How are you? I am fine.")
      await openMicrophone(microphone, socket);
  })
  
}

async function stopRecording() {
  if (isRecording) {
    clearQueue();
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }
    isPlayingAudio = false; // Reset isPlayingAudio flag
    microphone.stop();
    microphone.stream.getTracks().forEach((track) => track.stop());
    socket.emit("toggle_transcription", { action: "stop", sessionId });
    socket.emit("leave", {sessionId});
    microphone = null;
    isRecording = false;
    document.body.classList.remove("recording");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const recordButton = document.getElementById("record");

  recordButton.addEventListener("click", () => {
    if (!isRecording) {
      socket.emit("toggle_transcription", { action: "start", sessionId });
      startRecording()
        .then(() => {
          if (audioQueue.length > 0 && !isPlayingAudio) {
            playNextAudio();
          }
        })
        .catch((error) => console.error("Error starting recording:", error));
    } else {
      stopRecording().catch((error) => console.error("Error stopping recording:", error));
    }
  });
});

function enqueueAudio(audioBinary) {
  audioQueue.push(audioBinary);
  if (!isPlayingAudio) {
    playNextAudio();
  }
}

async function playNextAudio() {
  if (audioQueue.length === 0) {
    isPlayingAudio = false;
    return;
  }
  isPlayingAudio = true;
  const audioBinary = audioQueue.shift();
  await playAudio(audioBinary);
  playNextAudio();
}

async function playAudio(audioBinary) {
  try {
    if (!audioBinary) {
      throw new Error('No audio data received');
    }

    // Convert ArrayBuffer to Float32Array for PCM 32-bit float format
    const float32Array = new Float32Array(audioBinary);

    // Create an audio context
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();

    // Create an audio buffer and populate it with the PCM data
    const audioBuffer = audioContext.createBuffer(1, float32Array.length, 44100);
    audioBuffer.copyToChannel(float32Array, 0);

    // Create a buffer source, set its buffer, and connect to the audio context
    const bufferSource = audioContext.createBufferSource();
    bufferSource.buffer = audioBuffer;
    bufferSource.connect(audioContext.destination);

    // Play the audio
    bufferSource.start();
    bufferSource.onended = () => {
      audioContext.close();
    };
  } catch (error) {
    console.error("Error playing audio:", error);
  }
}


function clearQueue() {
  audioQueue = [];
}
