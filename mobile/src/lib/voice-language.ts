// SORA understands English, Arabic and French voice commands. The phone's locale
// picks which language the speech recognizer listens in and which language SORA
// speaks its command feedback in. Parsing itself always accepts all three.
export type VoiceLanguage = 'en' | 'ar' | 'fr';
const tags: Record<VoiceLanguage, { speech: string; recognition: string }> = {
  en: { speech: 'en-US', recognition: 'en-US' },
  ar: { speech: 'ar-SA', recognition: 'ar-SA' },
  fr: { speech: 'fr-FR', recognition: 'fr-FR' },
};
export function voiceLanguageFromLocale(locale: string): VoiceLanguage {
  const language = locale.toLowerCase().split(/[-_]/)[0];
  return language === 'ar' || language === 'fr' ? language : 'en';
}
let detected: VoiceLanguage | null = null;
export function voiceLanguage(): VoiceLanguage {
  if (detected) return detected;
  try { detected = voiceLanguageFromLocale(Intl.DateTimeFormat().resolvedOptions().locale); }
  catch { detected = 'en'; }
  return detected;
}
export function speechLanguage(language: VoiceLanguage = voiceLanguage()) { return tags[language].speech; }
export function recognitionLanguage(language: VoiceLanguage = voiceLanguage()) { return tags[language].recognition; }

const english = {
  startStreamFirst: 'Start a stream first by saying Hey Sora, start stream. Then ask about your surroundings.',
  noStream: 'There is no stream open to control. Say Hey Sora, start stream first.',
  controlFailed: 'Unable to control your stream. Please try again.',
  answerFailed: 'Unable to answer. Please try again.',
  notAvailable: 'That app command is not available yet.',
  noAnswer: 'There is no answer to repeat yet. Ask a question first.',
  noDirections: 'There are no directions to repeat yet. Ask for a walking route first.',
  voiceUnmuted: 'Voice unmuted.',
  listeningOnPausedStream: 'Question listening is on. Resume your stream to ask questions.',
  listeningOn: 'Listening for questions again.',
  listeningOff: 'Questions are paused. Playback controls and Hey Sora commands remain available. Say Hey Sora, start listening to ask questions again.',
  startingStream: 'Starting your stream.',
  resumingStream: 'Resuming your stream.',
  alreadyRunning: 'Your stream is already running.',
  alreadyPaused: 'Your stream is already paused.',
  pausedConfirm: 'Stream paused. Say Hey Sora, resume stream when you are ready.',
  stopConfirm: 'Stream stopped. Your saved moments are still available.',
  cameraPermission: 'Camera access is required. Enable it in your device settings, then try again.',
};
export type VoiceMessage = keyof typeof english;
const messages: Record<VoiceLanguage, Record<VoiceMessage, string>> = {
  en: english,
  ar: {
    startStreamFirst: 'ابدأ البث أولاً بقول «يا سورا، ابدأ البث»، ثم اسأل عما حولك.',
    noStream: 'لا يوجد بث مفتوح للتحكم به. قل «يا سورا، ابدأ البث» أولاً.',
    controlFailed: 'تعذر التحكم في البث. حاول مرة أخرى.',
    answerFailed: 'تعذر الإجابة. حاول مرة أخرى.',
    notAvailable: 'هذا الأمر غير متاح بعد.',
    noAnswer: 'لا توجد إجابة لإعادة تكرارها بعد. اطرح سؤالاً أولاً.',
    noDirections: 'لا توجد اتجاهات لإعادة تكرارها بعد. اطلب مسار المشي أولاً.',
    voiceUnmuted: 'تم إلغاء كتم الصوت.',
    listeningOnPausedStream: 'الاستماع للأسئلة مفعّل. استأنف البث لطرح الأسئلة.',
    listeningOn: 'الاستماع للأسئلة مرة أخرى.',
    listeningOff: 'تم إيقاف الأسئلة مؤقتاً. تبقى أوامر التشغيل وأوامر «يا سورا» متاحة. قل «يا سورا، ابدأ الاستماع» لطرح الأسئلة مجدداً.',
    startingStream: 'جارٍ بدء البث.',
    resumingStream: 'جارٍ استئناف البث.',
    alreadyRunning: 'البث يعمل بالفعل.',
    alreadyPaused: 'البث متوقف مؤقتاً بالفعل.',
    pausedConfirm: 'تم إيقاف البث مؤقتاً. قل «يا سورا، استأنف البث» عندما تكون مستعداً.',
    stopConfirm: 'تم إيقاف البث. لحظاتك المحفوظة ما زالت متاحة.',
    cameraPermission: 'مطلوب إذن الكاميرا. فعّله من إعدادات الجهاز ثم حاول مرة أخرى.',
  },
  fr: {
    startStreamFirst: 'Démarrez d’abord un flux en disant « Hé Sora, démarre le flux ». Posez ensuite votre question sur ce qui vous entoure.',
    noStream: 'Aucun flux n’est ouvert à contrôler. Dites « Hé Sora, démarre le flux » d’abord.',
    controlFailed: 'Impossible de contrôler votre flux. Réessayez.',
    answerFailed: 'Impossible de répondre. Réessayez.',
    notAvailable: 'Cette commande n’est pas encore disponible.',
    noAnswer: 'Aucune réponse à répéter pour l’instant. Posez d’abord une question.',
    noDirections: 'Aucun itinéraire à répéter pour l’instant. Demandez d’abord un itinéraire piéton.',
    voiceUnmuted: 'Son rétabli.',
    listeningOnPausedStream: 'L’écoute des questions est activée. Reprenez votre flux pour poser des questions.',
    listeningOn: 'J’écoute de nouveau vos questions.',
    listeningOff: 'Les questions sont en pause. Les commandes de lecture et « Hé Sora » restent disponibles. Dites « Hé Sora, commence à écouter » pour poser des questions.',
    startingStream: 'Je démarre votre flux.',
    resumingStream: 'Je reprends votre flux.',
    alreadyRunning: 'Votre flux est déjà en cours.',
    alreadyPaused: 'Votre flux est déjà en pause.',
    pausedConfirm: 'Flux en pause. Dites « Hé Sora, reprends le flux » quand vous êtes prêt.',
    stopConfirm: 'Flux arrêté. Vos moments enregistrés restent disponibles.',
    cameraPermission: 'L’accès à la caméra est requis. Activez-le dans les réglages de votre appareil, puis réessayez.',
  },
};
export function voiceText(message: VoiceMessage, language: VoiceLanguage = voiceLanguage()) { return messages[language][message]; }
