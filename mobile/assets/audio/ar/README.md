These bundled recordings use Gemini Aoede with the project's female Lebanese Arabic delivery instructions. They were generated with `gemini-3.8-flash-lite-tts` and encoded as 96 kbps MP3.

- `obstacle.mp3`: يوجد جسم في وسط صورة الكاميرا. لا يمكنني تقييم المسار كاملاً.
- `closed-door.mp3`: يبدو أن هناك باباً مغلقاً في وسط صورة الكاميرا.
- `unavailable.mp3`: الصوت غير متاح حالياً. الإجابة ظاهرة على الشاشة.

Obstacle recordings match the backend's two Arabic warning messages. They play locally to avoid cloud latency, quota failures, and switching to the device voice. The unavailable recording reports failed answer synthesis; it does not replace the displayed answer.
