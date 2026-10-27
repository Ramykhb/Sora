# Sora React dashboard

A responsive React dashboard using Vite, with the existing Sora design and local sample data. Dependencies have not been installed as part of this migration.

## Run

Use Node.js 22.12 or newer. From the project root:

```sh
cd dashboard
npm install
npm run dev
```

Open http://127.0.0.1:5173. Vite is required; opening `index.html` directly or serving it with Python no longer runs the React app.

```sh
npm run build    # Production output in dist/
npm run preview  # Preview that production build
```

## Included

- Overview with sample metrics, activity, recent moments and question summaries.
- Session preview with pause/resume, object outlines and expanded view.
- Frame library with combined search, type/date filtering and detail dialogs.
- Conversations with text/language filters and supporting-frame dialogs.
- Preferences held in React state, shared across pages and reset on reload.
- Responsive desktop/mobile styles, keyboard navigation, native modal focus handling, Escape dismissal, visible focus indicators, screen-reader labels and reduced-motion support.

Hash routes (`#overview`, `#live`, `#frames`, `#questions`, `#settings`) support browser back/forward navigation without server routing configuration. Unknown hashes show the overview.

All content remains demo data. There are no API calls, authentication wiring, camera access or third-party asset requests. The scene and thumbnails use the original local SVG illustration. Backend settings are not required.

## Structure

```text
dashboard/
├── assets/scene.svg
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── styles.css
    ├── components/
    │   ├── Layout.jsx
    │   ├── Icon.jsx
    │   ├── Shared.jsx
    │   ├── SessionPreview.jsx
    │   ├── FrameCard.jsx
    │   └── DetailDialog.jsx
    ├── data/demo.js
    ├── hooks/usePage.js
    └── pages/
        ├── Overview.jsx
        ├── LiveSession.jsx
        ├── FrameLibrary.jsx
        ├── Conversations.jsx
        └── Preferences.jsx
```
