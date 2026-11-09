// Renderiza cada .post[data-nome] de um HTML em PNG no tamanho exato (1080 px de largura).
// Uso: node scripts/render.mjs [arquivo.html] [pasta-de-saida] [--escala=1]
import {chromium} from 'playwright';
import {mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const args = process.argv.slice(2);
const escala = Number((args.find((a) => a.startsWith('--escala=')) || '--escala=1').split('=')[1]);
const [arquivo = 'exemplo/index.html', saida = 'out'] = args.filter((a) => !a.startsWith('--'));
mkdirSync(saida, {recursive: true});

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {});
const page = await browser.newPage({viewport: {width: 2400, height: 2000}, deviceScaleFactor: escala});
await page.goto(pathToFileURL(resolve(arquivo)).href, {waitUntil: 'networkidle'});
await page.evaluate(() => document.fonts.ready);
const posts = await page.$$('.post[data-nome]');
for (const post of posts) {
  const nome = await post.getAttribute('data-nome');
  await post.screenshot({path: `${saida}/${nome}.png`});
  console.log(`${saida}/${nome}.png`);
}
await browser.close();
if (!posts.length) console.error('Nenhum .post[data-nome] encontrado.');
