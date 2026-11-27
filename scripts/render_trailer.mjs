// Render the SerbiaCiv trailer from the real app and its synthesized score.
// Requires Python 3, Playwright + Chromium, and ffmpeg. Run from the repository root:
//   NODE_PATH=$(npm root -g) node scripts/render_trailer.mjs
import { createRequire } from 'node:module';
import { spawn, spawnSync } from 'node:child_process';
import { mkdtemp, writeFile, rm, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createServer } from 'node:net';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root = resolve('.');
const temp = await mkdtemp(join(tmpdir(), 'serbiaciv-trailer-'));
const socket = createServer();
await new Promise((resolve, reject) => socket.once('error', reject).listen(0, '127.0.0.1', resolve));
const port = socket.address().port;
await new Promise((resolve) => socket.close(resolve));
const server = spawn('python3', ['-m', 'http.server', String(port), '--bind', '127.0.0.1', '--directory', join(root, 'web')], { stdio: 'ignore' });
let browser;
const base = `http://127.0.0.1:${port}/`;
const run = (cmd, args) => {
  const p = spawnSync(cmd, args, { stdio: 'inherit' });
  if (p.status !== 0) throw new Error(`${cmd} exited with ${p.status}`);
};
const scenes = [
  { hash: '#script=lat', duration: 4, kicker: 'STVARNI PODACI. NOVI POGLED.', title: 'SRBIJA KAO STRATEŠKA MAPA', sub: 'Interaktivni atlas izgrađen od javnih podataka' },
  { hash: '#city=79014&view=city&script=lat', mode: 'city', duration: 5, kicker: 'GRADOVI I LJUDI', title: 'ISTRAŽI BEOGRAD', sub: 'Stanovništvo, građani, kvartovi i privreda' },
  { hash: '#lens=pop_change&script=lat', lens: 'pop_change', duration: 4, kicker: 'PODACI NA MAPI', title: 'KAKO SE SRBIJA MENJA', sub: 'Sočiva otkrivaju demografske promene' },
  { hash: '#city=89010&view=city&script=lat', mode: 'city', duration: 4, kicker: 'SVAKI GRAD IMA PRIČU', title: 'NOVI SAD', sub: 'Pogledaj grad kroz njegove ljude i delatnosti' },
  { hash: '#lens=relief&script=lat', lens: 'relief', place: 'Nacionalni park Kopaonik', duration: 4, kicker: 'OD RAVNICE DO PLANINE', title: 'TEREN IZ STVARNIH PODATAKA', sub: 'Reljef, reke, priroda i znamenitosti' },
  { hash: '#advisor=economy&script=lat', mode: 'advisor', duration: 4, kicker: 'OTKRIJ ŠIRU SLIKU', title: 'EKONOMIJA I RESURSI', sub: 'Uporedi gradove, okruge i javne pokazatelje' },
  { hash: '#script=lat', duration: 5, kicker: 'OTVORENI PODACI · OTVORENI KOD', title: 'ISTRAŽI SVOJU SRBIJU', sub: 'acailic.github.io/serbiaciv' },
];
const runId = (n) => String(n).padStart(2, '0');

