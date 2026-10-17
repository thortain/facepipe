import {FaceLandmarker, FilesetResolver} from '/assets/vendor/vision_bundle.mjs';

const video = document.getElementById('camera');
const token = document.getElementById('token');
const status = document.getElementById('status');
const startButton = document.getElementById('start');
const modelButton = document.getElementById('model-test');
const stopButton = document.getElementById('stop');
let stream = null;
let landmarker = null;
let running = false;
let pending = false;
let lastVideoTime = -1;
let lastSent = 0;
let sent = 0;

async function loadModel() {
  if (landmarker) return landmarker;
  const files = await FilesetResolver.forVisionTasks('/assets/vendor/wasm');
  landmarker = await FaceLandmarker.createFromOptions(files, {
    baseOptions: {modelAssetPath: '/assets/face_landmarker.task'},
    runningMode: 'VIDEO', numFaces: 1,
    outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true,
  });
  return landmarker;
}

const degrees = radians => radians * 180 / Math.PI;
const zero3 = () => [0, 0, 0];

function pose(matrix) {
  if (!matrix?.data || matrix.data.length < 16) return [0, 0, 0, 0, 0, 0];
  const m = matrix.data;
  const pitch = Math.asin(Math.max(-1, Math.min(1, -m[8])));
  const roll = Math.atan2(m[9], m[10]);
  const yaw = Math.atan2(m[4], m[0]);
  return [degrees(roll), degrees(pitch), degrees(yaw), m[3] * 0.01, m[7] * 0.01, m[11] * 0.01];
}

function eyePose(landmarks, indices) {
  if (!landmarks || landmarks.length < 478) return zero3();
  const iris = indices.map(index => landmarks[index]);
  const cx = iris.reduce((total, point) => total + point.x, 0) / iris.length;
  const cy = iris.reduce((total, point) => total + point.y, 0) / iris.length;
  const nearby = landmarks.filter(point => (point.x - cx) ** 2 + (point.y - cy) ** 2 < 0.025 ** 2);
  if (!nearby.length) return zero3();
  const ex = nearby.reduce((total, point) => total + point.x, 0) / nearby.length;
  const ey = nearby.reduce((total, point) => total + point.y, 0) / nearby.length;
  const clamp = value => Math.max(-35, Math.min(35, value));
  return [clamp(degrees(Math.atan2(cx - ex, 0.02))),
          clamp(-degrees(Math.atan2(cy - ey, 0.02))), 0];
}

function frameFromResult(result) {
  const categories = result.faceBlendshapes?.[0]?.categories || [];
  const blend = {};
  for (const category of categories) {
    if (category.categoryName !== '_neutral') blend[category.categoryName] = category.score;
  }
  const landmarks = result.faceLandmarks?.[0] || null;
  return {
    tracking: !!landmarks,
    blend,
    head: pose(result.facialTransformationMatrixes?.[0]),
    leftEye: eyePose(landmarks, [468, 469, 470, 471, 472]),
    rightEye: eyePose(landmarks, [473, 474, 475, 476, 477]),
    landmarks: landmarks?.map(point => [point.x, point.y]) || null,
  };
}

async function tick() {
  if (!running) return;
  const now = performance.now();
  if (!pending && video.readyState >= 2 && video.currentTime !== lastVideoTime && now - lastSent >= 33) {
    lastVideoTime = video.currentTime;
    lastSent = now;
    pending = true;
    try {
      const result = landmarker.detectForVideo(video, now);
      const response = await fetch('/api/frame', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-FacePipe-Token': token.value},
        body: JSON.stringify(frameFromResult(result)),
      });
      if (!response.ok) throw Error(response.status === 403 ? 'Pairing token rejected' : `Bridge HTTP ${response.status}`);
      sent += 1;
      status.textContent = `Streaming motion data: ${sent} frames`;
    } catch (error) {
      status.textContent = error.message;
      stop();
      return;
    } finally { pending = false; }
  }
  requestAnimationFrame(tick);
}

async function start() {
  if (running) return;
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    status.textContent = 'Camera access needs HTTPS, or localhost on this same device.';
    return;
  }
  startButton.disabled = true;
  status.textContent = 'Loading local face model...';
  try {
    await loadModel();
    stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'user'}, audio: false});
    video.srcObject = stream;
    await video.play();
    running = true;
    stopButton.disabled = false;
    status.textContent = 'Camera ready';
    requestAnimationFrame(tick);
  } catch (error) {
    status.textContent = error.message;
    stop();
  }
}

function stop() {
  running = false;
  stream?.getTracks().forEach(track => track.stop());
  stream = null;
  video.srcObject = null;
  startButton.disabled = false;
  stopButton.disabled = true;
}

startButton.addEventListener('click', start);
modelButton.addEventListener('click', async () => {
  modelButton.disabled = true;
  status.textContent = 'Loading local face model...';
  try {
    await loadModel();
    status.textContent = 'Model ready';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    modelButton.disabled = false;
  }
});
stopButton.addEventListener('click', stop);
window.addEventListener('pagehide', stop);
