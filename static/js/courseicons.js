/* Course icons: a small line drawing for each course offering, shown on its card on the home page.
   An offering's icon is kept in its about.json as "icon" (one of the ids below). Without one, the
   course code's letters pick one (CSC → computer science, CHM → chemistry), else "book".
   Each is drawn on a 24×24 grid in strokes of currentColor, so it takes the card's ink. */

const D = d => `<path d="${d}"/>`;
const C = (x, y, r) => `<circle cx="${x}" cy="${y}" r="${r}"/>`;
const DOT = (x, y, r = 1) => `<circle cx="${x}" cy="${y}" r="${r}" fill="currentColor" stroke="none"/>`;
const R = (x, y, w, h, rx = 0, extra = "") => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}"${extra}/>`;

// [id, name, group, drawing]
const LIST = [
  // Computing
  ["compsci", "Computer Science", "Computing", R(3, 4, 18, 12, 2) + D("M8 20h8M12 16v4M10 7.5 7.5 10l2.5 2.5M14 7.5l2.5 2.5-2.5 2.5")],
  ["code", "Programming", "Computing", D("M8 4c-2 0-2 1.5-2 3v2c0 1.5-1 2.5-2 3 1 .5 2 1.5 2 3v2c0 1.5 0 3 2 3M16 4c2 0 2 1.5 2 3v2c0 1.5 1 2.5 2 3-1 .5-2 1.5-2 3v2c0 1.5 0 3-2 3") + DOT(12, 12, 1.1)],
  ["terminal", "Systems", "Computing", R(3, 4, 18, 16, 2) + D("m7 9.5 3 2.5-3 2.5M12 15h5")],
  ["chip", "Computer Engineering", "Computing", R(6, 6, 12, 12, 1.5) + R(9.5, 9.5, 5, 5, .5) + D("M9 3v3M12 3v3M15 3v3M9 18v3M12 18v3M15 18v3M3 9h3M3 12h3M3 15h3M18 9h3M18 12h3M18 15h3")],
  ["robot", "Robotics", "Computing", R(4.5, 8, 15, 11, 3) + D("M12 8V5.5M10 16h4M2.5 12v3M21.5 12v3") + C(12, 4.2, 1.3) + DOT(9, 12.5, 1.3) + DOT(15, 12.5, 1.3)],
  ["ai", "AI & Machine Learning", "Computing", D("M10 3.5c.7 4.4 2.6 6.3 7 7-4.4.7-6.3 2.6-7 7-.7-4.4-2.6-6.3-7-7 4.4-.7 6.3-2.6 7-7zM18 14.5c.3 1.8.8 2.2 2.5 2.5-1.7.3-2.2.8-2.5 2.5-.3-1.7-.8-2.2-2.5-2.5 1.7-.3 2.2-.7 2.5-2.5z")],
  ["data", "Databases", "Computing", `<ellipse cx="12" cy="5.5" rx="7" ry="2.5"/>` + D("M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5")],
  ["network", "Networks", "Computing", C(12, 5, 2) + C(5, 18, 2) + C(19, 18, 2) + C(12, 12.5, 2) + D("M12 7v3.5M10.3 13.6 6.7 16.9M13.7 13.6l3.6 3.3M7 18h10")],
  ["tree", "Algorithms", "Computing", R(9.5, 3, 5, 4, 1) + R(3, 10, 5, 4, 1) + R(16, 10, 5, 4, 1) + R(10, 17, 5, 4, 1) + D("M12 7v1.5H5.5V10M12 8.5h6.5V10M18.5 14v1.5H12.5V17")],
  ["security", "Security", "Computing", D("M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6z") + R(9, 11, 6, 5, 1) + D("M10 11V9.5a2 2 0 0 1 4 0V11")],
  ["key", "Cryptography", "Computing", C(7.5, 15.5, 4) + D("m10.5 12.5 9-9M15.5 7.5l2.5 2.5M18 5l2.5 2.5")],
  ["cloud", "Distributed Systems", "Computing", D("M7 19a4.5 4.5 0 0 1-.6-9A6 6 0 0 1 18 9.5a4.8 4.8 0 0 1-.5 9.5z")],
  ["game", "Graphics & Games", "Computing", D("M6.5 8h11a4 4 0 0 1 3.9 4.9l-.9 4a2.4 2.4 0 0 1-4.2 1L14.5 16h-5l-1.8 1.9a2.4 2.4 0 0 1-4.2-1l-.9-4A4 4 0 0 1 6.5 8zM7.5 10.5v3.5M5.8 12.2h3.4") + DOT(15.5, 11.5, 1) + DOT(17.5, 13.5, 1)],
  ["cursor", "Human–Computer Interaction", "Computing", D("M5 3.5 18.5 10 12.5 12 10 18z M12.5 12l6 6") + D("M3 21h3M3 21v-3")],
  // Mathematics
  ["math", "Mathematics", "Mathematics", D("M7 4v6M4 7h6M14 7h6M4.5 14.5l5 5M9.5 14.5l-5 5M14 17h6") + DOT(17, 14.3, 1) + DOT(17, 19.7, 1)],
  ["calculus", "Calculus", "Mathematics", D("M14 4.2c-1-1.3-3.3-1-3.6 1.3L8.6 18.5c-.3 2.3-2.6 2.6-3.6 1.3") + D("M14 18c1.2-5 2.6-7.5 6-9")],
  ["linalg", "Linear Algebra", "Mathematics", D("M7 4H5v16h2M17 4h2v16h-2") + DOT(9.5, 9, 1.2) + DOT(14.5, 9, 1.2) + DOT(9.5, 15, 1.2) + DOT(14.5, 15, 1.2)],
  ["infinity", "Discrete Math & Logic", "Mathematics", D("M12 12c-2-2.5-3.5-4-5.5-4a4 4 0 0 0 0 8c2 0 3.5-1.5 5.5-4zm0 0c2 2.5 3.5 4 5.5 4a4 4 0 0 0 0-8c-2 0-3.5 1.5-5.5 4z")],
  ["pi", "Number Theory", "Mathematics", D("M4 8c1-1.6 2.4-2.3 4-2.3h12M9.5 5.7c0 6-.8 10-3 13.3M15 5.7c-.2 5.5 0 9.5 1.5 12 .7 1.2 2 1.6 3.5 1")],
  ["geometry", "Geometry", "Mathematics", C(12, 4.5, 1.5) + D("M11.2 6 6 20M12.8 6 18 20M7.8 15h8.4")],
  ["stats", "Statistics", "Mathematics", D("M3 19h18M3 18c3 0 4.5-12 9-12s6 12 9 12M12 6v13")],
  ["chart", "Data Science", "Mathematics", D("M4 20h16") + R(5, 13, 3, 7, .5) + R(10.5, 7, 3, 13, .5) + R(16, 10, 3, 10, .5)],
  // Physical sciences
  ["physics", "Physics", "Physical Sciences", DOT(12, 12, 1.6) + `<ellipse cx="12" cy="12" rx="9.5" ry="3.6"/><ellipse cx="12" cy="12" rx="9.5" ry="3.6" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="9.5" ry="3.6" transform="rotate(120 12 12)"/>`],
  ["magnet", "Electromagnetism", "Physical Sciences", D("M5.5 3v9a6.5 6.5 0 0 0 13 0V3h-4.5v9a2 2 0 0 1-4 0V3zM5.5 7H10M14 7h4.5")],
  ["wave", "Waves & Signals", "Physical Sciences", D("M2 12c1.7-6 3.8-6 5 0s3.3 6 5 0 3.3-6 5 0 3.3 6 5 0M2 20h20")],
  ["planet", "Astronomy", "Physical Sciences", C(12, 12, 5.5) + `<ellipse cx="12" cy="12" rx="10" ry="3" transform="rotate(-20 12 12)"/>` + D("M19 3v3M17.5 4.5h3M4.5 18v2M3.5 19h2")],
  ["rocket", "Aerospace", "Physical Sciences", D("M12 2.5c3 2 4.5 5.5 4.5 9.5v5h-9v-5c0-4 1.5-7.5 4.5-9.5zM7.5 13 5 16v3.5l2.5-2.5M16.5 13l2.5 3v3.5L16.5 17M10 19.5l2 2 2-2") + C(12, 9.5, 1.6)],
  ["chemistry", "Chemistry", "Physical Sciences", D("M9 3h6M10 3v6L4.8 18.2A1.9 1.9 0 0 0 6.4 21h11.2a1.9 1.9 0 0 0 1.6-2.8L14 9V3M7 15h10") + DOT(10.5, 17.8, .9) + DOT(13.8, 17, .7)],
  ["molecule", "Organic Chemistry", "Physical Sciences", D("M12 3 19.8 7.5v9L12 21l-7.8-4.5v-9z") + C(12, 12, 4)],
  ["weather", "Atmosphere & Climate", "Physical Sciences", C(9, 8, 3) + D("M9 2.5v1M3.5 8h1M5.1 4.1l.7.7M12.9 4.1l-.7.7M8.5 20a3.5 3.5 0 0 1-.4-7 5 5 0 0 1 9.5-.8 3.9 3.9 0 0 1 .4 7.8z")],
  ["mountain", "Earth Sciences", "Physical Sciences", D("m2 20 7-12 4 6 3-4 6 10zM6.8 11.6 9 13.2l2-1.5")],
  ["wave2", "Oceanography", "Physical Sciences", D("M2 8c2 0 2-1.5 4-1.5S8 8 10 8s2-1.5 4-1.5S16 8 18 8s2-1.5 4-1.5M2 13c2 0 2-1.5 4-1.5s2 1.5 4 1.5 2-1.5 4-1.5 2 1.5 4 1.5 2-1.5 4-1.5M2 18c2 0 2-1.5 4-1.5s2 1.5 4 1.5 2-1.5 4-1.5 2 1.5 4 1.5 2-1.5 4-1.5")],
  // Life sciences
  ["biology", "Biology", "Life Sciences", D("M7 3c0 4.5 10 4.5 10 9s-10 4.5-10 9M17 3c0 4.5-10 4.5-10 9s10 4.5 10 9M8.3 10.6h7.4M8.3 13.4h7.4M9.6 4.6h4.8M9.6 19.4h4.8")],
  ["microbe", "Microbiology", "Life Sciences", C(12, 12, 5) + D("M17 12h2.5M15.5 15.5l1.8 1.8M12 17v2.5M8.5 15.5l-1.8 1.8M7 12H4.5M8.5 8.5 6.7 6.7M12 7V4.5M15.5 8.5l1.8-1.8") + DOT(10.5, 11, 1) + DOT(13.5, 13.5, .8)],
  ["microscope", "Lab Science", "Life Sciences", D("M4 21h16M6.5 21v-2h11v2M15 10a5 5 0 0 1-4 8.5M8.2 14h4.5M9.7 14l-1.7-4") + R(8, 2.5, 4, 8.5, 1, ` transform="rotate(-22 10 7)"`)],
  ["leaf", "Ecology", "Life Sciences", D("M5 19C5 10 10 4 20 4c0 10-6 15-15 15zM5 19l8-8")],
  ["sprout", "Environment", "Life Sciences", D("M12 21v-9M12 12C12 7.5 9 5 4 5c0 4.5 3 7 8 7zM12 14.5c0-4 2.5-6.5 8-6.5 0 4-3 6.5-8 6.5zM7 21h10")],
  ["paw", "Zoology", "Life Sciences", D("M12 12c-3 0-5.5 3.3-5.5 5.5 0 2 1.5 3 3 3 1 0 1.5-.5 2.5-.5s1.5.5 2.5.5c1.5 0 3-1 3-3 0-2.2-2.5-5.5-5.5-5.5z") + `<ellipse cx="4.8" cy="10.5" rx="1.7" ry="2.2"/><ellipse cx="9" cy="6" rx="1.8" ry="2.4"/><ellipse cx="15" cy="6" rx="1.8" ry="2.4"/><ellipse cx="19.2" cy="10.5" rx="1.7" ry="2.2"/>`],
  ["fish", "Marine Biology", "Life Sciences", D("M2.5 7 6 12l-3.5 5M6 12c2.5-4 6-6 9.5-6 2.8 0 5 2.4 6 6-1 3.6-3.2 6-6 6-3.5 0-7-2-9.5-6z") + DOT(17, 10.8, 1)],
  ["brain", "Neuroscience", "Life Sciences", D("M12 5.5a2.8 2.8 0 0 0-5.3-.9A2.8 2.8 0 0 0 4.3 8.8a3 3 0 0 0 .2 5.4 3 3 0 0 0 2.6 4.6 2.8 2.8 0 0 0 4.9.7zM12 5.5a2.8 2.8 0 0 1 5.3-.9 2.8 2.8 0 0 1 2.4 4.2 3 3 0 0 1-.2 5.4 3 3 0 0 1-2.6 4.6 2.8 2.8 0 0 1-4.9.7zM12 5.5v14")],
  ["heart", "Medicine & Health", "Life Sciences", D("M12 20C3.8 12.7 2.4 9.3 3.6 6.6A5 5 0 0 1 12 5.2a5 5 0 0 1 8.4 1.4c1.2 2.7-.2 6.1-8.4 13.4zM5 12h3l1.5-3 3 6 1.5-3h5")],
  ["pill", "Pharmacology", "Life Sciences", R(2.5, 8.5, 19, 7, 3.5, ` transform="rotate(-45 12 12)"`) + D("m8.5 8.5 7 7")],
  ["apple", "Nutrition", "Life Sciences", D("M12 7.5c-1.5-1-3-1.5-4.5-1C5 7.2 4 9.5 4 12c0 4.5 3 9 5.5 9 1 0 1.5-.5 2.5-.5s1.5.5 2.5.5c2.5 0 5.5-4.5 5.5-9 0-2.5-1-4.8-3.5-5.5-1.5-.5-3 0-4.5 1zM12 7.5c0-2 1-3.5 3-4.5")],
  ["dumbbell", "Kinesiology", "Life Sciences", R(5, 6, 3, 12, 1) + R(16, 6, 3, 12, 1) + D("M8 12h8M3.5 9v6M20.5 9v6")],
  // Engineering
  ["gear", "Engineering", "Engineering", D("M18.0 10.3L20.5 10.6L20.5 13.4L18.0 13.7L17.4 15.1L19.0 17.0L17.0 19.0L15.1 17.4L13.7 18.0L13.4 20.5L10.6 20.5L10.3 18.0L8.9 17.4L7.0 19.0L5.0 17.0L6.6 15.1L6.0 13.7L3.5 13.4L3.5 10.6L6.0 10.3L6.6 8.9L5.0 7.0L7.0 5.0L8.9 6.6L10.3 6.0L10.6 3.5L13.4 3.5L13.7 6.0L15.1 6.6L17.0 5.0L19.0 7.0L17.4 8.9z") + C(12, 12, 2.6)],
  ["bolt", "Electrical Engineering", "Engineering", D("M13 2 4 14h7l-1 8 9-12h-7z")],
  ["wrench", "Mechanical Engineering", "Engineering", D("M14.5 3.3a5 5 0 0 0-4.6 6.9L3.6 16.5a2 2 0 0 0 2.9 2.9l6.3-6.3a5 5 0 0 0 6.9-4.6l-3 3-2.8-.7-.7-2.8z")],
  ["bridge", "Civil Engineering", "Engineering", D("M2 15h20M7 6v12M17 6v12M2 9.5C4.5 9.5 7 6 7 6s2 5.5 5 5.5S17 6 17 6s2.5 3.5 5 3.5M10 10.4V15M12 11.5V15M14 10.4V15")],
  ["setsquare", "Architecture & Design", "Engineering", D("M3 21V4l17 17zM7 17v-5l5 5zM3 8h2M3 12h2M3 16h2")],
  ["city", "Urban Planning", "Engineering", D("M3 21h18M5 21V9l5-3v15M10 21V11h5v10M15 21V5h4v16M7.5 11v.01M7.5 14v.01M7.5 17v.01M17 8v.01M17 11v.01M17 14v.01")],
  ["lightbulb", "Design & Innovation", "Engineering", D("M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2v.1h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z")],
  // Humanities
  ["history", "History", "Humanities", D("M3 9h18L12 4zM4 21h16M5 18h14M6.5 9.5v8M10 9.5v8M14 9.5v8M17.5 9.5v8")],
  ["hourglass", "Ancient & Medieval", "Humanities", D("M6 3h12M6 21h12M7 3c0 4.5 5 6 5 9s-5 4.5-5 9M17 3c0 4.5-5 6-5 9s5 4.5 5 9M9.5 18.5h5")],
  ["amphora", "Classics & Archaeology", "Humanities", D("M9 3h6M10 3v3c-3 1-5 4-5 8 0 3 1.5 5.5 3 7h8c1.5-1.5 3-4 3-7 0-4-2-7-5-8V3M6 11h12M5.5 15h13")],
  ["book", "Literature", "Humanities", D("M12 6.5C10 5 7 4.5 3 4.5v14c4 0 7 .5 9 2 2-1.5 5-2 9-2v-14c-4 0-7 .5-9 2zM12 6.5v14")],
  ["quill", "Writing", "Humanities", D("M20 3C12 3 7.5 8 6.5 16.5l3.5.5C16 15 19 10 20 3zM4 21l8-8")],
  ["thought", "Philosophy", "Humanities", D("M21 11.5a8.5 8.5 0 0 1-12.6 7.4L3 20.5l1.6-5.1A8.5 8.5 0 1 1 21 11.5zM9.8 9.5a2.2 2.2 0 1 1 3.2 2c-.6.3-1 .8-1 1.5v.4") + DOT(12, 16, .9)],
  ["languages", "Languages", "Humanities", D("M3 5.5A1.5 1.5 0 0 1 4.5 4h8A1.5 1.5 0 0 1 14 5.5v5a1.5 1.5 0 0 1-1.5 1.5H8l-3 2.5V12h-.5A1.5 1.5 0 0 1 3 10.5zM17 9h2.5A1.5 1.5 0 0 1 21 10.5v5a1.5 1.5 0 0 1-1.5 1.5H19v2.5L16 17h-4.5a1.5 1.5 0 0 1-1.5-1.5V15M6.5 10l2-4.5 2 4.5M7.2 8.6h2.6")],
  ["linguistics", "Linguistics", "Humanities", D("M3 19 7.5 6 12 19M4.7 14.5h5.6M19.5 12.5V19") + C(16.5, 16, 3)],
  ["music", "Music", "Humanities", D("M9 18V5l11-2v13M9 9l11-2") + C(6.5, 18, 2.5) + C(17.5, 16, 2.5)],
  ["palette", "Art", "Humanities", D("M12 3a9 9 0 0 0 0 18c1.2 0 2-.8 2-1.8 0-.5-.2-.9-.5-1.3-.3-.3-.5-.8-.5-1.3 0-1 .8-1.8 1.8-1.8H17a4 4 0 0 0 4-4C21 6.6 17 3 12 3z") + DOT(7.5, 11.5, 1.2) + DOT(9.5, 7.5, 1.2) + DOT(14.5, 7.5, 1.2) + DOT(17, 11, 1.2)],
  ["film", "Film & Media", "Humanities", R(4, 3, 16, 18, 1.5) + D("M8 3v18M16 3v18M4 7.5h4M4 12h4M4 16.5h4M16 7.5h4M16 12h4M16 16.5h4")],
  ["camera", "Photography", "Humanities", D("M3 8.5A1.5 1.5 0 0 1 4.5 7H7l1.5-2.5h7L17 7h2.5A1.5 1.5 0 0 1 21 8.5v10a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z") + C(12, 13.5, 3.5)],
  // Social sciences
  ["globe", "Geography", "Social Sciences", C(12, 12, 9) + `<ellipse cx="12" cy="12" rx="4" ry="9"/>` + D("M3 12h18M4.5 7.5h15M4.5 16.5h15")],
  ["map", "Cartography & GIS", "Social Sciences", D("M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20zM9 4v13.5M15 6.5V20")],
  ["psychology", "Psychology", "Social Sciences", D("M8.5 21v-3H6.5A1.5 1.5 0 0 1 5 16.5V14l-1.8-.6L5 9.8A7 7 0 0 1 19 10.5c0 2.4-1 4.3-2.5 5.5V21") + C(12, 10, 2.2) + D("M12 6.3v1.5M12 12.2v1.5M8.3 10h1.5M14.2 10h1.5")],
  ["people", "Sociology", "Social Sciences", C(9, 8, 3) + D("M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 14.3c2.9.2 5 2.6 5 5.7") + C(17, 9, 2.5)],
  ["capitol", "Political Science", "Social Sciences", D("M3 21h18M5 18h14M6 18v-6M10 18v-6M14 18v-6M18 18v-6M4 12h16M6.5 12a5.5 5.5 0 0 1 11 0M12 6.5V4")],
  ["scales", "Law", "Social Sciences", D("M12 3v17M8 20.5h8M4.5 6.5h15M4.5 6.5 2 13.5h5zM19.5 6.5 17 13.5h5zM2 13.5a2.5 2.5 0 0 0 5 0M17 13.5a2.5 2.5 0 0 0 5 0") + DOT(12, 3.5, 1.2)],
  ["trend", "Economics", "Social Sciences", D("M3 3v18h18M7 15l4-4 3 3 6-6M16 8h4v4")],
  ["coin", "Finance & Accounting", "Social Sciences", C(12, 12, 9) + D("M14.6 9.3c-.4-1-1.4-1.7-2.6-1.7-1.5 0-2.6.8-2.6 2 0 2.8 5.4 1.6 5.4 4.6 0 1.2-1.2 2.1-2.7 2.1-1.3 0-2.4-.7-2.8-1.8M12 6v1.6M12 16.4V18")],
  ["briefcase", "Business", "Social Sciences", R(3, 7, 18, 13, 2) + D("M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M3 12.5h18M11 12.5v1.5h2v-1.5")],
  ["megaphone", "Communication", "Social Sciences", D("M3 10v4a1 1 0 0 0 1 1h2.5L14 19.5v-15L6.5 9H4a1 1 0 0 0-1 1zM6.5 15l1.5 5.5h2.5L9.3 16M17.5 9a4 4 0 0 1 0 6M19.5 6.5a7.5 7.5 0 0 1 0 11")],
  ["cap", "Education", "Social Sciences", D("M2 9 12 4l10 5-10 5zM6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5M22 9v6")],
];

