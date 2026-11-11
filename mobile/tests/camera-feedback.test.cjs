const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/camera-feedback.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const moduleExports = {};
vm.runInNewContext(source, { exports: moduleExports });
const feedback = moduleExports.cameraFeedback;

test('camera advice names a view problem only when the answer supports it', () => {
  assert.match(feedback(true, "The ground isn't visible in this view."), /tilt the camera slightly downward/);
  assert.match(feedback(true, 'The image is too dark to identify the sign.'), /better light/);
  assert.match(feedback(true, 'The object is blurry.'), /hold the camera steady/i);
  assert.match(feedback(true, 'The object is cut off.'), /center it in the frame/);
});

test('uncertainty alone receives neutral guidance and certain answers receive none', () => {
  const generic = feedback(true, 'I cannot identify it confidently.', ['quality_override']);
  assert.match(generic, /center what you want to identify/);
  assert.doesNotMatch(generic, /is too dark|ground isn't visible/);
  assert.equal(feedback(false, 'The ground is clearly visible.'), null);
  assert.equal(feedback(true, 'No nearby place found.', [], false), null);
  assert.match(feedback(true, 'I could not get a fresh frame.', ['current_view_timeout']), /fresh view/);
});
