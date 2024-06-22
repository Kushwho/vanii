let isRecording = false;
let socket;
let microphone;
let audioQueue = [];
let isPlayingAudio = false;

const socket_port = 5001;
socket = io("http://" + window.location.hostname + ":" + socket_port.toString());


socket.on('connect', () => {
  socket.emit('session_start', "1");
});


socket.on("transcription_update", (data) => {
  const { transcription, audioBinary } = data;
  console.log("I am transcription " + transcription)
  console.log("I am adio_binary " + audioBinary)
  const captions = document.getElementById("captions");
  captions.innerHTML = transcription;
  enqueueAudio(audioBinary);
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
      console.log("Client: Microphone data received");
      if (event.data.size > 0) {
        socket.emit("audio_stream", event.data);
      }
    };
    microphone.start(1000);
  });
}

async function startRecording() {
  isRecording = true;
  microphone = await getMicrophone();
  console.log("Client: Waiting to open microphone");
  await openMicrophone(microphone, socket);
}

async function stopRecording() {
  if (isRecording === true) {
    microphone.stop();
    microphone.stream.getTracks().forEach((track) => track.stop());
    socket.emit("toggle_transcription", { action: "stop" });
    microphone = null;
    isRecording = false;
    console.log("Client: Microphone closed");
    document.body.classList.remove("recording");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const recordButton = document.getElementById("record");

  recordButton.addEventListener("click", () => {
    if (!isRecording) {
      socket.emit("toggle_transcription", { action: "start" });
      startRecording().catch((error) => console.error("Error starting recording:", error));
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
let i = 0
async function playNextAudio() {
  if (audioQueue.length === 0) {
    isPlayingAudio = false;
    return;
  }
  i++
  console.log(i)
  isPlayingAudio = true;
  const audioBinary = audioQueue.shift();
  await playAudio(audioBinary);
  playNextAudio();
}

async function playAudio(audioBinary) {
  try {
    const audioBlob = new Blob([audioBinary], { type: 'audio/mpeg' });
    const audioUrl = URL.createObjectURL(audioBlob);

    const audio = new Audio(audioUrl);
    return new Promise((resolve) => {
      audio.onended = () => {
        resolve();
      };
      audio.play();
    });
  } catch (error) {
    console.error("Error playing audio:", error);
  }
}
