import type { VoiceLanguage } from './voice-language';

const ADVICE = {
  en: {
    ground: "The ground isn't visible—tilt the camera slightly downward and try again.",
    dark: 'The image looks too dark. Move toward better light and try again.',
    blur: 'The image looks blurry. Hold the camera steady, let it focus, and try again.',
    partial: 'Part of the subject is outside the view. Move back slightly and center it in the frame.',
    stale: 'A fresh view was not available. Hold the camera steady and ask again.',
    generic: 'For a clearer answer, center what you want to identify, hold the camera steady, and try again in good light.',
  },
  fr: {
    ground: 'Le sol n’est pas visible. Inclinez légèrement la caméra vers le bas et réessayez.',
    dark: 'L’image est trop sombre. Déplacez-vous vers un meilleur éclairage et réessayez.',
    blur: 'L’image est floue. Tenez la caméra immobile, laissez-la faire la mise au point, puis réessayez.',
    partial: 'Une partie du sujet est hors du champ. Reculez légèrement et centrez-le dans le cadre.',
    stale: 'Aucune vue récente n’était disponible. Tenez la caméra immobile et posez de nouveau la question.',
    generic: 'Pour une réponse plus claire, centrez ce que vous voulez identifier, tenez la caméra immobile et réessayez avec un bon éclairage.',
  },
  ar: {
    ground: 'الأرض غير ظاهرة. أمل الكاميرا قليلاً إلى الأسفل وحاول مرة أخرى.',
    dark: 'الصورة شديدة الظلمة. انتقل إلى إضاءة أفضل وحاول مرة أخرى.',
    blur: 'الصورة غير واضحة. ثبّت الكاميرا وانتظر التركيز ثم حاول مرة أخرى.',
    partial: 'جزء من الهدف خارج الإطار. تراجع قليلاً وضعه في وسط الإطار.',
    stale: 'لم تتوفر صورة حديثة. ثبّت الكاميرا واطرح السؤال مرة أخرى.',
    generic: 'للحصول على إجابة أوضح، ضع ما تريد التعرف عليه في وسط الإطار، وثبّت الكاميرا، وحاول مجدداً في إضاءة جيدة.',
  },
} as const;

/** Actionable recapture advice grounded in an uncertain visual answer. */
export function cameraFeedback(uncertain: boolean, answer: string, warnings: readonly string[] = [], visualContext = true, language: VoiceLanguage = 'en'): string | null {
  if (!uncertain || !visualContext) return null;
  const text = answer.toLowerCase();
  const advice = ADVICE[language];
  if (
    (/ground|floor|walking surface|path ahead/.test(text) && /not visible|isn't visible|can't see|cannot see|out of (?:the )?(?:view|frame)|not shown|unclear/.test(text))
    || (/sol|surface|passage/.test(text) && /pas visible|invisible|non visible|hors (?:du )?(?:champ|cadre)|impossible de voir|peu visible/.test(text))
    || (/(?:الأرض|أرضية|المسار)/.test(text) && /غير مرئي|لا يظهر|خارج الإطار|غير واضح/.test(text))
  ) {
    return advice.ground;
  }
  if (/too dark|low light|poor lighting|not enough light|underexposed|dim image|image is dark|sombre|obscur|peu de lumière|éclairage faible|مظلم|مظلمة|إضاءة ضعيفة|قاتم/.test(text)) {
    return advice.dark;
  }
  if (/blurr|out of focus|motion blur|shak|flou|brouill|secou|bougé|ضبابي|غير حاد|اهتزاز|مهزوز/.test(text)) {
    return advice.blur;
  }
  if (/partially (?:visible|hidden)|cut off|out of (?:the )?frame|not fully visible|partiellement|coupé|hors (?:du )?(?:champ|cadre)|pas entièrement|جزء|جزئي|خارج الإطار|غير كامل/.test(text)) {
    return advice.partial;
  }
  if (warnings.includes('current_view_timeout') || warnings.includes('evidence_expired_during_inference')) {
    return advice.stale;
  }
  return advice.generic;
}