try {
  for (let i = 0; i < 40; i++) {
    try { if ((await fetch(base)).ok) break; } catch {}
    if (i === 39) throw new Error('The local app server did not start');
    await new Promise((r) => setTimeout(r, 250));
  }
  browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  for (let i = 0; i < scenes.length; i++) {
    const scene = scenes[i];
    await page.goto(base + scene.hash, { waitUntil: 'load', timeout: 60000 });
    await page.waitForFunction(() => window.__app && !document.getElementById('loading'), null, { timeout: 60000 });
    if (scene.mode) await page.waitForFunction((mode) => window.__app.mode === mode, scene.mode, { timeout: 20000 });
    if (scene.lens) await page.waitForFunction((lens) => window.__app.state.lens?.id === lens, scene.lens, { timeout: 20000 });
    if (scene.place) {
      await page.evaluate(async (name) => {
        const data = await window.__app.loadData('wonders');
        const item = data.wonders.find((x) => x.name === name);
        if (!item) throw new Error(`Missing place: ${name}`);
        window.__app.flyTo(item.x, item.y, 3.1, 700);
      }, scene.place);
    }
    await page.waitForFunction(() => !window.__app.cam.moving, null, { timeout: 12000 }).catch(() => {});
    await page.waitForTimeout(500);
    await page.screenshot({ path: join(temp, `scene-${runId(i)}.png`) });
    console.log(`Captured ${scene.title}`);
  }

  // Reuse the original, code-synthesized score; these cue names are its timing interface.
  const download = page.waitForEvent('download', { timeout: 120000 });
  await page.evaluate(async () => {
    const { buildScore, toWav } = await import('./dev/trailer/score.js');
    const times = [['title', 0, 3.1], ['rockies', 3.1, 5.8], ['cities', 5.8, 9.8],
      ['lenses', 9.8, 15.3], ['improvements', 15.3, 19.9], ['city', 19.9, 24.6],
      ['trade', 24.6, 27.4], ['end', 27.4, 30]];
    const shots = times.map(([id, t0, t1]) => ({ id, t0, t1 }));
    const { buffer } = await buildScore({ shots, duration: 30, fade: 0.45 });
    const url = URL.createObjectURL(toWav(buffer));
    const a = document.createElement('a'); a.href = url; a.download = 'score.wav'; a.click();
  });
  await (await download).saveAs(join(temp, 'score.wav'));
  await browser.close(); browser = null;

  const font = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';
  const bold = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf';
  for (let i = 0; i < scenes.length; i++) {
    const scene = scenes[i], n = runId(i);
    for (const key of ['kicker', 'title', 'sub']) await writeFile(join(temp, `${n}-${key}.txt`), scene[key]);
    const text = (key, fontfile, size, y, color) => `drawtext=fontfile=${fontfile}:textfile=${join(temp, `${n}-${key}.txt`)}:fontsize=${size}:fontcolor=${color}:x=94:y=${y}:shadowcolor=black@0.8:shadowx=2:shadowy=2`;
    const filter = [
      `scale=2100:1182:force_original_aspect_ratio=increase`,
      `zoompan=z='min(pzoom+0.00035,1.055)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=30`,
      'format=yuv420p',
      'drawbox=x=0:y=ih-260:w=iw:h=260:color=0x08121e@0.88:t=fill',
      'drawbox=x=0:y=ih-260:w=iw:h=3:color=0xc9a45c@0.95:t=fill',
      text('kicker', bold, 24, 'h-229', '0xe7c47b'),
      text('title', bold, 54, 'h-181', '0xfff3d5'),
      text('sub', font, 30, 'h-105', '0xe0d5ba'),
      `fade=t=in:st=0:d=0.35`, `fade=t=out:st=${scene.duration - 0.35}:d=0.35`,
    ].join(',');
    run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-loop', '1', '-framerate', '30', '-i', join(temp, `scene-${n}.png`),
      '-vf', filter, '-t', String(scene.duration), '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24',
      '-pix_fmt', 'yuv420p', '-threads', '2', join(temp, `part-${n}.mp4`)]);
    console.log(`Rendered scene ${i + 1}/${scenes.length}`);
  }
  await writeFile(join(temp, 'parts.txt'), scenes.map((_, i) => `file '${join(temp, `part-${runId(i)}.mp4`)}'`).join('\n') + '\n');
  await mkdir(join(root, 'docs'), { recursive: true });
  const movie = join(root, 'docs', 'trailer.mp4');
  run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', join(temp, 'parts.txt'),
    '-i', join(temp, 'score.wav'), '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-t', '30', '-movflags', '+faststart', movie]);
  run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', movie, '-vf',
    'fps=6,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=5',
    '-loop', '0', '-threads', '1', join(root, 'docs', 'trailer-preview.gif')]);
  console.log('Created docs/trailer.mp4 and docs/trailer-preview.gif');
} finally {
  if (browser) await browser.close();
  server.kill();
  await rm(temp, { recursive: true, force: true });
}
