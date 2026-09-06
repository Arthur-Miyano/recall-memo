// 单词发音：浏览器原生 Web Speech API，零依赖可离线
// 两个坑（MDN）：语音列表异步加载（首次 getVoices 可能为空，要等 onvoiceschanged）；
// 必须显式选英文语音，否则中文 Windows 会用中文引擎读英文
let voicesPromise = null

function loadVoices() {
  if (!('speechSynthesis' in window)) return Promise.resolve([])
  const v = speechSynthesis.getVoices()
  if (v.length) return Promise.resolve(v)
  if (!voicesPromise) {
    voicesPromise = new Promise((resolve) => {
      const timer = setTimeout(() => resolve(speechSynthesis.getVoices() || []), 1500)
      speechSynthesis.onvoiceschanged = () => {
        clearTimeout(timer)
        resolve(speechSynthesis.getVoices() || [])
      }
    })
  }
  return voicesPromise
}

export async function speakWord(word) {
  if (!('speechSynthesis' in window)) return false
  const voices = await loadVoices()
  const u = new SpeechSynthesisUtterance(word)
  u.lang = 'en-US'
  // 优先本机/在线英文语音（Edge 有 Natural 语音），找不到就让 lang 兜底
  const voice = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith('en'))
  if (voice) u.voice = voice
  u.rate = 0.92
  speechSynthesis.cancel()
  speechSynthesis.speak(u)
  return true
}
