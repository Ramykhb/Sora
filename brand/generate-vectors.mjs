import fs from 'node:fs/promises';

// Buddy: the open frame and two eyes from the selected concept.
const frame = 'M26 40V34C26 20 37 11 52 11H76C91 11 102 20 102 34V40M26 88V94C26 108 37 117 52 117H76C91 117 102 108 102 94V88';
const mark = `<path d="${frame}" stroke="#B79AFF" stroke-width="10" stroke-linecap="round" fill="none"/><rect x="41" y="49" width="13" height="30" rx="6.5" fill="#F3F0FF"/><rect x="74" y="49" width="13" height="30" rx="6.5" fill="#F3F0FF"/>`;
const lightMark = mark.replaceAll('#B79AFF', '#6840B7').replaceAll('#F3F0FF', '#191326');
const mono = mark.replaceAll('#B79AFF', '#FFFFFF').replaceAll('#F3F0FF', '#FFFFFF');
const tile = '<rect width="128" height="128" rx="28" fill="#131720"/>';
const svg = (size, content, box = '0 0 1024 1024') => `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="${box}">${content}</svg>`;

await fs.writeFile('brand/sora-symbol.svg', svg(128, mark, '0 0 128 128'));
// UI assets have true transparency. Light mode uses dark eyes for contrast.
await fs.writeFile('brand/sora-logo.svg', svg(512, `<g transform="scale(8)">${mark}</g>`));
await fs.writeFile('brand/sora-logo-light.svg', svg(512, `<g transform="scale(8)">${lightMark}</g>`));
await fs.writeFile('brand/sora-app-icon.svg', svg(1024, `<rect width="1024" height="1024" fill="#131720"/><g transform="translate(115.2 115.2) scale(6.2)">${mark}</g>`));
await fs.writeFile('brand/sora-adaptive-foreground.svg', svg(1024, `<g transform="translate(256 256) scale(4)">${tile}${mark}</g>`));
await fs.writeFile('brand/sora-monochrome.svg', svg(1024, `<g transform="translate(256 256) scale(4)">${mono}</g>`));
await fs.writeFile('brand/sora-hero.svg', svg(768, `<g transform="translate(264 264) scale(3.875)">${mark}</g>`));
await fs.writeFile('brand/sora-hero-light.svg', svg(768, `<g transform="translate(264 264) scale(3.875)">${lightMark}</g>`));
for (const name of ['sora-symbol.svg', 'sora-logo.svg', 'sora-logo-light.svg']) await fs.copyFile(`brand/${name}`, `dashboard/public/brand/${name}`);
