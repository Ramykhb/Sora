// Illustrative fixtures only. No backend calls are made.
export const frames = [
  {
    "id": "FR-0248",
    "title": "An open doorway ahead",
    "time": "10:42:08",
    "tags": [
      "Door",
      "Exit sign"
    ],
    "type": "Text detected",
    "scene": 1,
    "caption": "A green door with an EXIT sign above it. A table is visible to the left.",
    "ocr": "EXIT →",
    "date": "Today",
    "quality": 96
  },
  {
    "id": "FR-0247",
    "title": "Table by the window",
    "time": "10:41:56",
    "tags": [
      "Table",
      "Cup"
    ],
    "type": "Objects detected",
    "scene": 2,
    "caption": "A wooden table near the window, with a cup and a small stack of books.",
    "ocr": "No text detected",
    "date": "Today",
    "quality": 95
  },
  {
    "id": "FR-0246",
    "title": "Inside the study room",
    "time": "10:41:42",
    "tags": [
      "Room",
      "Furniture"
    ],
    "type": "Scene captured",
    "scene": 3,
    "caption": "A furnished study room with a table, a window, a door and a potted plant.",
    "ocr": "EXIT →",
    "date": "Today",
    "quality": 94
  },
  {
    "id": "FR-0245",
    "title": "A plant beside the wall",
    "time": "10:41:28",
    "tags": [
      "Plant",
      "Indoor"
    ],
    "type": "Objects detected",
    "scene": 4,
    "caption": "A leafy plant in a pot against the wall, to the left of a table.",
    "ocr": "No text detected",
    "date": "Today",
    "quality": 93
  },
  {
    "id": "FR-0244",
    "title": "Exit sign in the hallway",
    "time": "10:40:14",
    "tags": [
      "Exit sign",
      "Door"
    ],
    "type": "Text detected",
    "scene": 1,
    "caption": "An illuminated exit sign with an arrow pointing right, above a green door.",
    "ocr": "EXIT →",
    "date": "Today",
    "quality": 96
  },
  {
    "id": "FR-0243",
    "title": "A cup on the table",
    "time": "10:39:51",
    "tags": [
      "Cup",
      "Table"
    ],
    "type": "Objects detected",
    "scene": 2,
    "caption": "A light-colored cup sitting on a wooden table next to books.",
    "ocr": "No text detected",
    "date": "Today",
    "quality": 95
  },
  {
    "id": "FR-0242",
    "title": "An afternoon indoors",
    "time": "15:24:10",
    "tags": [
      "Room",
      "Window"
    ],
    "type": "Scene captured",
    "scene": 3,
    "caption": "Sunlight comes through the study room window. Furniture is visible in front of the camera.",
    "ocr": "EXIT →",
    "date": "Yesterday",
    "quality": 94
  },
  {
    "id": "FR-0241",
    "title": "Greenery near the window",
    "time": "15:23:48",
    "tags": [
      "Plant",
      "Window"
    ],
    "type": "Objects detected",
    "scene": 4,
    "caption": "A potted plant is positioned near a window, beside the study area.",
    "ocr": "No text detected",
    "date": "Yesterday",
    "quality": 93
  }
];

export const questions = [
  {
    "q": "What’s in front of me?",
    "a": "There’s a wooden table ahead with a cup and some books. A door is visible further to the right.",
    "time": "10:42 AM",
    "language": "English",
    "status": "Grounded",
    "frame": 0,
    "scope": "Current scene"
  },
  {
    "q": "What does the sign say?",
    "a": "The sign above the door reads “EXIT” and has an arrow pointing to the right.",
    "time": "10:40 AM",
    "language": "English",
    "status": "Grounded",
    "frame": 4,
    "scope": "Read text"
  },
  {
    "q": "Est-ce qu’il y a une porte ?",
    "a": "Oui, une porte verte se trouve devant vous, à droite de la table.",
    "time": "10:38 AM",
    "language": "Français",
    "status": "Grounded",
    "frame": 0,
    "scope": "Current scene"
  },
  {
    "q": "Can I walk forward?",
    "a": "A table is visible in front of you. I can’t confirm that the path is clear; use your usual mobility aid.",
    "time": "10:36 AM",
    "language": "English",
    "status": "Uncertain",
    "frame": 2,
    "scope": "Current scene"
  }
];

export const defaultPreferences = () => ({ spoken: true, alerts: true, boxes: true, language: 'English', retention: '24 hours' });
