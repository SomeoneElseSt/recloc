// Renders each slide of the deck to a 1920×1080 PNG via headless Chrome.
// Usage: node tools/render-slide.mjs [outDir] [slideNumbers...]
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SLIDE_WIDTH = 1920;
const SLIDE_HEIGHT = 1080;
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const deckDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const deckHtml = readFileSync(join(deckDir, 'recloc-deck.html'), 'utf8');
const outDir = resolve(process.argv[2] ?? join(deckDir, 'render'));
const only = process.argv.slice(3).map(Number);

// The deck keeps its CSS inline and its slides in one <main>, so both can be lifted out directly.
const styles = [...deckHtml.matchAll(/<style>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join('\n');
const main = deckHtml.match(/<main class="deck">([\s\S]*?)<\/main>/)[1];
const slides = [...main.matchAll(/<section class="slide([^"]*)">([\s\S]*?)<\/section>/g)];
if (slides.length === 0) {
  console.error('No slides found in recloc-deck.html');
  process.exit(1);
}

// Print-style rules: show every slide the same way, drop the screen-view scaling.
const printStyles = `
  @page { size: ${SLIDE_WIDTH}px ${SLIDE_HEIGHT}px; margin: 0; }
  body { overflow: hidden; margin: 0; background: #000; }
  .deck { position: static !important; transform: none !important; left: auto !important; top: auto !important; }
  .slide { display: none; }
  .slide.current { display: block; }
  .slide.statement.current { display: flex; }
`;

if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });
const work = mkdtempSync(join(tmpdir(), 'recloc-render-'));
const targets = only.length ? only : slides.map((_, n) => n + 1);
for (const number of targets) {
  const slide = slides[number - 1];
  if (!slide) {
    console.error(`Slide ${number} does not exist (deck has ${slides.length})`);
    process.exit(1);
  }
  const page = `<!doctype html><html><head><meta charset="utf-8"><style>${styles}\n${printStyles}</style></head>
<body><main class="deck"><section class="slide${slide[1]} current">${slide[2]}</section></main></body></html>`;
  const htmlPath = join(work, `slide-${number}.html`);
  const pngPath = join(outDir, `slide-${String(number).padStart(2, '0')}.png`);
  writeFileSync(htmlPath, page);
  execFileSync(CHROME, [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    '--force-device-scale-factor=1',
    `--window-size=${SLIDE_WIDTH},${SLIDE_HEIGHT}`,
    `--screenshot=${pngPath}`,
    `file://${htmlPath}`,
  ], { stdio: 'ignore' });
  console.log(pngPath);
}
