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
  cameraGuidance: 'Point your camera at your surroundings. Say describe the scene, or ask a question about your surroundings.',
  homeGuidance: 'Tap anywhere in the main area to start your stream. More tools and settings are at the bottom.',
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
    cameraGuidance: 'وجّه الكاميرا نحو ما حولك. قل «صف المشهد» أو اطرح سؤالاً عما حولك.',
    homeGuidance: 'اضغط في أي مكان في المنطقة الرئيسية لبدء البث. المزيد من الأدوات والإعدادات في الأسفل.',
    sosGetting: 'جارٍ تحديد موقعك لإرسال الطوارئ…',
    sosSent: 'تم إرسال موقعك إلى جهة اتصال الطوارئ.',
    sosContactRequired: 'أضف بريد جهة اتصال الطوارئ واحفظه في الإعدادات أولاً.',
    sosSignInChanged: 'تغيّر تسجيل الدخول. حاول إرسال موقع الطوارئ مرة أخرى.',
    sosFailed: 'تعذر إرسال موقع الطوارئ.',
    locationAccessRequired: 'اسمح بالوصول إلى الموقع في الإعدادات لاستخدام موقعك الحالي.',
    locationTimedOut: 'انتهت مهلة تحديد الموقع. انتقل إلى مكان يتوفر فيه GPS وحاول مرة أخرى.',
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
    cameraGuidance: 'Pointez la caméra vers ce qui vous entoure. Dites « décris la scène » ou posez une question sur votre environnement.',
    homeGuidance: 'Touchez n’importe où dans la zone principale pour démarrer votre flux. Plus d’outils et les réglages se trouvent en bas.',
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
