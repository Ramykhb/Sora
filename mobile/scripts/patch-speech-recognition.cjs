const fs = require('node:fs');
const path = require('node:path');

// Apple's voice-processing unit otherwise ducks AVSpeechSynthesizer/AVPlayer
// as "other audio". Preserve echo cancellation with minimal, fixed ducking.
const marker = '// SORA: Keep spoken answers audible with voice processing enabled.';
const anchor = '        try audioEngine.outputNode.setVoiceProcessingEnabled(true)';
const insertion = `${anchor}
        ${marker}
        if #available(iOS 17.0, *) {
          audioEngine.inputNode.voiceProcessingOtherAudioDuckingConfiguration =
            AVAudioVoiceProcessingOtherAudioDuckingConfiguration(
              enableAdvancedDucking: false,
              duckingLevel: .min
            )
        }`;

function patchSpeechRecognition(file) {
  const source = fs.readFileSync(file, 'utf8');
  if (source.includes(marker)) return false;
  if (!source.includes(anchor)) throw new Error('Unsupported expo-speech-recognition source: review the SORA audio ducking patch.');
  fs.writeFileSync(file, source.replace(anchor, insertion));
  return true;
}

if (require.main === module) {
  const root = path.dirname(require.resolve('expo-speech-recognition/package.json'));
  if (patchSpeechRecognition(path.join(root, 'ios/ExpoSpeechRecognizer.swift'))) {
    console.log('Applied SORA speech-recognition audio ducking fix.');
  }
}
module.exports = { patchSpeechRecognition };