export const COURSE_ICONS = LIST.map(([id, name, group, body]) => ({ id, name, group, body }));
const BY_ID = new Map(COURSE_ICONS.map(i => [i.id, i]));

// The icon a course code suggests, by its letters: "csc258" → "compsci".
const BY_CODE = {
  csc: "compsci", cs: "compsci", cse: "compsci", comp: "compsci", cmpt: "compsci", cscb: "compsci", cscc: "compsci", cscd: "compsci",
  ece: "chip", ecen: "chip", eee: "bolt", ee: "bolt", ele: "bolt", rob: "robot", aer: "rocket", aps: "gear", eng: "gear", mie: "wrench", mec: "wrench", me: "wrench", civ: "bridge", ce: "bridge",
  mat: "math", math: "math", mth: "math", mata: "math", matb: "math", apm: "calculus", sta: "stats", stat: "stats", sds: "chart", ds: "chart",
  phy: "physics", phys: "physics", ast: "planet", astr: "planet", chm: "chemistry", chem: "chemistry", che: "chemistry",
  bio: "biology", biol: "biology", bch: "molecule", mgy: "microbe", mij: "microbe", mic: "microbe", eeb: "leaf", env: "sprout", ees: "sprout", ess: "mountain", glg: "mountain", geol: "mountain", eas: "mountain", jpe: "weather",
  hmb: "brain", neu: "brain", nrsc: "brain", pcl: "pill", phm: "pill", nfs: "apple", nutr: "apple", kpe: "dumbbell", kin: "dumbbell", hlth: "heart", med: "heart", nur: "heart", nurs: "heart",
  psy: "psychology", psyc: "psychology", soc: "people", ant: "amphora", anth: "amphora", cla: "amphora", clas: "amphora", his: "history", hist: "history",
  ggr: "globe", geog: "globe", geo: "globe", pol: "capitol", pols: "capitol", law: "scales", eco: "trend", econ: "trend", rsm: "briefcase", mgt: "briefcase", bus: "briefcase", acc: "coin", fin: "coin",
  phl: "thought", phil: "thought", lin: "linguistics", ling: "linguistics", fre: "languages", spa: "languages", ger: "languages", ita: "languages", jal: "languages",
  ini: "megaphone", com: "megaphone", engl: "book", lit: "book", wri: "quill", mus: "music", music: "music", fah: "palette", vis: "palette", art: "palette", cin: "film", film: "film", arc: "setsquare", arch: "setsquare", jav: "setsquare", plan: "city", edu: "cap", educ: "cap",
};
export function guessIcon(code) {
  const letters = String(code || "").toLowerCase().match(/^[a-z]+/);
  if (!letters) return "book";
  const s = letters[0];
  for (let n = s.length; n >= 2; n--) if (BY_CODE[s.slice(0, n)]) return BY_CODE[s.slice(0, n)];
  return "book";
}

// The <svg> for an icon id (an unknown id draws as a book).
export function courseIcon(id) {
  const i = BY_ID.get(id) || BY_ID.get("book");
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${i.body}</svg>`;
}
export const iconName = id => (BY_ID.get(id) || BY_ID.get("book")).name;
export const isIcon = id => BY_ID.has(id);
