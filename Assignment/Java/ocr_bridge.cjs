const fs = require('fs');
const path = require('path');
const {createWorker} = require('tesseract.js');
(async () => {
  const image = path.resolve(process.argv[2]);
  if (!fs.statSync(image).isFile()) throw new Error('Expected a local image file');
  const cache = path.join(__dirname, 'ocr_cache');
  fs.mkdirSync(cache, {recursive:true});
  const worker = await createWorker('eng', 1, {cachePath:cache});
  try { const result = await worker.recognize(image); process.stdout.write(result.data.text); }
  finally { await worker.terminate(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
