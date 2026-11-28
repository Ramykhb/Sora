// SORA understands English, Arabic and French voice commands. The language chosen
// in Settings (defaulting to the phone's locale) picks which language the speech
// recognizer listens in and which language SORA speaks its command feedback in.
// Parsing itself always accepts all three.
export type VoiceLanguage = 'en' | 'ar' | 'fr';
export const VOICE_LANGUAGES: { id: VoiceLanguage; label: string }[] = [
  { id: 'en', label: 'English' },
  { id: 'ar', label: 'العربية' },
  { id: 'fr', label: 'Français' },
];
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

// Supply vowels for the ambiguous imperative without rewriting displayed text
// or the distinct word «أبداً» (never). Preserve already vocalized Arabic.
export function speechText(text: string, language: string) {
  if (language.toLowerCase().split(/[-_]/)[0] !== 'ar') return text;
  return text.replace(/(^|[^\p{L}\p{N}\p{M}])(?:ابدأ|إبدأ)(?=$|[^\p{L}\p{N}\p{M}])/gu, '$1اِبْدَأْ');
}

const english = {
  startStreamFirst: 'Start a stream first.',
  noStream: 'There is no active stream.',
  controlFailed: 'Unable to control your stream. Please try again.',
  answerFailed: 'Unable to answer. Please try again.',
  notAvailable: 'That app command is not available yet.',
  noAnswer: 'There is no answer to repeat yet.',
  noDirections: 'There are no directions to repeat yet.',
  voiceUnmuted: 'Voice unmuted.',
  listeningOnPausedStream: 'Question listening is on. Resume your stream to ask questions.',
  listeningOn: 'Listening for questions again.',
  listeningOff: 'Questions are paused.',
  startingStream: 'Starting your stream.',
  resumingStream: 'Resuming your stream.',
  alreadyRunning: 'Your stream is already running.',
  alreadyPaused: 'Your stream is already paused.',
  pausedConfirm: 'Stream paused.',
  stopConfirm: 'Stream stopped.',
  detectionOn: 'Obstacle detection is on.',
  detectionOff: 'Obstacle detection is off.',
  detectionAlreadyOn: 'Obstacle detection is already on.',
  detectionAlreadyOff: 'Obstacle detection is already off.',
  cameraPermission: 'Camera access is required. Enable it in your device settings, then try again.',
  cameraGuidance: 'Point your camera at your surroundings.',
  homeGuidance: 'Tap anywhere in the main area to start your stream.',
  sosGetting: 'Getting your current location for SOS…',
  sosSent: 'Your location was sent to your SOS contact.',
  sosContactRequired: 'Add and save your SOS contact email in Settings first.',
  sosSignInChanged: 'Sign-in changed. Please try sharing your SOS location again.',
  sosFailed: 'Unable to send your SOS location.',
  locationAccessRequired: 'Allow location access in Settings to use your current location.',
  locationTimedOut: 'Location timed out. Move where GPS is available and try again.',
};
export type VoiceMessage = keyof typeof english;
const messages: Record<VoiceLanguage, Record<VoiceMessage, string>> = {
  en: english,
  ar: {
    startStreamFirst: 'ابدأ البث أولاً.',
    noStream: 'لا يوجد بث نشط.',
    controlFailed: 'تعذر التحكم في البث. حاول مرة أخرى.',
    answerFailed: 'تعذر الإجابة. حاول مرة أخرى.',
    notAvailable: 'هذا الأمر غير متاح بعد.',
    noAnswer: 'لا توجد إجابة لإعادة تكرارها بعد.',
    noDirections: 'لا توجد اتجاهات لإعادة تكرارها بعد.',
    voiceUnmuted: 'تم إلغاء كتم الصوت.',
    listeningOnPausedStream: 'الاستماع للأسئلة مفعّل. استأنف البث لطرح الأسئلة.',
    listeningOn: 'الاستماع للأسئلة مرة أخرى.',
    listeningOff: 'تم إيقاف الأسئلة مؤقتاً.',
    startingStream: 'جارٍ بدء البث.',
    resumingStream: 'جارٍ استئناف البث.',
    alreadyRunning: 'البث يعمل بالفعل.',
    alreadyPaused: 'البث متوقف مؤقتاً بالفعل.',
    pausedConfirm: 'تم إيقاف البث مؤقتاً.',
    stopConfirm: 'تم إيقاف البث.',
    detectionOn: 'تم تشغيل كشف العوائق.',
    detectionOff: 'تم إيقاف كشف العوائق.',
    detectionAlreadyOn: 'كشف العوائق قيد التشغيل بالفعل.',
    detectionAlreadyOff: 'كشف العوائق متوقف بالفعل.',
    cameraPermission: 'مطلوب إذن الكاميرا. فعّله من إعدادات الجهاز ثم حاول مرة أخرى.',
    cameraGuidance: 'وجّه الكاميرا نحو ما حولك.',
    homeGuidance: 'اضغط في أي مكان في المنطقة الرئيسية لبدء البث.',
    sosGetting: 'جارٍ تحديد موقعك لإرسال الطوارئ…',
    sosSent: 'تم إرسال موقعك إلى جهة اتصال الطوارئ.',
    sosContactRequired: 'أضف بريد جهة اتصال الطوارئ واحفظه في الإعدادات أولاً.',
    sosSignInChanged: 'تغيّر تسجيل الدخول. حاول إرسال موقع الطوارئ مرة أخرى.',
    sosFailed: 'تعذر إرسال موقع الطوارئ.',
    locationAccessRequired: 'اسمح بالوصول إلى الموقع في الإعدادات لاستخدام موقعك الحالي.',
    locationTimedOut: 'انتهت مهلة تحديد الموقع. انتقل إلى مكان يتوفر فيه GPS وحاول مرة أخرى.',
  },
  fr: {
    startStreamFirst: 'Démarrez d’abord un flux.',
    noStream: 'Aucun flux n’est actif.',
    controlFailed: 'Impossible de contrôler votre flux. Réessayez.',
    answerFailed: 'Impossible de répondre. Réessayez.',
    notAvailable: 'Cette commande n’est pas encore disponible.',
    noAnswer: 'Aucune réponse à répéter pour l’instant.',
    noDirections: 'Aucun itinéraire à répéter pour l’instant.',
    voiceUnmuted: 'Son rétabli.',
    listeningOnPausedStream: 'L’écoute des questions est activée. Reprenez votre flux pour poser des questions.',
    listeningOn: 'J’écoute de nouveau vos questions.',
    listeningOff: 'Les questions sont en pause.',
    startingStream: 'Je démarre votre flux.',
    resumingStream: 'Je reprends votre flux.',
    alreadyRunning: 'Votre flux est déjà en cours.',
    alreadyPaused: 'Votre flux est déjà en pause.',
    pausedConfirm: 'Flux en pause.',
    stopConfirm: 'Flux arrêté.',
    detectionOn: 'La détection des obstacles est activée.',
    detectionOff: 'La détection des obstacles est désactivée.',
    detectionAlreadyOn: 'La détection des obstacles est déjà activée.',
    detectionAlreadyOff: 'La détection des obstacles est déjà désactivée.',
    cameraPermission: 'L’accès à la caméra est requis. Activez-le dans les réglages de votre appareil, puis réessayez.',
    cameraGuidance: 'Pointez la caméra vers ce qui vous entoure.',
    homeGuidance: 'Touchez n’importe où dans la zone principale pour démarrer votre flux.',
    sosGetting: 'Localisation de votre position pour le SOS…',
    sosSent: 'Votre position a été envoyée à votre contact SOS.',
    sosContactRequired: 'Ajoutez et enregistrez l’adresse e-mail de votre contact SOS dans Réglages.',
    sosSignInChanged: 'La session a changé. Réessayez d’envoyer votre position SOS.',
    sosFailed: 'Impossible d’envoyer votre position SOS.',
    locationAccessRequired: 'Autorisez l’accès à la position dans Réglages pour utiliser votre position actuelle.',
    locationTimedOut: 'La localisation a expiré. Déplacez-vous là où le GPS fonctionne et réessayez.',
  },
};
export function voiceText(message: VoiceMessage, language: VoiceLanguage = voiceLanguage()) { return messages[language][message]; }
