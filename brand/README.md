# Sora identity

Buddy is Sora’s minimal robot mark: an open purple frame and two pale pill-shaped eyes. UI logos and hero artwork have fully transparent backgrounds. Light mode uses a darker purple frame and dark eyes for contrast. Only launcher app icons retain the charcoal background. The dashboard and mobile use the same purple identity (#B79AFF) on charcoal (#090B10).

- `sora-symbol.svg`: standalone mark.
- `sora-logo.svg`: transparent Buddy for both apps.
- `sora-logo-light.svg`: transparent Buddy with dark eyes for light backgrounds.
- `sora-hero.svg` / `sora-hero-light.svg`: transparent hero artwork for mobile onboarding, sign-in and home.
- `sora-app-icon.svg`: opaque, square 1024 px store/iOS icon (the OS applies its mask).
- `sora-adaptive-foreground.svg`: transparent Android foreground within the central safe area.
- `sora-monochrome.svg`: single-color Android themed icon.

Mobile PNG exports are in `mobile/assets/brand` and `mobile/assets/images`. Dashboard SVG copies and the favicon are in `dashboard/public/brand`. Export SVGs at their declared dimensions with transparency, except the opaque launcher app icon; favicon is 128 px. No runtime network requests or additional packages are needed for these assets.

Expo app icon, adaptive icon and splash configuration lives in `mobile/app.json`. Rebuild the native app after changing those launch assets. The in-app logo and hero load with the JavaScript app.

Run `node brand/generate-vectors.mjs` from the project root to regenerate the SVG family and dashboard copies. Mobile PNGs are raster exports of those SVGs at their declared dimensions.
