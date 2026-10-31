/** Playwright probe: no getUserMedia, no microphone, no capture permission requested. */
import { chromium, firefox, webkit } from 'playwright'
const report = []
for (const [name, type] of Object.entries({ chromium, firefox, webkit })) {
  let browser
  try {
    browser = await type.launch({ headless: true })
    const page = await browser.newPage()
    await page.goto('http://127.0.0.1:55887/revisar.html')
    const data = await page.evaluate(async () => {
      const supported = navigator.mediaDevices?.getSupportedConstraints() ?? null
      const mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm', 'audio/wav']
      const context = new AudioContext()
      const oscillator = context.createOscillator()
      const destination = context.createMediaStreamDestination()
      oscillator.connect(destination)
      const track = destination.stream.getAudioTracks()[0]
      const formats = []
      for (const format of mime) {
        if (!MediaRecorder.isTypeSupported(format)) { formats.push({format, supported: false}); continue }
        const recorder = new MediaRecorder(destination.stream, { mimeType: format })
        const chunks = []
        recorder.ondataavailable = e => chunks.push(e.data)
        const stopped = new Promise(resolve => { recorder.onstop = resolve })
        recorder.start(); await new Promise(resolve => setTimeout(resolve, 150)); recorder.stop(); await stopped
        formats.push({ format, supported: true, effectiveMime: recorder.mimeType,
          effectiveAudioBitsPerSecond: recorder.audioBitsPerSecond,
          bytes: new Blob(chunks).size, source: 'WEB_AUDIO_SYNTHETIC_NOT_MICROPHONE' })
      }
      const result = { supportedConstraints: supported,
        syntheticTrackCapabilities: track.getCapabilities?.() ?? null,
        syntheticTrackSettings: track.getSettings(), formats,
        microphoneSettings: null, microphoneVerified: false,
        reviewSections: document.querySelectorAll('section').length }
      destination.stream.getTracks().forEach(t=>t.stop()); await context.close(); return result
    })
    report.push({ browser: name, version: browser.version(), status: 'PASS', ...data })
  } catch(error) { report.push({browser:name, status:'UNAVAILABLE', error:String(error)}) }
  finally { await browser?.close() }
}
console.log(JSON.stringify(report,null,2))
