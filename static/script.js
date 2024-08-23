let isRecording = false;
let socket;
let microphone;
let audioQueue = [];
let isPlayingAudio = false;
let currentAudio = null;

const sessionId = "1";
const socket_port = 5001;
socket = io("ws://localhost:5001");

socket.on('connect', () => {
  socket.emit('session_start', { sessionId });
  socket.emit('join', {sessionId});
});

socket.on("transcription_update", (data) => {
  const { transcription, audioBinary, sessionId: responseSessionId } = data;
  console.log(responseSessionId)
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
        console.log("I am sending data")
        socket.emit("audio_stream", {data: event.data, sessionId});
      }
    };
    microphone.start(1000);
  });
}

async function startRecording() {
  // socket.emit('join', {sessionId,voice:"Deepgram",email : "aswanib133@gmail.com"});
  isRecording = true;
  microphone = await getMicrophone();
  socket.on('deepgram_connection_opened' , async () => {
    console.log("Hello, Deepgram connections is open.")
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
    // socket.emit("leave", {sessionId});
    microphone = null;
    isRecording = false;
    document.body.classList.remove("recording");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const recordButton = document.getElementById("record");

  recordButton.addEventListener("click", () => {
    if (!isRecording) {
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
    const audioBlob = new Blob([audioBinary], { type: 'audio/mp3' });
    const audioUrl = URL.createObjectURL(audioBlob);
    currentAudio = new Audio(audioUrl);

    return new Promise((resolve) => {
      currentAudio.onended = () => {
        resolve();
      };
      currentAudio.play();
 });
  } catch (error) {
    console.error("Error playing audio:", error);
  }
}

function clearQueue() {
  audioQueue = [];
}
                                                                     
                                                                           
                                                                                     